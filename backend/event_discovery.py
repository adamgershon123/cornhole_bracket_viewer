from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

import requests

from provenance import record_ingestion_attempt, record_source_payload


EVENTS_RADIUS_URL = "https://api.iplayacl.com/api/v1/events-radius"
SENSITIVE_KEYS = {
    "email",
    "playeremail",
    "adminemail",
    "phone",
    "playerphone",
    "token",
    "cookie",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_event_discovery_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS event_discovery_searches (
            search_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_id INTEGER NOT NULL,
            request_json TEXT NOT NULL,
            source_payload_id INTEGER,
            event_count INTEGER NOT NULL,
            redacted_field_count INTEGER NOT NULL,
            searched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS discovered_events (
            event_id INTEGER PRIMARY KEY,
            bucket_id INTEGER NOT NULL,
            event_name TEXT,
            event_date TEXT,
            advertised_time TEXT,
            status TEXT,
            match_type TEXT,
            bracket_type TEXT,
            blind_draw INTEGER,
            event_type TEXT,
            event_sub_type TEXT,
            event_list_type TEXT,
            cobs_event TEXT,
            location_name TEXT,
            location_city TEXT,
            location_state TEXT,
            location_country TEXT,
            location_lat REAL,
            location_lng REAL,
            distance REAL,
            format_candidate TEXT NOT NULL,
            format_basis TEXT NOT NULL,
            event_group TEXT NOT NULL DEFAULT 'STANDARD',
            event_group_basis TEXT NOT NULL DEFAULT 'DEFAULT',
            timezone_status TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_discovered_event_date
            ON discovered_events(event_date, status, format_candidate);
        """
    )
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(discovered_events)").fetchall()
    }
    if "event_group" not in columns:
        conn.execute(
            "ALTER TABLE discovered_events ADD COLUMN event_group TEXT NOT NULL DEFAULT 'STANDARD'"
        )
    if "event_group_basis" not in columns:
        conn.execute(
            "ALTER TABLE discovered_events ADD COLUMN event_group_basis TEXT NOT NULL DEFAULT 'DEFAULT'"
        )
    conn.execute(
        """
        UPDATE discovered_events
        SET event_group='SIT_AND_GO', event_group_basis='EVENT_NAME'
        WHERE LOWER(REPLACE(REPLACE(REPLACE(COALESCE(event_name, ''), ' ', ''), '&', 'and'), '''', ''))
              LIKE '%sitandgo%'
           OR LOWER(REPLACE(REPLACE(COALESCE(event_name, ''), ' ', ''), '''', ''))
              LIKE '%sitngo%'
        """
    )
    conn.commit()


def redact_discovery_payload(value: Any) -> tuple[Any, int]:
    if isinstance(value, list):
        redacted, counts = zip(
            *(redact_discovery_payload(item) for item in value),
            strict=False,
        ) if value else ((), ())
        return list(redacted), sum(counts)
    if isinstance(value, dict):
        result = {}
        count = 0
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS:
                result[key] = "[REDACTED_PERSONAL_DATA]"
                count += 1
            else:
                result[key], nested = redact_discovery_payload(item)
                count += nested
        return result, count
    return value, 0


def _format_candidate(row: dict[str, Any]) -> tuple[str, str]:
    name = str(row.get("leagueName") or "").lower()
    bracket = str(row.get("bracketType") or "").upper()
    if bracket == "W":
        return "SWISS_CANDIDATE", "BRACKET_TYPE"
    if bracket == "P":
        return "SWAP_CANDIDATE", "BRACKET_TYPE"
    if bracket:
        return "BRACKET_CANDIDATE", "BRACKET_TYPE"
    if "rounders" in name or "swiss" in name:
        return "SWISS_CANDIDATE", "EVENT_NAME"
    if "swap" in name:
        return "SWAP_CANDIDATE", "EVENT_NAME"
    return "BRACKET_CANDIDATE", "DEFAULT_EVENT_LIST"


def _event_group(row: dict[str, Any]) -> tuple[str, str]:
    name = str(row.get("leagueName") or "")
    compact = re.sub(r"[^a-z0-9]+", "", name.lower())
    if "sitandgo" in compact or "sitngo" in compact:
        return "SIT_AND_GO", "EVENT_NAME"
    return "STANDARD", "DEFAULT"


def _upsert_event(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    bucket_id: int,
    observed_at: str,
) -> bool:
    event_id = row.get("eventID") or row.get("leagueID")
    if event_id in (None, "") or row.get("eventListType") == "reg":
        return False
    candidate, basis = _format_candidate(row)
    event_group, event_group_basis = _event_group(row)
    conn.execute(
        """
        INSERT INTO discovered_events(
            event_id, bucket_id, event_name, event_date, advertised_time,
            status, match_type, bracket_type, blind_draw, event_type,
            event_sub_type, event_list_type, cobs_event, location_name,
            location_city, location_state, location_country, location_lat,
            location_lng, distance, format_candidate, format_basis,
            event_group, event_group_basis, timezone_status, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, 'UNRESOLVED', ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            bucket_id=excluded.bucket_id,
            event_name=excluded.event_name,
            event_date=excluded.event_date,
            advertised_time=excluded.advertised_time,
            status=excluded.status,
            match_type=excluded.match_type,
            bracket_type=excluded.bracket_type,
            blind_draw=excluded.blind_draw,
            event_type=excluded.event_type,
            event_sub_type=excluded.event_sub_type,
            event_list_type=excluded.event_list_type,
            cobs_event=excluded.cobs_event,
            location_name=excluded.location_name,
            location_city=excluded.location_city,
            location_state=excluded.location_state,
            location_country=excluded.location_country,
            location_lat=excluded.location_lat,
            location_lng=excluded.location_lng,
            distance=excluded.distance,
            format_candidate=excluded.format_candidate,
            format_basis=excluded.format_basis,
            event_group=excluded.event_group,
            event_group_basis=excluded.event_group_basis,
            last_seen_at=excluded.last_seen_at
        """,
        (
            int(event_id),
            bucket_id,
            row.get("leagueName"),
            row.get("leagueStartDate"),
            row.get("leagueTime"),
            row.get("leagueStatus"),
            row.get("matchType") or row.get("leagueMatchType"),
            row.get("bracketType"),
            int(bool(row.get("blindDraw") or row.get("leagueBlindDraw"))),
            row.get("eventType"),
            row.get("eventSubType"),
            row.get("eventListType"),
            row.get("cobsEvent"),
            row.get("locationName"),
            row.get("locationCity"),
            row.get("locationState"),
            row.get("locationCountry"),
            row.get("mapLat"),
            row.get("mapLng"),
            row.get("distance"),
            candidate,
            basis,
            event_group,
            event_group_basis,
            observed_at,
            observed_at,
        ),
    )
    return True


def search_acl_events(
    conn: sqlite3.Connection,
    *,
    bucket_id: int,
    origin_lat: float,
    origin_lng: float,
    event_range: float = 10000,
    selected_time: str = "WEEK",
    time_range: int = 1,
    event_country_code: str = "US",
    event_state: str = "ALL",
    event_status: str = "ALL",
    event_type: str = "ALL",
    event_blind_draw: str = "ALL",
    team_format: str = "ALL",
    search_address: str = "",
    app_version: str = "14.1.0",
    session: Any = requests,
) -> dict[str, Any]:
    initialize_event_discovery_schema(conn)
    request_payload = {
        "originLat": origin_lat,
        "originLng": origin_lng,
        "searchAddress": search_address,
        "eventRange": event_range,
        "eventBlindDraw": event_blind_draw,
        "eventCountryCode": event_country_code,
        "eventState": event_state,
        "eventStatus": event_status,
        "eventType": event_type,
        "selectedCount": 1,
        "selectedTime": selected_time,
        "teamFormat": team_format,
        "timeRange": time_range,
    }
    url = f"{EVENTS_RADIUS_URL}?bucket_id={int(bucket_id)}"
    entity_key = f"bucket:{bucket_id}:search:{origin_lat:.5f},{origin_lng:.5f}"
    try:
        response = session.post(
            url,
            json=request_payload,
            headers={
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "origin": "https://app.iplayacl.com",
                "referer": "https://app.iplayacl.com/",
                "x-app-version": app_version,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        record_ingestion_attempt(
            conn,
            source_endpoint="events-radius",
            entity_key=entity_key,
            request_url=url,
            outcome="network_error",
            error_kind=type(exc).__name__,
            error_message=str(exc),
        )
        raise
    if response.status_code >= 400:
        record_ingestion_attempt(
            conn,
            source_endpoint="events-radius",
            entity_key=entity_key,
            request_url=url,
            outcome="auth_blocked" if response.status_code in {401, 403} else "http_error",
            http_status=response.status_code,
        )
        response.raise_for_status()
    payload = response.json()
    sanitized, redacted_count = redact_discovery_payload(payload)
    observed_at = utc_now()
    source_payload_id = record_source_payload(
        conn,
        source_endpoint="events-radius",
        entity_key=entity_key,
        request_url=url,
        payload=sanitized,
        retrieved_at=observed_at,
        http_status=response.status_code,
    )
    record_ingestion_attempt(
        conn,
        source_endpoint="events-radius",
        entity_key=entity_key,
        request_url=url,
        outcome="success",
        http_status=response.status_code,
        source_payload_id=source_payload_id,
    )
    indexed = sum(
        _upsert_event(conn, row, bucket_id=bucket_id, observed_at=observed_at)
        for row in payload.get("data", [])
        if isinstance(row, dict)
    )
    conn.execute(
        """
        INSERT INTO event_discovery_searches(
            bucket_id, request_json, source_payload_id, event_count,
            redacted_field_count, searched_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            bucket_id,
            json.dumps(request_payload, sort_keys=True),
            source_payload_id,
            indexed,
            redacted_count,
            observed_at,
        ),
    )
    conn.commit()
    return {
        "source": "events-radius",
        "bucketId": bucket_id,
        "reportedEventCount": payload.get("event_count"),
        "indexedEventCount": indexed,
        "redactedFieldCount": redacted_count,
        "redaction": (
            "Sensitive response fields were replaced before provenance storage; "
            "they are not copied into discovered_events."
        ),
    }
