from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_player_history_queue_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS player_history_queue (
            player_id INTEGER PRIMARY KEY,
            priority INTEGER NOT NULL DEFAULT 100,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reasons_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_attempted_at TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            rounds_before INTEGER,
            rounds_after INTEGER,
            events_after INTEGER,
            auth_blocked_count INTEGER NOT NULL DEFAULT 0,
            failure_message TEXT,
            CHECK(status IN (
                'PENDING', 'IN_PROGRESS', 'COMPLETE', 'PARTIAL', 'FAILED'
            ))
        );

        CREATE INDEX IF NOT EXISTS idx_history_queue_work
            ON player_history_queue(status, priority, first_seen_at);
        """
    )
    conn.commit()


def player_history_coverage(
    conn: sqlite3.Connection,
    player_id: int,
) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS rounds, COUNT(DISTINCT event_id) AS events
        FROM player_rounds
        WHERE player_id=?
        """,
        (int(player_id),),
    ).fetchone()
    return {"rounds": int(row[0] or 0), "events": int(row[1] or 0)}


def enqueue_players(
    conn: sqlite3.Connection,
    *,
    player_ids: Iterable[int],
    reason: dict[str, Any],
    priority: int = 100,
) -> int:
    initialize_player_history_queue_schema(conn)
    changed = 0
    now = utc_now()
    for player_id in sorted({int(value) for value in player_ids}):
        existing = conn.execute(
            "SELECT reasons_json, status FROM player_history_queue WHERE player_id=?",
            (player_id,),
        ).fetchone()
        reasons = json.loads(existing["reasons_json"]) if existing else []
        if reason not in reasons:
            reasons.append(reason)
        status = existing["status"] if existing else "PENDING"
        if status in {"FAILED", "PARTIAL"}:
            status = "PENDING"
        conn.execute(
            """
            INSERT INTO player_history_queue(
                player_id, priority, status, reasons_json,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                priority=MIN(player_history_queue.priority, excluded.priority),
                status=?,
                reasons_json=excluded.reasons_json,
                last_seen_at=excluded.last_seen_at
            """,
            (
                player_id,
                priority,
                status,
                json.dumps(reasons, sort_keys=True),
                now,
                now,
                status,
            ),
        )
        changed += 1
    conn.commit()
    return changed


def queued_history_report(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_player_history_queue_schema(conn)
    groups = conn.execute(
        """
        SELECT status, COUNT(*) AS players,
               COALESCE(SUM(rounds_after), 0) AS rounds_after,
               COALESCE(SUM(auth_blocked_count), 0) AS auth_blocked
        FROM player_history_queue
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()
    return {
        "totalPlayers": sum(int(row["players"]) for row in groups),
        "groups": [dict(row) for row in groups],
    }


def process_player_history_queue(
    conn: sqlite3.Connection,
    *,
    collector: Callable[..., dict[str, Any]],
    limit: int = 5,
    minimum_rounds: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    bucket_id: int = 11,
    bucket_ids: Iterable[int] | None = None,
    refresh_index: bool = False,
) -> dict[str, Any]:
    initialize_player_history_queue_schema(conn)
    # A player may gain sufficient history through the general collector after
    # being queued. Reconcile that coverage before selecting work so a player
    # with hundreds of rounds cannot monopolize a roster-priority batch.
    conn.execute(
        """
        UPDATE player_history_queue
        SET status='COMPLETE',
            rounds_after=(
                SELECT COUNT(*) FROM player_rounds
                WHERE player_rounds.player_id=player_history_queue.player_id
            ),
            events_after=(
                SELECT COUNT(DISTINCT event_id) FROM player_rounds
                WHERE player_rounds.player_id=player_history_queue.player_id
            ),
            failure_message=NULL
        WHERE status IN ('PENDING', 'PARTIAL', 'IN_PROGRESS')
          AND (
              SELECT COUNT(*) FROM player_rounds
              WHERE player_rounds.player_id=player_history_queue.player_id
          ) >= ?
        """,
        (int(minimum_rounds),),
    )
    conn.commit()
    rows = conn.execute(
        """
        SELECT player_id
        FROM player_history_queue
        WHERE status IN ('PENDING', 'PARTIAL')
        ORDER BY priority, first_seen_at, player_id
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    report = {
        "selected": len(rows),
        "complete": 0,
        "partial": 0,
        "failed": 0,
        "players": [],
    }
    for row in rows:
        player_id = int(row["player_id"])
        before = player_history_coverage(conn, player_id)
        conn.execute(
            """
            UPDATE player_history_queue
            SET status='IN_PROGRESS', rounds_before=?, last_attempted_at=?,
                attempt_count=attempt_count+1, failure_message=NULL
            WHERE player_id=?
            """,
            (before["rounds"], utc_now(), player_id),
        )
        conn.commit()
        try:
            collector_args = dict(
                player_ids=[player_id],
                start_date=start_date,
                end_date=end_date,
                bucket_id=bucket_id,
                force=False,
                refresh_index=refresh_index,
                include_profiles=False,
                full_event=False,
            )
            if bucket_ids is not None:
                collector_args["bucket_ids"] = list(bucket_ids)
            result = collector(**collector_args)
            after = player_history_coverage(conn, player_id)
            coverage = result.get("manifest", {}).get("coverage", {})
            auth_blocked = int(coverage.get("matchStatsAuthBlocked") or 0)
            status = "COMPLETE" if after["rounds"] >= minimum_rounds else "PARTIAL"
            conn.execute(
                """
                UPDATE player_history_queue
                SET status=?, rounds_after=?, events_after=?,
                    auth_blocked_count=?, failure_message=NULL
                WHERE player_id=?
                """,
                (
                    status,
                    after["rounds"],
                    after["events"],
                    auth_blocked,
                    player_id,
                ),
            )
            report[status.lower()] += 1
            report["players"].append({
                "playerId": player_id,
                "status": status,
                "roundsBefore": before["rounds"],
                "roundsAfter": after["rounds"],
                "eventsAfter": after["events"],
                "authBlocked": auth_blocked,
            })
        except Exception as exc:
            conn.execute(
                """
                UPDATE player_history_queue
                SET status='FAILED', failure_message=?
                WHERE player_id=?
                """,
                (str(exc), player_id),
            )
            report["failed"] += 1
            report["players"].append({
                "playerId": player_id,
                "status": "FAILED",
                "error": str(exc),
            })
        conn.commit()
    return report
