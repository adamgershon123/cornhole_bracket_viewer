from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable


STATISTIC_TYPES = {
    "ACL_REPORTED_CPI",
    "ACL_REPORTED_SEASON_PPR",
    "ACL_REPORTED_EVENT_PPR",
    "ACL_REPORTED_GAME_PPR",
    "ACL_REPORTED_PROFILE_PPR",
}

AVAILABILITY_STATUSES = {
    "AVAILABLE",
    "ZERO_UNVALIDATED",
    "MISSING",
    "INVALID_VALUE",
    "INVALID_EFFECTIVE_TIME",
}

PUBLIC_PLAYER_SNAPSHOT_ENDPOINTS = {
    "swap-standings",
    "swap-schedule-breakdown",
    "swap-up-next-players-list",
    "swiss-pairing-schedule-breakdown",
    "swiss-pairing-standings",
    "swiss-pairing-up-next-players-list",
}


def initialize_statistic_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS statistic_observations (
            statistic_observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_payload_id INTEGER NOT NULL,
            source_endpoint TEXT NOT NULL,
            source_json_path TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            statistic_type TEXT NOT NULL,
            numeric_value REAL,
            raw_value_json TEXT,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            bucket_id INTEGER,
            source_effective_at TEXT,
            retrieved_at TEXT NOT NULL,
            availability_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(source_payload_id) REFERENCES source_payloads(source_payload_id),
            UNIQUE(
                source_payload_id, source_json_path, player_id,
                statistic_type, scope_type, scope_id
            ),
            CHECK(statistic_type IN (
                'ACL_REPORTED_CPI',
                'ACL_REPORTED_SEASON_PPR',
                'ACL_REPORTED_EVENT_PPR',
                'ACL_REPORTED_GAME_PPR',
                'ACL_REPORTED_PROFILE_PPR'
            )),
            CHECK(availability_status IN (
                'AVAILABLE',
                'ZERO_UNVALIDATED',
                'MISSING',
                'INVALID_VALUE',
                'INVALID_EFFECTIVE_TIME'
            ))
        );

        CREATE INDEX IF NOT EXISTS idx_statistic_player_cutoff
            ON statistic_observations(
                player_id, statistic_type, source_effective_at, retrieved_at
            );

        CREATE INDEX IF NOT EXISTS idx_statistic_scope
            ON statistic_observations(scope_type, scope_id, statistic_type);
        """
    )
    conn.commit()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_timestamp(value: Any) -> tuple[str | None, bool]:
    if value in (None, "", "null", "undefined"):
        return None, True
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(), True


def normalize_numeric(value: Any) -> tuple[float | None, str]:
    if value in (None, "", "null", "undefined"):
        return None, "MISSING"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "INVALID_VALUE"
    if not math.isfinite(number):
        return None, "INVALID_VALUE"
    if number == 0:
        return 0.0, "ZERO_UNVALIDATED"
    return number, "AVAILABLE"


def record_statistic_observation(
    conn: sqlite3.Connection,
    *,
    source_payload_id: int,
    source_endpoint: str,
    source_json_path: str,
    player_id: int,
    statistic_type: str,
    raw_value: Any,
    scope_type: str,
    scope_id: str | int | None,
    retrieved_at: str,
    source_effective_at: Any = None,
    bucket_id: int | None = None,
) -> int:
    if statistic_type not in STATISTIC_TYPES:
        raise ValueError(f"Unsupported statistic type: {statistic_type}")
    initialize_statistic_schema(conn)
    numeric_value, availability = normalize_numeric(raw_value)
    effective_at, timestamp_valid = normalize_timestamp(source_effective_at)
    if source_effective_at not in (None, "", "null", "undefined") and not timestamp_valid:
        availability = "INVALID_EFFECTIVE_TIME"
    cursor = conn.execute(
        """
        INSERT INTO statistic_observations (
            source_payload_id, source_endpoint, source_json_path, player_id,
            statistic_type, numeric_value, raw_value_json, scope_type, scope_id,
            bucket_id, source_effective_at, retrieved_at, availability_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            source_payload_id, source_json_path, player_id,
            statistic_type, scope_type, scope_id
        ) DO NOTHING
        """,
        (
            source_payload_id,
            source_endpoint,
            source_json_path,
            int(player_id),
            statistic_type,
            numeric_value,
            json.dumps(raw_value, default=str),
            scope_type,
            None if scope_id is None else str(scope_id),
            bucket_id,
            effective_at,
            retrieved_at,
            availability,
            utc_now(),
        ),
    )
    row = conn.execute(
        """
        SELECT statistic_observation_id
        FROM statistic_observations
        WHERE source_payload_id=? AND source_json_path=? AND player_id=?
          AND statistic_type=? AND scope_type=? AND scope_id IS ?
        """,
        (
            source_payload_id,
            source_json_path,
            int(player_id),
            statistic_type,
            scope_type,
            None if scope_id is None else str(scope_id),
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("Statistic observation insert could not be resolved")
    observation_id = int(row[0])
    conn.commit()
    return observation_id


def _walk_player_rows(value: Any, path: str = "$") -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        player_id = value.get("playerID") or value.get("playerId") or value.get("playerid")
        if player_id not in (None, ""):
            yield path, value
        for key, child in value.items():
            yield from _walk_player_rows(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_player_rows(child, f"{path}[{index}]")


def _scope_from_entity_key(entity_key: str) -> tuple[str, str]:
    parts = entity_key.split(":")
    if parts and parts[0] in {"event", "game", "player", "bucket"}:
        return parts[0], ":".join(parts[1:])
    if entity_key.startswith("match-stats:"):
        return "game", entity_key.removeprefix("match-stats:")
    if len(parts) >= 2 and parts[0] in {
        "event-player-stats",
        "swap-standings",
        "swap-schedule-breakdown",
        "swap-up-next-players-list",
        "swiss-pairing-schedule-breakdown",
        "swiss-pairing-standings",
        "swiss-pairing-up-next-players-list",
    }:
        return "event", parts[1]
    return "source_entity", entity_key


def extract_statistic_observations(
    conn: sqlite3.Connection,
    *,
    source_payload_id: int,
    source_endpoint: str,
    entity_key: str,
    payload: Any,
    retrieved_at: str,
) -> int:
    initialize_statistic_schema(conn)
    scope_type, scope_id = _scope_from_entity_key(entity_key)
    recorded = 0

    if source_endpoint in PUBLIC_PLAYER_SNAPSHOT_ENDPOINTS:
        seen: set[tuple[Any, ...]] = set()
        for path, row in _walk_player_rows(payload):
            player_id = row.get("playerID") or row.get("playerId") or row.get("playerid")
            if "playerCPI" in row:
                cpi_key = (
                    int(player_id),
                    "ACL_REPORTED_CPI",
                    json.dumps(row.get("playerCPI"), default=str),
                    str(row.get("cPITimeStamp")),
                )
                if cpi_key not in seen:
                    seen.add(cpi_key)
                    record_statistic_observation(
                        conn,
                        source_payload_id=source_payload_id,
                        source_endpoint=source_endpoint,
                        source_json_path=f"{path}.playerCPI",
                        player_id=int(player_id),
                        statistic_type="ACL_REPORTED_CPI",
                        raw_value=row.get("playerCPI"),
                        scope_type=scope_type,
                        scope_id=scope_id,
                        retrieved_at=retrieved_at,
                        source_effective_at=row.get("cPITimeStamp"),
                    )
                    recorded += 1
            if "playerPPR" in row:
                ppr_key = (
                    int(player_id),
                    "ACL_REPORTED_PROFILE_PPR",
                    json.dumps(row.get("playerPPR"), default=str),
                )
                if ppr_key not in seen:
                    seen.add(ppr_key)
                    record_statistic_observation(
                        conn,
                        source_payload_id=source_payload_id,
                        source_endpoint=source_endpoint,
                        source_json_path=f"{path}.playerPPR",
                        player_id=int(player_id),
                        statistic_type="ACL_REPORTED_PROFILE_PPR",
                        raw_value=row.get("playerPPR"),
                        scope_type=scope_type,
                        scope_id=scope_id,
                        retrieved_at=retrieved_at,
                    )
                    recorded += 1

    elif source_endpoint == "player-compare-stats":
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            if not isinstance(row, dict) or row.get("playerID") in (None, ""):
                continue
            record_statistic_observation(
                conn,
                source_payload_id=source_payload_id,
                source_endpoint=source_endpoint,
                source_json_path=f"$.data[{index}].ptsPerRnd",
                player_id=int(row["playerID"]),
                statistic_type="ACL_REPORTED_SEASON_PPR",
                raw_value=row.get("ptsPerRnd"),
                scope_type="bucket",
                scope_id=row.get("bucketID"),
                bucket_id=int(row["bucketID"]) if row.get("bucketID") not in (None, "") else None,
                retrieved_at=retrieved_at,
            )
            recorded += 1

    elif source_endpoint == "event-player-stats":
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            if not isinstance(row, dict) or row.get("playerID") in (None, ""):
                continue
            record_statistic_observation(
                conn,
                source_payload_id=source_payload_id,
                source_endpoint=source_endpoint,
                source_json_path=f"$.data[{index}].ptsPerRnd",
                player_id=int(row["playerID"]),
                statistic_type="ACL_REPORTED_EVENT_PPR",
                raw_value=row.get("ptsPerRnd"),
                scope_type=scope_type,
                scope_id=scope_id,
                retrieved_at=retrieved_at,
            )
            recorded += 1

    elif source_endpoint == "match-stats":
        rows = payload.get("event_match_details", []) if isinstance(payload, dict) else []
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            player_id = row.get("playerid") if isinstance(row, dict) else None
            if player_id in (None, ""):
                continue
            record_statistic_observation(
                conn,
                source_payload_id=source_payload_id,
                source_endpoint=source_endpoint,
                source_json_path=f"$.event_match_details[{index}].ptsperrnd",
                player_id=int(player_id),
                statistic_type="ACL_REPORTED_GAME_PPR",
                raw_value=row.get("ptsperrnd"),
                scope_type=scope_type,
                scope_id=scope_id,
                retrieved_at=retrieved_at,
            )
            recorded += 1

    return recorded


def eligible_observations(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    statistic_type: str,
    cutoff_at: str,
) -> list[dict[str, Any]]:
    if statistic_type not in STATISTIC_TYPES:
        raise ValueError(f"Unsupported statistic type: {statistic_type}")
    initialize_statistic_schema(conn)
    cutoff, valid = normalize_timestamp(cutoff_at)
    if not valid or cutoff is None:
        raise ValueError(f"Invalid cutoff timestamp: {cutoff_at}")
    cursor = conn.execute(
        """
        SELECT *
        FROM statistic_observations
        WHERE player_id=?
          AND statistic_type=?
          AND availability_status='AVAILABLE'
          AND retrieved_at <= ?
          AND (source_effective_at IS NULL OR source_effective_at <= ?)
        ORDER BY COALESCE(source_effective_at, retrieved_at) DESC, retrieved_at DESC
        """,
        (int(player_id), statistic_type, cutoff, cutoff),
    )
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description or []]
    return [
        dict(row) if isinstance(row, sqlite3.Row) else dict(zip(columns, row))
        for row in rows
    ]
