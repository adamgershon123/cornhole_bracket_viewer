from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_walker_repair_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS walker_repair_queue (
            event_id INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            game_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            discovered_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            PRIMARY KEY(event_id, match_id, game_id)
        );
        """
    )


def seed_walker_repairs(conn: sqlite3.Connection, limit: int = 25) -> int:
    ensure_walker_repair_schema(conn)
    rows = conn.execute(
        """
        SELECT DISTINCT event_id, match_id, game_id
        FROM player_rounds r
        WHERE r.player_id=99999
          AND NOT EXISTS (
            SELECT 1 FROM walker_repair_queue q
            WHERE q.event_id=r.event_id AND q.match_id=r.match_id AND q.game_id=r.game_id
          )
        ORDER BY event_id DESC, CAST(match_id AS INTEGER), game_id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO walker_repair_queue(event_id, match_id, game_id, discovered_at) VALUES (?, ?, ?, ?)",
            (row["event_id"], row["match_id"], row["game_id"], _now()),
        )
    conn.commit()
    return len(rows)


def walker_repair_status(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_walker_repair_schema(conn)
    groups = conn.execute(
        "SELECT status, COUNT(*) AS count FROM walker_repair_queue GROUP BY status"
    ).fetchall()
    counts = {row["status"]: int(row["count"]) for row in groups}
    last = conn.execute(
        "SELECT * FROM walker_repair_queue ORDER BY COALESCE(finished_at, started_at, discovered_at) DESC LIMIT 1"
    ).fetchone()
    undiscovered = conn.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT DISTINCT event_id, match_id, game_id FROM player_rounds WHERE player_id=99999
          EXCEPT
          SELECT event_id, match_id, game_id FROM walker_repair_queue
        )
        """
    ).fetchone()[0]
    return {
        "status": "RUNNING",
        "pending": counts.get("PENDING", 0),
        "complete": counts.get("COMPLETE", 0),
        "failed": counts.get("FAILED", 0),
        "undiscoveredCandidates": int(undiscovered or 0),
        "lastItem": dict(last) if last else None,
    }


def _cached_payload_path(conn: sqlite3.Connection, data_dir: str, event_id: int, match_id: str, game_id: int) -> str | None:
    row = conn.execute(
        """
        SELECT local_path FROM api_manifest
        WHERE entity_type='game' AND entity_id=? AND source_endpoint='match-stats'
        ORDER BY last_checked DESC LIMIT 1
        """,
        (f"{event_id}:{match_id}:{game_id}",),
    ).fetchone()
    candidates = [
        row["local_path"] if row else None,
        os.path.join(data_dir, f"event_{event_id}_match_{match_id}_game_{game_id}_stats.json"),
        os.path.join(data_dir, "season_platform", "raw", f"event_{event_id}_match_{match_id}_game_{game_id}_stats.json"),
    ]
    return next((str(path) for path in candidates if path and Path(path).exists()), None)


def process_one_walker_repair(conn: sqlite3.Connection, data_dir: str, normalizer: Callable[..., int]) -> dict[str, Any]:
    ensure_walker_repair_schema(conn)
    row = conn.execute(
        "SELECT * FROM walker_repair_queue WHERE status IN ('PENDING','FAILED') AND attempts < 3 ORDER BY discovered_at LIMIT 1"
    ).fetchone()
    if not row:
        return {"status": "IDLE"}
    key = (row["event_id"], row["match_id"], row["game_id"])
    conn.execute(
        "UPDATE walker_repair_queue SET status='RUNNING', started_at=?, attempts=attempts+1, last_error=NULL WHERE event_id=? AND match_id=? AND game_id=?",
        (_now(), *key),
    )
    conn.commit()
    try:
        path = _cached_payload_path(conn, data_dir, *key)
        if not path:
            raise FileNotFoundError("Cached raw match-stat response is unavailable")
        with open(path, "r", encoding="utf-8") as source:
            payload = json.load(source)
        saved = normalizer(conn, key[0], str(key[1]), int(key[2]), payload)
        participation = conn.execute(
            "SELECT 1 FROM walker_participations WHERE event_id=? AND match_id=? AND game_id=? LIMIT 1",
            key,
        ).fetchone()
        if not participation:
            raise ValueError("Candidate was not a definitive ACL synthetic-seat walker game")
        conn.execute(
            "UPDATE walker_repair_queue SET status='COMPLETE', finished_at=? WHERE event_id=? AND match_id=? AND game_id=?",
            (_now(), *key),
        )
        conn.commit()
        return {"status": "COMPLETE", "eventId": key[0], "matchId": key[1], "gameId": key[2], "rows": saved}
    except Exception as exc:
        conn.execute(
            "UPDATE walker_repair_queue SET status='FAILED', finished_at=?, last_error=? WHERE event_id=? AND match_id=? AND game_id=?",
            (_now(), str(exc)[:1000], *key),
        )
        conn.commit()
        return {"status": "FAILED", "error": str(exc), "eventId": key[0], "matchId": key[1], "gameId": key[2]}


def start_walker_repair_worker(db_factory: Callable[[], sqlite3.Connection], data_dir: str, normalizer: Callable[..., int]) -> None:
    def worker() -> None:
        time.sleep(75)
        while True:
            try:
                with db_factory() as conn:
                    seed_walker_repairs(conn, limit=10)
                    result = process_one_walker_repair(conn, data_dir, normalizer)
                if result.get("status") != "IDLE":
                    print(f"Walker history repair: {result}", flush=True)
            except Exception as exc:
                print(f"Walker history repair cycle failed: {exc}", flush=True)
            time.sleep(120)

    threading.Thread(target=worker, daemon=True, name="walker-history-repair").start()
