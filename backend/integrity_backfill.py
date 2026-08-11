from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from data_integrity import INTEGRITY_VERSION, inspect_match_payload


MATCH_FILE = re.compile(r"event_(\d+)_match_(.+)_game_(\d+)_stats\.json$")
MATCH_ENTITY = re.compile(r"^match-stats:(\d+):(.+):(\d+)$")


def _payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("payload"), dict):
        return value["payload"]
    return value if isinstance(value, dict) else {}


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _archive_hash(payload: Any) -> str:
    """Match the canonical hash used by provenance/payload_archive."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cached_match_files(data_dir: str | Path) -> dict[tuple[int, str, int], Path]:
    selected: dict[tuple[int, str, int], Path] = {}
    for path in Path(data_dir).rglob("event_*_match_*_game_*_stats.json"):
        match = MATCH_FILE.match(path.name)
        if not match:
            continue
        key = (int(match.group(1)), match.group(2), int(match.group(3)))
        current = selected.get(key)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            selected[key] = path
    return selected


def archived_match_sources(conn: sqlite3.Connection) -> dict[tuple[int, str, int], dict[str, Any]]:
    """Return the newest hash-verified archive record for each ACL game."""
    available = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_payloads'"
    ).fetchone()
    if not available:
        return {}
    selected: dict[tuple[int, str, int], dict[str, Any]] = {}
    rows = conn.execute(
        """
        SELECT source_payload_id,entity_key,payload_hash,payload_json,archive_path,
               archive_codec,retrieved_at
        FROM source_payloads
        WHERE source_endpoint='match-stats'
        ORDER BY retrieved_at DESC, source_payload_id DESC
        """
    ).fetchall()
    for row in rows:
        match = MATCH_ENTITY.match(str(row["entity_key"] or ""))
        if not match:
            continue
        key = (int(match.group(1)), match.group(2), int(match.group(3)))
        if key not in selected:
            selected[key] = dict(row)
    return selected


def _archive_root(conn: sqlite3.Connection, data_dir: str | Path) -> Path:
    configured = os.environ.get("PAYLOAD_ARCHIVE_DIR")
    if configured:
        return Path(configured)
    candidate = Path(data_dir) / "season_platform" / "payload_archive"
    if candidate.exists():
        return candidate
    database = conn.execute("PRAGMA database_list").fetchone()
    return Path(database[2]).resolve().parent / "payload_archive"


def _archived_payload(record: dict[str, Any], root: Path) -> dict[str, Any]:
    if record.get("payload_json"):
        value = json.loads(str(record["payload_json"]))
    else:
        if record.get("archive_codec") != "gzip-json-v1" or not record.get("archive_path"):
            raise ValueError("Archived payload has no supported readable representation")
        with gzip.open(root / str(record["archive_path"]), "rt", encoding="utf-8") as handle:
            value = json.load(handle)
    if _archive_hash(value) != str(record.get("payload_hash") or ""):
        raise ValueError("Archived payload hash verification failed")
    if isinstance(value, dict) and isinstance(value.get("payload"), dict):
        value = value["payload"]
    return value if isinstance(value, dict) else {}


def audit_cached_match_stats(
    conn: sqlite3.Connection,
    data_dir: str | Path,
    *,
    apply: bool = False,
    limit: int | None = None,
    event_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    # Delayed import avoids the season_platform -> data_integrity dependency
    # becoming a circular import at module initialization.
    from season_platform import match_stats_completed, normalize_match_stats_to_rounds

    conn.row_factory = sqlite3.Row
    files = cached_match_files(data_dir)
    archives = archived_match_sources(conn)
    archive_root = _archive_root(conn, data_dir)
    source_keys = set(archives) | set(files)
    result: dict[str, Any] = {
        "integrityVersion": INTEGRITY_VERSION,
        "mode": "APPLY" if apply else "DRY_RUN",
        "filesDiscovered": len(files),
        "archivePayloadsDiscovered": len(archives),
        "sourcesDiscovered": len(source_keys),
        "eligibleFinalGames": 0,
        "partialGames": 0,
        "alreadyCurrent": 0,
        "validated": 0,
        "quarantined": 0,
        "remaining": 0,
        "games": [],
    }
    # Keep only lightweight references between discovery and processing. Some
    # ACL payloads are large; retaining every decoded response here exceeded
    # the production worker memory limit before the first game could commit.
    pending: list[tuple[tuple[int, str, int], str, str]] = []

    def load_source(key: tuple[int, str, int]) -> tuple[dict[str, Any], str]:
        # Loose files represent the latest operational cache and override an
        # older archived observation for the same game.
        if key in files:
            return _payload(files[key]), str(files[key])
        return (
            _archived_payload(archives[key], archive_root),
            f"source_payload:{archives[key]['source_payload_id']}",
        )

    event_match_types = {
        int(row[0]): row[1]
        for row in conn.execute("SELECT event_id,match_type FROM events").fetchall()
    }
    for key in sorted(source_keys):
        if event_id is not None and key[0] != int(event_id):
            continue
        try:
            payload, source = load_source(key)
        except Exception as exc:
            result["quarantined"] += 1
            result["games"].append({"eventId": key[0], "matchId": key[1], "gameId": key[2], "status": "UNREADABLE", "error": str(exc)})
            continue
        completed = match_stats_completed(payload)
        if completed:
            result["eligibleFinalGames"] += 1
        else:
            result["partialGames"] += 1
        fingerprint = _hash(payload)
        existing = conn.execute(
            """SELECT integrity_version,source_payload_hash FROM game_data_integrity
               WHERE event_id=? AND match_id=? AND game_id=?""",
            key,
        ).fetchone()
        if existing and existing["integrity_version"] == INTEGRITY_VERSION and existing["source_payload_hash"] == fingerprint and not force:
            result["alreadyCurrent"] += 1
            continue
        pending.append((key, source, fingerprint))

    selected = pending[: max(0, int(limit))] if limit is not None else pending
    result["remaining"] = max(0, len(pending) - len(selected))
    for key, source, fingerprint in selected:
        try:
            payload, reloaded_source = load_source(key)
            reloaded_fingerprint = _hash(payload)
        except Exception as exc:
            result["quarantined"] += 1
            result["games"].append({
                "eventId": key[0], "matchId": key[1], "gameId": key[2],
                "status": "UNREADABLE", "error": str(exc), "source": source,
            })
            continue
        if reloaded_source != source or reloaded_fingerprint != fingerprint:
            # Never certify a source that changed between discovery and use.
            result["quarantined"] += 1
            result["games"].append({
                "eventId": key[0], "matchId": key[1], "gameId": key[2],
                "status": "UNSTABLE_SOURCE", "source": source,
                "error": "Source changed during integrity audit",
            })
            continue
        completed = match_stats_completed(payload)
        inspection = inspect_match_payload(
            payload,
            completed=completed,
            match_type=event_match_types.get(key[0]),
        )
        status = ("WOULD_VERIFY" if inspection["passed"] else "WOULD_QUARANTINE") if completed else "WOULD_RETAIN_RAW_ONLY"
        if apply:
            normalize_match_stats_to_rounds(conn, key[0], key[1], key[2], payload)
            row = conn.execute(
                """SELECT integrity_status FROM game_data_integrity
                   WHERE event_id=? AND match_id=? AND game_id=?""",
                key,
            ).fetchone()
            status = str(row[0]) if row else "MISSING"
        if status in {"VERIFIED", "WOULD_VERIFY"}:
            result["validated"] += 1
        elif status in {"PARTIAL", "WOULD_RETAIN_RAW_ONLY"}:
            pass
        else:
            result["quarantined"] += 1
        result["games"].append({
            "eventId": key[0], "matchId": key[1], "gameId": key[2],
            "status": status, "source": source, "checks": inspection,
            "sourcePayloadHash": fingerprint,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit or migrate cached ACL match-stat files into Data Integrity v2.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--event-id", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.database, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        from season_platform import init_db
        init_db(conn)
        result = audit_cached_match_stats(
            conn, args.data_dir, apply=args.apply, limit=args.limit,
            event_id=args.event_id, force=args.force,
        )
        print(json.dumps(result, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
