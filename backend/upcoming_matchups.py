from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from acl_prediction_assistance import hydrate_acl_prediction_assistance
from provenance import canonical_payload_hash
from player_history_queue import enqueue_players, initialize_player_history_queue_schema
from shadow_predictions import (
    SHADOW_MODEL_VERSION,
    create_shadow_prediction,
    initialize_shadow_schema,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_upcoming_schema(conn: sqlite3.Connection) -> None:
    initialize_shadow_schema(conn)
    initialize_player_history_queue_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS upcoming_matchup_candidates (
            candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            source_endpoint TEXT NOT NULL,
            format TEXT NOT NULL,
            scheduled_start_at TEXT,
            source_timezone TEXT,
            home_player_ids_json TEXT NOT NULL,
            away_player_ids_json TEXT NOT NULL,
            match_status_id INTEGER,
            discovery_status TEXT NOT NULL,
            discovery_issue TEXT,
            source_hash TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            pregame_verified INTEGER NOT NULL DEFAULT 0,
            timing_basis TEXT NOT NULL DEFAULT 'SCHEDULED_MATCH_START',
            roster_revealed_at TEXT,
            UNIQUE(event_id, match_id, source_endpoint)
        );

        CREATE INDEX IF NOT EXISTS idx_upcoming_ready
            ON upcoming_matchup_candidates(
                discovery_status, scheduled_start_at, event_id
            );
        """
    )
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(upcoming_matchup_candidates)").fetchall()
    }
    for name, declaration in (
        ("pregame_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("timing_basis", "TEXT NOT NULL DEFAULT 'SCHEDULED_MATCH_START'"),
        ("roster_revealed_at", "TEXT"),
    ):
        if name not in columns:
            conn.execute(
                f"ALTER TABLE upcoming_matchup_candidates ADD COLUMN {name} {declaration}"
            )
    conn.commit()


def _identifier(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _player_ids(rows: Any) -> list[int]:
    values = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        value = _identifier(
            row,
            "playerID",
            "playerId",
            "playerid",
            "fldPlayerID",
            "userID",
        )
        try:
            values.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(set(values))


def _schedule_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("overAllSchedule", "availableMatchList", "inProgressMatchList", "schedule"):
        rows = data.get(key)
        if isinstance(rows, list) and rows:
            return [row for row in rows if isinstance(row, dict)]
    return []


def _normalize_timestamp(
    raw: Any,
    *,
    source_timezone: str | None,
) -> tuple[str | None, str | None]:
    if raw in (None, ""):
        return None, "MISSING_SCHEDULED_START"
    try:
        parsed = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError:
        return None, "INVALID_SCHEDULED_START"
    if parsed.tzinfo is None:
        if not source_timezone:
            return None, "MISSING_SOURCE_TIMEZONE"
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(source_timezone))
        except Exception:
            return None, "INVALID_SOURCE_TIMEZONE"
    return parsed.astimezone(timezone.utc).isoformat(), None


def ingest_schedule_matchups(
    conn: sqlite3.Connection,
    *,
    event_id: str | int,
    payload: dict[str, Any],
    source_endpoint: str,
    format_name: str,
    source_timezone: str | None = None,
    observed_at: str | None = None,
    event_start_at: str | None = None,
) -> dict[str, Any]:
    initialize_upcoming_schema(conn)
    observed_at = observed_at or utc_now()
    counts = {
        "rowsSeen": 0,
        "ready": 0,
        "completed": 0,
        "missingSides": 0,
        "missingTime": 0,
    }
    seen_matches: set[str] = set()
    for row in _schedule_rows(payload):
        match_id = _identifier(row, "matchID", "matchId", "matchid", "bracketmatchid")
        if match_id in (None, "") or str(match_id) in seen_matches:
            continue
        seen_matches.add(str(match_id))
        counts["rowsSeen"] += 1
        home = _player_ids(
            row.get("homeTeam")
            or row.get("homePlayers")
            or row.get("homePlayerList")
        )
        away = _player_ids(
            row.get("awayTeam")
            or row.get("awayPlayers")
            or row.get("awayPlayerList")
        )
        status_id = _identifier(row, "matchStatusID", "matchStatusId", "statusID")
        try:
            status_id = int(status_id) if status_id is not None else None
        except (TypeError, ValueError):
            status_id = None
        scheduled, time_issue = _normalize_timestamp(
            _identifier(row, "matchStartTime", "scheduledStartTime", "startTime"),
            source_timezone=source_timezone,
        )
        home_score = _identifier(row, "homeScore", "team1Score")
        away_score = _identifier(row, "awayScore", "team2Score")
        game_results = row.get("gameResults")
        result_status = _identifier(row, "resultGameStatus", "gameStatusID")
        match_status = str(row.get("matchStatus") or "").strip().lower()
        zero_score = (
            float(home_score or 0) == 0
            and float(away_score or 0) == 0
            and (
                not isinstance(game_results, dict)
                or (
                    float(game_results.get("homeScore") or 0) == 0
                    and float(game_results.get("awayScore") or 0) == 0
                )
            )
        )
        pregame_verified = (
            status_id == 1
            and match_status in {"scheduled", "upcoming", "available", ""}
            and zero_score
            and result_status in (None, "", 0, "0")
            and not row.get("matchEndTime")
        )
        timing_basis = "SCHEDULED_MATCH_START"
        if scheduled is None and pregame_verified and event_start_at:
            scheduled = event_start_at
            time_issue = None
            timing_basis = "EVENT_START_ROSTER_REVEAL"
        if status_id == 5:
            status, issue = "COMPLETED", None
            counts["completed"] += 1
        elif not home or not away:
            status, issue = "BLOCKED", "INCOMPLETE_SIDE_IDENTITIES"
            counts["missingSides"] += 1
        elif time_issue:
            status, issue = "BLOCKED", time_issue
            counts["missingTime"] += 1
        else:
            status, issue = "READY", None
            counts["ready"] += 1
        conn.execute(
            """
            INSERT INTO upcoming_matchup_candidates(
                event_id, match_id, source_endpoint, format,
                scheduled_start_at, source_timezone, home_player_ids_json,
                away_player_ids_json, match_status_id, discovery_status,
                discovery_issue, source_hash, first_seen_at, last_seen_at
                , pregame_verified, timing_basis, roster_revealed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, match_id, source_endpoint) DO UPDATE SET
                scheduled_start_at=excluded.scheduled_start_at,
                source_timezone=excluded.source_timezone,
                home_player_ids_json=excluded.home_player_ids_json,
                away_player_ids_json=excluded.away_player_ids_json,
                match_status_id=excluded.match_status_id,
                discovery_status=excluded.discovery_status,
                discovery_issue=excluded.discovery_issue,
                source_hash=excluded.source_hash,
                last_seen_at=excluded.last_seen_at,
                pregame_verified=excluded.pregame_verified,
                timing_basis=excluded.timing_basis,
                roster_revealed_at=COALESCE(upcoming_matchup_candidates.roster_revealed_at, excluded.roster_revealed_at)
            """,
            (
                str(event_id),
                str(match_id),
                source_endpoint,
                format_name,
                scheduled,
                source_timezone,
                json.dumps(home),
                json.dumps(away),
                status_id,
                status,
                issue,
                canonical_payload_hash(row),
                observed_at,
                observed_at,
                1 if pregame_verified else 0,
                timing_basis,
                observed_at if pregame_verified else None,
            ),
        )
        if home or away:
            enqueue_players(
                conn,
                player_ids=[*home, *away],
                reason={
                    "source": source_endpoint,
                    "eventId": str(event_id),
                    "matchId": str(match_id),
                    "format": format_name,
                },
                priority=10 if status == "READY" else 20,
            )
    conn.commit()
    return counts


def create_due_shadow_predictions(
    conn: sqlite3.Connection,
    *,
    as_of: str | None = None,
    lookahead_minutes: int = 180,
) -> dict[str, Any]:
    initialize_upcoming_schema(conn)
    now = datetime.fromisoformat((as_of or utc_now()).replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    horizon = now + timedelta(minutes=lookahead_minutes)
    rows = conn.execute(
        """
        SELECT *
        FROM upcoming_matchup_candidates
        WHERE discovery_status='READY'
          AND scheduled_start_at <= ?
          AND (scheduled_start_at > ? OR pregame_verified=1)
        ORDER BY scheduled_start_at, event_id, match_id
        """,
        (horizon.isoformat(), now.isoformat()),
    ).fetchall()
    summary: dict[str, Any] = {
        "asOf": now.isoformat(),
        "lookaheadMinutes": lookahead_minutes,
        "dueCandidates": len(rows),
        "predicted": 0,
        "abstained": 0,
        "alreadyRecorded": 0,
        "errors": [],
    }
    due_player_ids: set[int] = set()
    for row in rows:
        due_player_ids.update(json.loads(row["home_player_ids_json"]))
        due_player_ids.update(json.loads(row["away_player_ids_json"]))
    internally_covered: set[int] = set()
    if due_player_ids:
        placeholders = ",".join("?" for _ in due_player_ids)
        internally_covered = {
            int(row[0])
            for row in conn.execute(
                f"""
                SELECT DISTINCT player_id
                FROM player_rounds
                WHERE player_id IN ({placeholders})
                  AND event_date IS NOT NULL
                  AND event_date < ?
                """,
                [*sorted(due_player_ids), now.date().isoformat()],
            ).fetchall()
        }
    summary["rapidHistoryAssistance"] = hydrate_acl_prediction_assistance(
        conn,
        player_ids=due_player_ids - internally_covered,
        bucket_id=11,
    )
    summary["rapidHistoryAssistance"]["internallyCoveredPlayers"] = len(
        internally_covered
    )
    prediction_recorded_at = utc_now()
    for row in rows:
        existing = conn.execute(
            """
            SELECT shadow_run_id FROM shadow_prediction_runs
            WHERE event_id=? AND match_id=? AND model_version=?
            """,
            (row["event_id"], row["match_id"], SHADOW_MODEL_VERSION),
        ).fetchone()
        if existing:
            summary["alreadyRecorded"] += 1
            continue
        try:
            result = create_shadow_prediction(
                conn,
                event_id=row["event_id"],
                match_id=row["match_id"],
                side_a_player_ids=json.loads(row["home_player_ids_json"]),
                side_b_player_ids=json.loads(row["away_player_ids_json"]),
                recorded_at=prediction_recorded_at,
                scheduled_start_at=row["scheduled_start_at"],
                pregame_status_verified=bool(row["pregame_verified"]),
                timing_basis=row["timing_basis"],
            )
            if result["status"] == "PREDICTED":
                summary["predicted"] += 1
            else:
                summary["abstained"] += 1
        except Exception as exc:
            summary["errors"].append({
                "eventId": row["event_id"],
                "matchId": row["match_id"],
                "error": str(exc),
            })
    return summary


def matchup_discovery_report(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_upcoming_schema(conn)
    rows = conn.execute(
        """
        SELECT discovery_status, COALESCE(discovery_issue, 'NONE') AS issue,
               COUNT(*) AS count
        FROM upcoming_matchup_candidates
        GROUP BY discovery_status, COALESCE(discovery_issue, 'NONE')
        ORDER BY discovery_status, issue
        """
    ).fetchall()
    return {
        "totalCandidates": sum(int(row["count"]) for row in rows),
        "groups": [dict(row) for row in rows],
    }
