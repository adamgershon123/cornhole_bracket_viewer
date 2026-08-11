from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARCHIVE_CODEC = "gzip-json-v1"
ARCHIVE_BATCH_SIZE = 25
ARCHIVE_IDLE_SECONDS = 2.0
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _database_path(conn: sqlite3.Connection) -> Path | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if not row or not row[2] or row[2] == ":memory:":
        return None
    return Path(row[2]).resolve()


def archive_root(conn: sqlite3.Connection) -> Path | None:
    db_path = _database_path(conn)
    if db_path is None:
        return None
    configured = os.environ.get("PAYLOAD_ARCHIVE_DIR")
    return Path(configured).resolve() if configured else db_path.parent / "payload_archive"


def initialize_payload_archive_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(source_payloads)").fetchall()
    }
    additions = {
        "archive_path": "TEXT",
        "archive_codec": "TEXT",
        "archive_size_bytes": "INTEGER",
        "archive_verified_at": "TEXT",
        "inline_size_bytes": "INTEGER",
    }
    for name, declaration in additions.items():
        if name not in columns:
            conn.execute(
                f"ALTER TABLE source_payloads ADD COLUMN {name} {declaration}"
            )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS payload_archive_runs (
            payload_archive_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            payloads_archived INTEGER NOT NULL DEFAULT 0,
            source_bytes_archived INTEGER NOT NULL DEFAULT 0,
            archive_bytes_written INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_source_payload_archive_pending
            ON source_payloads(archive_verified_at, source_payload_id);
        """
    )
    conn.commit()


def _relative_archive_path(payload_hash: str) -> Path:
    return Path(payload_hash[:2]) / payload_hash[2:4] / f"{payload_hash}.json.gz"


def _write_verified_archive(
    root: Path,
    payload_hash: str,
    serialized: str,
) -> tuple[Path, int]:
    relative = _relative_archive_path(payload_hash)
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not destination.exists():
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=destination.parent,
            prefix=".payload-",
            suffix=".tmp",
        ) as temporary:
            temporary_path = Path(temporary.name)
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=temporary,
                compresslevel=6,
                mtime=0,
            ) as compressed:
                compressed.write(serialized.encode("utf-8"))
        os.replace(temporary_path, destination)

    with gzip.open(destination, "rt", encoding="utf-8") as archived:
        restored = json.load(archived)
    if _canonical_hash(restored) != payload_hash:
        raise ValueError(f"Archive verification failed for {payload_hash}")
    return relative, destination.stat().st_size


def archive_pending_payloads(
    conn: sqlite3.Connection,
    *,
    limit: int = ARCHIVE_BATCH_SIZE,
) -> dict[str, int | str]:
    initialize_payload_archive_schema(conn)
    root = archive_root(conn)
    if root is None:
        return {
            "status": "SKIPPED",
            "archived": 0,
            "sourceBytes": 0,
            "archiveBytes": 0,
        }
    root.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    cursor = conn.execute(
        "INSERT INTO payload_archive_runs(started_at, status) VALUES (?, 'RUNNING')",
        (started,),
    )
    run_id = int(cursor.lastrowid)
    conn.commit()
    rows = conn.execute(
        """
        SELECT source_payload_id, payload_hash, payload_json
        FROM source_payloads
        WHERE archive_verified_at IS NULL
          AND COALESCE(payload_json, '') != ''
        ORDER BY source_payload_id
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()
    archived = 0
    source_bytes = 0
    archive_bytes = 0
    try:
        for row in rows:
            serialized = str(row["payload_json"])
            restored = json.loads(serialized)
            if _canonical_hash(restored) != row["payload_hash"]:
                raise ValueError(
                    f"Inline payload hash mismatch for {row['source_payload_id']}"
                )
            relative, compressed_size = _write_verified_archive(
                root,
                str(row["payload_hash"]),
                serialized,
            )
            original_size = len(serialized.encode("utf-8"))
            conn.execute(
                """
                UPDATE source_payloads
                SET archive_path=?, archive_codec=?,
                    archive_size_bytes=?, archive_verified_at=?,
                    inline_size_bytes=?, payload_json=''
                WHERE source_payload_id=?
                  AND archive_verified_at IS NULL
                """,
                (
                    relative.as_posix(),
                    ARCHIVE_CODEC,
                    compressed_size,
                    utc_now(),
                    original_size,
                    row["source_payload_id"],
                ),
            )
            archived += 1
            source_bytes += original_size
            archive_bytes += compressed_size
        conn.execute(
            """
            UPDATE payload_archive_runs
            SET finished_at=?, status='COMPLETE', payloads_archived=?,
                source_bytes_archived=?, archive_bytes_written=?
            WHERE payload_archive_run_id=?
            """,
            (utc_now(), archived, source_bytes, archive_bytes, run_id),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.execute(
            """
            UPDATE payload_archive_runs
            SET finished_at=?, status='FAILED', error_message=?
            WHERE payload_archive_run_id=?
            """,
            (utc_now(), str(exc), run_id),
        )
        conn.commit()
        raise
    return {
        "status": "COMPLETE",
        "archived": archived,
        "sourceBytes": source_bytes,
        "archiveBytes": archive_bytes,
    }


def load_source_payload(
    conn: sqlite3.Connection,
    source_payload_id: int,
) -> Any:
    initialize_payload_archive_schema(conn)
    row = conn.execute(
        """
        SELECT payload_json, payload_hash, archive_path, archive_codec
        FROM source_payloads WHERE source_payload_id=?
        """,
        (int(source_payload_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown source payload {source_payload_id}")
    if row["payload_json"]:
        payload = json.loads(row["payload_json"])
    else:
        root = archive_root(conn)
        if root is None or not row["archive_path"]:
            raise FileNotFoundError(
                f"Source payload {source_payload_id} has no readable content"
            )
        if row["archive_codec"] != ARCHIVE_CODEC:
            raise ValueError(f"Unsupported archive codec {row['archive_codec']}")
        with gzip.open(root / row["archive_path"], "rt", encoding="utf-8") as source:
            payload = json.load(source)
    if _canonical_hash(payload) != row["payload_hash"]:
        raise ValueError(f"Source payload {source_payload_id} failed hash validation")
    return payload


def payload_archive_health(
    conn: sqlite3.Connection,
    *,
    initialize: bool = True,
) -> dict[str, Any]:
    if initialize:
        initialize_payload_archive_schema(conn)
    root = archive_root(conn)
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN archive_verified_at IS NOT NULL THEN 1 ELSE 0 END) AS archived,
            SUM(CASE WHEN archive_verified_at IS NULL
                      AND COALESCE(payload_json, '') != '' THEN 1 ELSE 0 END) AS pending,
            COALESCE(SUM(inline_size_bytes), 0) AS source_bytes_archived,
            COALESCE(SUM(archive_size_bytes), 0) AS archive_bytes,
            MAX(archive_verified_at) AS last_verified_at
        FROM source_payloads
        """
    ).fetchone()
    failed = conn.execute(
        "SELECT COUNT(*) FROM payload_archive_runs WHERE status='FAILED'"
    ).fetchone()[0]
    latest_run = conn.execute(
        """
        SELECT status, error_message
        FROM payload_archive_runs
        ORDER BY payload_archive_run_id DESC
        LIMIT 1
        """
    ).fetchone()
    archived = int(row["archived"] or 0)
    archive_bytes = int(row["archive_bytes"] or 0)
    source_bytes = int(row["source_bytes_archived"] or 0)
    return {
        "status": (
            "HEALTHY"
            if latest_run is None or latest_run["status"] == "COMPLETE"
            else "ATTENTION"
        ),
        "totalPayloads": int(row["total"] or 0),
        "archivedPayloads": archived,
        "pendingPayloads": int(row["pending"] or 0),
        "sourceBytesArchived": source_bytes,
        "archiveBytes": archive_bytes,
        "spaceReductionRate": (
            round(1 - archive_bytes / source_bytes, 4) if source_bytes else 0
        ),
        "lastVerifiedAt": row["last_verified_at"],
        "failedRuns": int(failed or 0),
        "latestRunStatus": latest_run["status"] if latest_run else None,
        "latestError": latest_run["error_message"] if latest_run else None,
        "archiveDirectory": str(root) if root else None,
    }


def start_payload_archive_worker(db_factory: Any) -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True

    def worker() -> None:
        time.sleep(15)
        while True:
            delay = ARCHIVE_IDLE_SECONDS
            try:
                with db_factory() as conn:
                    result = archive_pending_payloads(conn)
                if int(result.get("archived") or 0) > 0:
                    delay = 0.25
            except Exception as exc:
                print(f"Payload archive cycle failed: {exc}")
                delay = 10
            time.sleep(delay)

    threading.Thread(
        target=worker,
        daemon=True,
        name="payload-archive",
    ).start()
