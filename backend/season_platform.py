from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from provenance import (
    initialize_provenance_schema,
    record_ingestion_attempt,
    record_source_payload,
)
from statistic_observations import (
    extract_statistic_observations,
    initialize_statistic_schema,
)
from baseline_predictions import initialize_prediction_schema
from shadow_predictions import initialize_shadow_schema
from upcoming_matchups import (
    create_due_shadow_predictions,
    ingest_schedule_matchups,
    initialize_upcoming_schema,
)
from event_discovery import initialize_event_discovery_schema, redact_discovery_payload
from outcome_ingestion import initialize_outcome_schema, ingest_completed_outcomes
from player_contact_directory import index_contact_payload
from data_integrity import (
    PARTIAL,
    QUARANTINED,
    READY,
    ensure_integrity_schema,
    inspect_match_payload,
    reconcile_normalized_game,
    record_game_integrity,
)


ACL_BASE = "https://api.iplayacl.com/api/v1"
_DB_SETUP_LOCK = threading.Lock()
_DB_SCHEMA_READY = False
ACL_AUTH_BASE = "https://api.iplayacl.com/api/auth/v1"
DATA_DIR = os.environ.get("DATA_DIR", "data")
PLATFORM_DIR = os.path.join(DATA_DIR, "season_platform")
RAW_DIR = os.path.join(PLATFORM_DIR, "raw")
DB_PATH = os.path.join(PLATFORM_DIR, "season_platform.db")
LIVE_PRIORITY_DIR = os.path.join(DATA_DIR, "live_priority")

AUTH_RETRY_STATUSES = {401, 403}

FANZONE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://fanzone.iplayacl.com",
    "referer": "https://fanzone.iplayacl.com/",
    "user-agent": "Mozilla/5.0",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)


def atomic_write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=os.path.dirname(path), encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        temp_path = tmp.name
    shutil.move(temp_path, path)


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def is_complete_status(value: Any) -> bool:
    status = str(value or "").strip().upper()
    return status in {"C", "COMPLETE", "COMPLETED"} or "COMPLETE" in status


def bracket_completed(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    event_info = payload.get("eventInfo") or {}
    if any(is_complete_status(event_info.get(k)) for k in ("leagueStatus", "leagueStatusDesc", "status")):
        return True
    statuses = [
        row.get("matchStatusID")
        for row in payload.get("bracketDetails", []) or []
        if isinstance(row, dict) and row.get("bracketmatchid") not in (None, "")
    ]
    return bool(statuses) and all(str(status) == "5" for status in statuses)


def match_stats_completed(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return payload.get("matchStatus") == 5 or is_complete_status(payload.get("matchStatusDesc"))


def schedule_completed(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    rows = data.get("overAllSchedule") or []
    return bool(rows) and all(
        str(row.get("matchStatusID")) == "5"
        for row in rows
        if isinstance(row, dict)
    )


def cache_path(*parts: str) -> str:
    safe = [str(part).replace("/", "_").replace("\\", "_").replace(":", "_") for part in parts]
    return os.path.join(RAW_DIR, *safe)


def payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def db() -> sqlite3.Connection:
    global _DB_SCHEMA_READY
    ensure_dirs()
    # Live forecasts and live-game writes are user-facing and time-sensitive.
    # Background workers yield before opening their next database transaction
    # whenever a web process has reserved the SQLite writer lane.
    if os.environ.get("PROCESS_ROLE", "web").strip().lower() == "background":
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                active = [
                    path for path in Path(LIVE_PRIORITY_DIR).glob("*.lock")
                    if time.time() - path.stat().st_mtime < 300
                ]
            except OSError:
                active = []
            if not active:
                break
            time.sleep(0.5)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    if not _DB_SCHEMA_READY:
        with _DB_SETUP_LOCK:
            if not _DB_SCHEMA_READY:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                init_db(conn)
                _DB_SCHEMA_READY = True
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_cache (
            cache_key TEXT PRIMARY KEY,
            source_endpoint TEXT NOT NULL,
            url TEXT NOT NULL,
            local_path TEXT NOT NULL,
            status_code INTEGER,
            etag TEXT,
            acl_response_date TEXT,
            fetched_at TEXT,
            completion_status TEXT,
            payload_hash TEXT
        );

        CREATE TABLE IF NOT EXISTS api_manifest (
            manifest_key TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            source_endpoint TEXT NOT NULL,
            local_path TEXT,
            last_checked TEXT,
            completion_status TEXT,
            metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            display_name TEXT,
            state TEXT,
            city TEXT,
            profile_image TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS player_profiles (
            player_id INTEGER PRIMARY KEY,
            profile_json TEXT NOT NULL,
            fetched_at TEXT,
            FOREIGN KEY(player_id) REFERENCES players(player_id)
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY,
            event_name TEXT,
            event_date TEXT,
            status TEXT,
            location_id TEXT,
            location_name TEXT,
            location_city TEXT,
            location_state TEXT,
            match_type TEXT,
            bracket_type TEXT,
            blind_draw INTEGER,
            event_type TEXT,
            event_sub_type TEXT,
            bucket_id INTEGER,
            bracket_downloaded INTEGER DEFAULT 0,
            bracket_completed INTEGER DEFAULT 0,
            match_stats_targets INTEGER DEFAULT 0,
            match_stats_downloaded INTEGER DEFAULT 0,
            last_checked TEXT
        );

        CREATE TABLE IF NOT EXISTS teams (
            team_id TEXT PRIMARY KEY,
            event_id INTEGER,
            team_name TEXT,
            FOREIGN KEY(event_id) REFERENCES events(event_id)
        );

        CREATE TABLE IF NOT EXISTS team_members (
            team_id TEXT,
            player_id INTEGER,
            event_id INTEGER,
            PRIMARY KEY(team_id, player_id, event_id)
        );

        CREATE TABLE IF NOT EXISTS matches (
            event_id INTEGER,
            match_id TEXT,
            court_id TEXT,
            round_desc TEXT,
            bracket_side TEXT,
            status_id INTEGER,
            PRIMARY KEY(event_id, match_id)
        );

        CREATE TABLE IF NOT EXISTS games (
            event_id INTEGER,
            match_id TEXT,
            game_id INTEGER,
            status_id INTEGER,
            home_team_id TEXT,
            away_team_id TEXT,
            home_score INTEGER,
            away_score INTEGER,
            completed INTEGER DEFAULT 0,
            stats_downloaded INTEGER DEFAULT 0,
            PRIMARY KEY(event_id, match_id, game_id)
        );

        CREATE TABLE IF NOT EXISTS rounds (
            event_id INTEGER,
            match_id TEXT,
            game_id INTEGER,
            round_no INTEGER,
            scoring_team_id TEXT,
            net_points INTEGER,
            PRIMARY KEY(event_id, match_id, game_id, round_no)
        );

        CREATE TABLE IF NOT EXISTS player_rounds (
            event_id INTEGER,
            match_id TEXT,
            game_id INTEGER,
            round_no INTEGER,
            player_id INTEGER,
            player_name TEXT,
            team_id TEXT,
            opponent_player_id INTEGER,
            opponent_team_id TEXT,
            team_side TEXT,
            court_id TEXT,
            gross_points INTEGER,
            opponent_points INTEGER,
            net_points INTEGER,
            scored_points INTEGER,
            bags_in INTEGER,
            bags_on INTEGER,
            bags_off INTEGER,
            four_bagger INTEGER,
            round_result TEXT,
            event_date TEXT,
            location_id TEXT,
            location_name TEXT,
            match_type TEXT,
            bracket_type TEXT,
            blind_draw INTEGER,
            PRIMARY KEY(event_id, match_id, game_id, round_no, player_id)
        );

        CREATE TABLE IF NOT EXISTS event_results (
            event_id INTEGER,
            player_id INTEGER,
            place INTEGER,
            points REAL,
            team_id TEXT,
            team_name TEXT,
            wins INTEGER,
            losses INTEGER,
            player_ppr REAL,
            PRIMARY KEY(event_id, player_id, team_id)
        );

        CREATE TABLE IF NOT EXISTS swap_standings (
            event_id INTEGER,
            player_id INTEGER,
            player_name TEXT,
            city TEXT,
            state TEXT,
            player_group TEXT,
            checked_in TEXT,
            skill_level TEXT,
            player_ppr REAL,
            player_cpi REAL,
            partner_history_json TEXT,
            wins INTEGER,
            losses INTEGER,
            differential_points INTEGER,
            total_points INTEGER,
            rank INTEGER,
            finish_points REAL,
            updated_at TEXT,
            PRIMARY KEY(event_id, player_id)
        );

        CREATE TABLE IF NOT EXISTS swap_up_next (
            event_id INTEGER,
            player_id INTEGER,
            player_name TEXT,
            city TEXT,
            state TEXT,
            player_group TEXT,
            checked_in TEXT,
            skill_level TEXT,
            player_ppr REAL,
            player_cpi REAL,
            partner_history_json TEXT,
            wins INTEGER,
            losses INTEGER,
            differential_points INTEGER,
            total_points INTEGER,
            rank INTEGER,
            fetched_at TEXT,
            PRIMARY KEY(event_id, player_id)
        );
        """
    )
    ensure_column(conn, "games", "home_team_id", "TEXT")
    ensure_column(conn, "games", "away_team_id", "TEXT")
    ensure_column(conn, "player_rounds", "team_side", "TEXT")
    ensure_column(conn, "events", "location_country", "TEXT")
    ensure_column(conn, "events", "location_lat", "REAL")
    ensure_column(conn, "events", "location_lng", "REAL")
    ensure_column(conn, "events", "event_group", "TEXT")
    ensure_column(conn, "events", "event_group_basis", "TEXT")
    ensure_column(conn, "players", "skill_level", "TEXT")
    ensure_column(conn, "players", "skill_level_source", "TEXT")
    ensure_column(conn, "players", "is_pro", "INTEGER")
    ensure_column(conn, "players", "pro_classification_source", "TEXT")
    ensure_column(conn, "players", "pro_observed_at", "TEXT")
    ensure_column(conn, "players", "membership_name", "TEXT")
    ensure_column(conn, "players", "membership_type", "TEXT")
    ensure_column(conn, "players", "membership_source", "TEXT")
    ensure_column(conn, "players", "membership_observed_at", "TEXT")
    conn.execute(
        """
        UPDATE events
        SET event_group='SIT_AND_GO', event_group_basis='EVENT_NAME'
        WHERE LOWER(REPLACE(REPLACE(REPLACE(COALESCE(event_name, ''), ' ', ''), '&', 'and'), '''', ''))
              LIKE '%sitandgo%'
           OR LOWER(REPLACE(REPLACE(COALESCE(event_name, ''), ' ', ''), '''', ''))
              LIKE '%sitngo%'
        """
    )
    conn.execute(
        """
        UPDATE events
        SET event_group=COALESCE(event_group, 'STANDARD'),
            event_group_basis=COALESCE(event_group_basis, 'DEFAULT')
        """
    )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_player_rounds_player_date
            ON player_rounds(player_id, event_date);
        CREATE INDEX IF NOT EXISTS idx_player_rounds_game
            ON player_rounds(event_id, match_id, game_id);
        CREATE INDEX IF NOT EXISTS idx_player_rounds_location_date
            ON player_rounds(location_id, event_date);
        CREATE INDEX IF NOT EXISTS idx_team_members_player_event
            ON team_members(player_id, event_id);
        CREATE INDEX IF NOT EXISTS idx_games_event_teams
            ON games(event_id, home_team_id, away_team_id);
        CREATE INDEX IF NOT EXISTS idx_events_date
            ON events(event_date);
        """
    )
    initialize_provenance_schema(conn)
    initialize_statistic_schema(conn)
    initialize_prediction_schema(conn)
    initialize_shadow_schema(conn)
    initialize_upcoming_schema(conn)
    initialize_event_discovery_schema(conn)
    initialize_outcome_schema(conn)
    ensure_integrity_schema(conn)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingestion_attempts_endpoint_entity
        ON ingestion_attempts(source_endpoint, entity_key, ingestion_attempt_id)
        """
    )
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def upsert_api_cache(
    conn: sqlite3.Connection,
    *,
    cache_key: str,
    source_endpoint: str,
    url: str,
    local_path: str,
    status_code: int | None,
    etag: str | None,
    acl_response_date: str | None,
    fetched_at: str | None,
    completion_status: str,
    payload: Any,
) -> None:
    conn.execute(
        """
        INSERT INTO api_cache (
            cache_key, source_endpoint, url, local_path, status_code, etag,
            acl_response_date, fetched_at, completion_status, payload_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            source_endpoint=excluded.source_endpoint,
            url=excluded.url,
            local_path=excluded.local_path,
            status_code=excluded.status_code,
            etag=excluded.etag,
            acl_response_date=excluded.acl_response_date,
            fetched_at=excluded.fetched_at,
            completion_status=excluded.completion_status,
            payload_hash=excluded.payload_hash
        """,
        (
            cache_key,
            source_endpoint,
            url,
            local_path,
            status_code,
            etag,
            acl_response_date,
            fetched_at,
            completion_status,
            payload_hash(payload),
        ),
    )
    conn.commit()


def upsert_manifest(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    source_endpoint: str,
    local_path: str | None,
    completion_status: str,
    metadata: dict[str, Any],
) -> None:
    manifest_key = f"{entity_type}:{entity_id}:{source_endpoint}"
    conn.execute(
        """
        INSERT INTO api_manifest (
            manifest_key, entity_type, entity_id, source_endpoint, local_path,
            last_checked, completion_status, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(manifest_key) DO UPDATE SET
            local_path=excluded.local_path,
            last_checked=excluded.last_checked,
            completion_status=excluded.completion_status,
            metadata_json=excluded.metadata_json
        """,
        (
            manifest_key,
            entity_type,
            str(entity_id),
            source_endpoint,
            local_path,
            utc_now(),
            completion_status,
            json.dumps(metadata, sort_keys=True, default=str),
        ),
    )
    conn.commit()


def cached_get(
    conn: sqlite3.Connection,
    *,
    cache_key: str,
    url: str,
    source_endpoint: str,
    local_path: str,
    headers: dict[str, str] | None = None,
    force: bool = False,
    reuse_if_cached: bool = False,
    completion_checker=None,
    payload_sanitizer=None,
    payload_before_sanitize=None,
) -> tuple[Any, dict[str, Any]]:
    cached = read_json(local_path)
    cached_payload = (cached or {}).get("payload") if isinstance(cached, dict) else None
    if cached_payload is not None and payload_sanitizer:
        cached_payload = payload_sanitizer(cached_payload)
    cached_meta = (cached or {}).get("meta", {}) if isinstance(cached, dict) else {}
    cached_status = cached_meta.get("completionStatus")

    if cached_payload is not None and not force and (reuse_if_cached or cached_status == "complete"):
        source_payload_id = record_source_payload(
            conn,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            request_url=url,
            payload=cached_payload,
            retrieved_at=cached_meta.get("fetchedAt"),
            http_status=cached_meta.get("statusCode"),
            local_path=local_path,
        )
        record_ingestion_attempt(
            conn,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            request_url=url,
            outcome="cache_hit",
            http_status=cached_meta.get("statusCode"),
            source_payload_id=source_payload_id,
        )
        extract_statistic_observations(
            conn,
            source_payload_id=source_payload_id,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            payload=cached_payload,
            retrieved_at=cached_meta.get("fetchedAt") or utc_now(),
        )
        return cached_payload, {"source": "cache", **cached_meta}

    request_headers = dict(headers or FANZONE_HEADERS)
    if cached_meta.get("etag") and not force:
        request_headers["if-none-match"] = cached_meta["etag"]

    try:
        response = requests.get(url, headers=request_headers, timeout=30)
    except requests.RequestException as exc:
        record_ingestion_attempt(
            conn,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            request_url=url,
            outcome="network_error",
            error_kind=type(exc).__name__,
            error_message=str(exc),
        )
        raise

    if response.status_code == 304 and cached_payload is not None:
        meta = {**cached_meta, "source": "not_modified", "lastChecked": utc_now()}
        upsert_api_cache(
            conn,
            cache_key=cache_key,
            source_endpoint=source_endpoint,
            url=url,
            local_path=local_path,
            status_code=304,
            etag=cached_meta.get("etag"),
            acl_response_date=cached_meta.get("aclResponseDate"),
            fetched_at=cached_meta.get("fetchedAt"),
            completion_status=cached_status or "incomplete",
            payload=cached_payload,
        )
        source_payload_id = record_source_payload(
            conn,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            request_url=url,
            payload=cached_payload,
            retrieved_at=cached_meta.get("fetchedAt"),
            http_status=304,
            local_path=local_path,
        )
        record_ingestion_attempt(
            conn,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            request_url=url,
            outcome="not_modified",
            http_status=304,
            source_payload_id=source_payload_id,
        )
        extract_statistic_observations(
            conn,
            source_payload_id=source_payload_id,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            payload=cached_payload,
            retrieved_at=cached_meta.get("fetchedAt") or utc_now(),
        )
        return cached_payload, meta

    if response.status_code >= 400:
        record_ingestion_attempt(
            conn,
            source_endpoint=source_endpoint,
            entity_key=cache_key,
            request_url=url,
            outcome="auth_blocked" if response.status_code in AUTH_RETRY_STATUSES else "http_error",
            http_status=response.status_code,
            error_kind="HTTPError",
            error_message=f"HTTP {response.status_code}",
        )
        response.raise_for_status()
    payload = response.json()
    if payload_before_sanitize:
        payload_before_sanitize(payload)
    if payload_sanitizer:
        payload = payload_sanitizer(payload)
    completion_status = "complete" if completion_checker and completion_checker(payload) else "incomplete"
    meta = {
        "fetchedAt": utc_now(),
        "aclResponseDate": response.headers.get("date"),
        "etag": response.headers.get("etag"),
        "completionStatus": completion_status,
        "sourceEndpoint": source_endpoint,
        "url": url,
        "statusCode": response.status_code,
    }
    atomic_write_json(local_path, {"meta": meta, "payload": payload})
    upsert_api_cache(
        conn,
        cache_key=cache_key,
        source_endpoint=source_endpoint,
        url=url,
        local_path=local_path,
        status_code=response.status_code,
        etag=meta["etag"],
        acl_response_date=meta["aclResponseDate"],
        fetched_at=meta["fetchedAt"],
        completion_status=completion_status,
        payload=payload,
    )
    source_payload_id = record_source_payload(
        conn,
        source_endpoint=source_endpoint,
        entity_key=cache_key,
        request_url=url,
        payload=payload,
        retrieved_at=meta["fetchedAt"],
        http_status=response.status_code,
        local_path=local_path,
    )
    record_ingestion_attempt(
        conn,
        source_endpoint=source_endpoint,
        entity_key=cache_key,
        request_url=url,
        outcome="success",
        http_status=response.status_code,
        source_payload_id=source_payload_id,
    )
    extract_statistic_observations(
        conn,
        source_payload_id=source_payload_id,
        source_endpoint=source_endpoint,
        entity_key=cache_key,
        payload=payload,
        retrieved_at=meta["fetchedAt"],
    )
    return payload, {"source": "network", **meta}


def display_name(first: Any, last: Any) -> str:
    return f"{first or ''} {last or ''}".strip()


def sanitize_profile(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    return {
        "playerID": data.get("playerID") or data.get("playerId") or data.get("id"),
        "firstName": data.get("firstName") or data.get("playerFirstName"),
        "lastName": data.get("lastName") or data.get("playerLastName"),
        "profileImage": data.get("profileImage") or data.get("playerPhoto") or data.get("playerImage"),
        "city": data.get("city") or data.get("playerCity"),
        "state": data.get("state") or data.get("playerState"),
        "skillLevelDesc": data.get("skillLevelDesc"),
        "playerPPR": data.get("playerPPR"),
        "playerCPI": data.get("playerCPI"),
        "cPITimeStamp": data.get("cPITimeStamp"),
        "conferenceName": data.get("conferenceName"),
        "playerMembershipName": data.get("playerMembershipName"),
        "playerMembershipType": data.get("playerMembershipType"),
        "_membershipSource": "authenticated-player-profile",
        "bucketDesc": data.get("bucketDesc"),
    }


def upsert_player(conn: sqlite3.Connection, player: dict[str, Any]) -> None:
    player_id = player.get("playerID") or player.get("playerId") or player.get("playerid")
    if not player_id:
        return
    first = player.get("firstName") or player.get("firstname") or player.get("playerfirstname")
    last = player.get("lastName") or player.get("lastname") or player.get("playerlastname")
    explicit_skill = (
        player.get("skillLevel")
        or player.get("skillLevelDesc")
        or player.get("playerSkillLevel")
    )
    is_pro = (
        1 if str(explicit_skill or "").strip().upper() == "PRO"
        else 0 if explicit_skill not in (None, "")
        else None
    )
    classification_source = player.get("_classificationSource")
    membership_name = player.get("playerMembershipName")
    membership_type = player.get("playerMembershipType")
    membership_source = player.get("_membershipSource") or (
        classification_source
        if membership_name not in (None, "") or membership_type not in (None, "")
        else None
    )
    conn.execute(
        """
        INSERT INTO players (
            player_id, first_name, last_name, display_name, state, city,
            profile_image, skill_level, skill_level_source, is_pro,
            pro_classification_source, pro_observed_at,
            membership_name, membership_type, membership_source,
            membership_observed_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            first_name=COALESCE(excluded.first_name, players.first_name),
            last_name=COALESCE(excluded.last_name, players.last_name),
            display_name=COALESCE(excluded.display_name, players.display_name),
            state=COALESCE(excluded.state, players.state),
            city=COALESCE(excluded.city, players.city),
            profile_image=COALESCE(excluded.profile_image, players.profile_image),
            skill_level=COALESCE(excluded.skill_level, players.skill_level),
            skill_level_source=COALESCE(excluded.skill_level_source, players.skill_level_source),
            is_pro=COALESCE(excluded.is_pro, players.is_pro),
            pro_classification_source=COALESCE(
                excluded.pro_classification_source,
                players.pro_classification_source
            ),
            pro_observed_at=CASE
                WHEN excluded.is_pro IS NOT NULL THEN excluded.pro_observed_at
                ELSE players.pro_observed_at
            END,
            membership_name=COALESCE(excluded.membership_name, players.membership_name),
            membership_type=COALESCE(excluded.membership_type, players.membership_type),
            membership_source=COALESCE(excluded.membership_source, players.membership_source),
            membership_observed_at=CASE
                WHEN excluded.membership_name IS NOT NULL
                  OR excluded.membership_type IS NOT NULL
                THEN excluded.membership_observed_at
                ELSE players.membership_observed_at
            END,
            updated_at=excluded.updated_at
        """,
        (
            int(player_id),
            first,
            last,
            display_name(first, last) or player.get("name"),
            player.get("state") or player.get("playerstate"),
            player.get("city") or player.get("playercity"),
            player.get("profileImage") or player.get("photoimage") or player.get("playerimage"),
            explicit_skill,
            classification_source,
            is_pro,
            classification_source if is_pro is not None else None,
            utc_now() if is_pro is not None else None,
            membership_name,
            membership_type,
            membership_source,
            (
                utc_now()
                if membership_name not in (None, "") or membership_type not in (None, "")
                else None
            ),
            utc_now(),
        ),
    )
    conn.commit()


def fetch_event_player_classifications(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Persist ACL's public skillLevel classification for an event roster."""
    path = cache_path("event_player_stats", f"event_{event_id}.json")
    url = f"{ACL_BASE}/event-player-stats/{event_id}"
    payload, meta = cached_get(
        conn,
        cache_key=f"event-player-stats:{event_id}",
        url=url,
        source_endpoint="event-player-stats",
        local_path=path,
        headers={
            **FANZONE_HEADERS,
            "origin": "https://app.iplayacl.com",
            "referer": "https://app.iplayacl.com/",
            "x-app-version": "14.1.0",
        },
        force=force,
        reuse_if_cached=True,
    )
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    pro_ids: list[int] = []
    classified = 0
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("playerID") in (None, ""):
            continue
        skill_level = row.get("skillLevel") or row.get("playerSkillLevel")
        upsert_player(
            conn,
            {
                **row,
                "firstName": row.get("playerFirstName"),
                "lastName": row.get("playerLastName"),
                "skillLevel": skill_level,
                "_classificationSource": "event-player-stats.skillLevel",
            },
        )
        if skill_level not in (None, ""):
            classified += 1
        if str(skill_level or "").strip().upper() == "PRO":
            pro_ids.append(int(row["playerID"]))
    return {
        "eventId": int(event_id),
        "players": len(rows),
        "classified": classified,
        "proPlayers": len(pro_ids),
        "proPlayerIds": sorted(set(pro_ids)),
        "source": meta.get("source"),
        "networkRequests": 0 if meta.get("source") == "cache" else 1,
    }


def fetch_player_profile(conn: sqlite3.Connection, player_id: int, *, force: bool = False) -> dict[str, Any] | None:
    path = cache_path("profiles", f"player_{player_id}.json")
    url = f"{ACL_AUTH_BASE}/players/{player_id}?dw=false&nd=true&dwt=true"
    raw, _ = cached_get(
        conn,
        cache_key=f"profile:{player_id}",
        url=url,
        source_endpoint="player-profile",
        local_path=path,
        headers=FANZONE_HEADERS,
        force=force,
        reuse_if_cached=True,
    )
    profile = sanitize_profile(raw)
    if not profile.get("playerID"):
        return None
    upsert_player(conn, profile)
    conn.execute(
        """
        INSERT INTO player_profiles (player_id, profile_json, fetched_at)
        VALUES (?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            profile_json=excluded.profile_json,
            fetched_at=excluded.fetched_at
        """,
        (int(profile["playerID"]), json.dumps(profile, sort_keys=True), utc_now()),
    )
    conn.commit()
    return profile


def parse_player_event(row: dict[str, Any], bucket_id: int) -> dict[str, Any]:
    return {
        "eventId": int(row.get("leagueID") or row.get("eventID") or row.get("eventId")),
        "eventName": row.get("leagueName") or row.get("eventName") or row.get("name"),
        "date": row.get("leaguestartdate") or row.get("leagueStartDate") or row.get("startdate") or row.get("date"),
        "status": row.get("leagueStatus") or row.get("status"),
        "locationId": row.get("leagueLocationID") or row.get("locationId"),
        "locationName": row.get("leagueLocationName") or row.get("locationName"),
        "locationCity": row.get("locationCity"),
        "locationState": row.get("locationState"),
        "locationCountry": row.get("countryCode") or row.get("locationCountry"),
        "locationLat": row.get("locationLat") or row.get("mapLat"),
        "locationLng": row.get("locationLng") or row.get("mapLng"),
        "matchType": row.get("matchType") or row.get("matchtype"),
        "bracketType": row.get("bracketType") or row.get("brackettype"),
        "blindDraw": 1 if row.get("blindDraw") else 0,
        "eventType": row.get("eventType") or row.get("eventtype"),
        "eventSubType": row.get("eventSubType") or row.get("eventsubtype"),
        "bucketId": bucket_id,
        "raw": row,
    }


def fetch_player_events(
    conn: sqlite3.Connection,
    player_id: int,
    bucket_id: int,
    *,
    force: bool = False,
    refresh_index: bool = False,
    statuses: Iterable[str] = ("ACTIVE", "COMPLETED"),
    include_metadata: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    request_metadata: list[dict[str, Any]] = []
    for status in statuses:
        path = cache_path("player_events", f"player_{player_id}_bucket_{bucket_id}_{status}.json")
        url = f"{ACL_BASE}/player-events-grouped/{player_id}?bucket_id={bucket_id}&eventStatus={status}"
        payload, meta = cached_get(
            conn,
            cache_key=f"player-events:{player_id}:{bucket_id}:{status}",
            url=url,
            source_endpoint="player-events-grouped",
            local_path=path,
            headers=FANZONE_HEADERS,
            force=force or refresh_index,
            reuse_if_cached=not refresh_index,
        )
        request_metadata.append(meta)
        rows = payload.get("eventsGrouped") or payload.get("events") or payload.get("data") or []
        upsert_manifest(
            conn,
            entity_type="player",
            entity_id=str(player_id),
            source_endpoint=f"player-events-grouped:{status}",
            local_path=path,
            completion_status=meta.get("completionStatus", "index"),
            metadata={"bucketId": bucket_id, "status": status, "count": len(rows)},
        )
        events.extend(parse_player_event(row, bucket_id) for row in rows if row.get("leagueID") or row.get("eventID") or row.get("eventId"))

    deduped: dict[int, dict[str, Any]] = {}
    for event in events:
        deduped[event["eventId"]] = event
        upsert_event(conn, event)
    result = sorted(deduped.values(), key=lambda e: e.get("date") or "")
    return (result, request_metadata) if include_metadata else result


def upsert_event(conn: sqlite3.Connection, event: dict[str, Any], *, bracket_downloaded: bool | None = None, bracket_is_complete: bool | None = None) -> None:
    compact_name = "".join(
        character
        for character in str(event.get("eventName") or "").lower()
        if character.isalnum()
    )
    event_group = (
        "SIT_AND_GO"
        if "sitandgo" in compact_name or "sitngo" in compact_name
        else "STANDARD"
    )
    event_group_basis = "EVENT_NAME" if event_group == "SIT_AND_GO" else "DEFAULT"
    conn.execute(
        """
        INSERT INTO events (
            event_id, event_name, event_date, status, location_id, location_name,
            location_city, location_state, location_country, location_lat,
            location_lng, match_type, bracket_type, blind_draw,
            event_type, event_sub_type, bucket_id, event_group, event_group_basis,
            bracket_downloaded, bracket_completed, last_checked
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            event_name=COALESCE(excluded.event_name, events.event_name),
            event_date=COALESCE(excluded.event_date, events.event_date),
            status=COALESCE(excluded.status, events.status),
            location_id=COALESCE(excluded.location_id, events.location_id),
            location_name=COALESCE(excluded.location_name, events.location_name),
            location_city=COALESCE(excluded.location_city, events.location_city),
            location_state=COALESCE(excluded.location_state, events.location_state),
            location_country=COALESCE(excluded.location_country, events.location_country),
            location_lat=COALESCE(excluded.location_lat, events.location_lat),
            location_lng=COALESCE(excluded.location_lng, events.location_lng),
            match_type=COALESCE(excluded.match_type, events.match_type),
            bracket_type=COALESCE(excluded.bracket_type, events.bracket_type),
            blind_draw=COALESCE(excluded.blind_draw, events.blind_draw),
            event_type=COALESCE(excluded.event_type, events.event_type),
            event_sub_type=COALESCE(excluded.event_sub_type, events.event_sub_type),
            bucket_id=COALESCE(excluded.bucket_id, events.bucket_id),
            event_group=excluded.event_group,
            event_group_basis=excluded.event_group_basis,
            bracket_downloaded=CASE WHEN excluded.bracket_downloaded IS NULL THEN events.bracket_downloaded ELSE excluded.bracket_downloaded END,
            bracket_completed=CASE WHEN excluded.bracket_completed IS NULL THEN events.bracket_completed ELSE excluded.bracket_completed END,
            last_checked=excluded.last_checked
        """,
        (
            event.get("eventId"),
            event.get("eventName"),
            event.get("date"),
            event.get("status"),
            event.get("locationId"),
            event.get("locationName"),
            event.get("locationCity"),
            event.get("locationState"),
            event.get("locationCountry"),
            event.get("locationLat"),
            event.get("locationLng"),
            event.get("matchType"),
            event.get("bracketType"),
            event.get("blindDraw"),
            event.get("eventType"),
            event.get("eventSubType"),
            event.get("bucketId"),
            event_group,
            event_group_basis,
            int(bracket_downloaded) if bracket_downloaded is not None else None,
            int(bracket_is_complete) if bracket_is_complete is not None else None,
            utc_now(),
        ),
    )
    conn.commit()


def event_from_bracket(payload: dict[str, Any], fallback_event_id: int | None = None) -> dict[str, Any]:
    info = payload.get("eventInfo") or {} if isinstance(payload, dict) else {}
    event_id = info.get("eventID") or info.get("leagueID") or fallback_event_id
    if event_id in (None, ""):
        raise ValueError("Bracket payload did not include an event id")
    return {
        "eventId": int(event_id),
        "eventName": info.get("eventName") or info.get("leagueName") or info.get("leaguename"),
        "date": info.get("startdate") or info.get("leagueStartDate") or info.get("leaguestartdate"),
        "status": info.get("leagueStatus") or info.get("status"),
        "locationId": info.get("leagueLocationID"),
        "locationName": info.get("leagueLocationName") or info.get("locationName"),
        "locationCity": info.get("locationCity"),
        "locationState": info.get("locationState"),
        "locationCountry": info.get("countryCode") or info.get("locationCountry"),
        "locationLat": info.get("locationLat") or info.get("mapLat"),
        "locationLng": info.get("locationLng") or info.get("mapLng"),
        "matchType": info.get("matchType") or info.get("matchtype"),
        "bracketType": info.get("bracketType") or info.get("brackettype"),
        "blindDraw": 1 if info.get("blindDraw") else 0,
        "eventType": info.get("eventType") or info.get("eventtype"),
        "eventSubType": info.get("eventSubType") or info.get("eventsubtype"),
        "bucketId": info.get("bucketID") or info.get("eventBucketID"),
    }


def fetch_bracket(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    force: bool = False,
    preserve_contact_data: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = cache_path("brackets", f"event_{event_id}.json")
    url = f"{ACL_BASE}/bracket-data/{event_id}"

    def capture_private_director_fields(raw_payload: Any) -> None:
        try:
            from director_directory import index_director_event_payload

            index_director_event_payload(conn, raw_payload, fallback_event_id=event_id)
        except Exception:
            # Private contact capture must never block bracket ingestion.
            pass

    payload, meta = cached_get(
        conn,
        cache_key=f"bracket:{event_id}",
        url=url,
        source_endpoint="bracket-data",
        local_path=path,
        headers=FANZONE_HEADERS,
        force=force,
        completion_checker=bracket_completed,
        payload_sanitizer=(
            None
            if preserve_contact_data
            else lambda value: redact_discovery_payload(value)[0]
        ),
        payload_before_sanitize=capture_private_director_fields,
    )
    event = event_from_bracket(payload, fallback_event_id=event_id)
    upsert_event(conn, event, bracket_downloaded=True, bracket_is_complete=bracket_completed(payload))
    try:
        from director_directory import index_director_event_payload

        index_director_event_payload(
            conn,
            payload,
            source_payload_id=meta.get("sourcePayloadId"),
            fallback_event_id=event_id,
        )
    except Exception:
        # Private director indexing must never block bracket availability.
        pass
    if bracket_completed(payload):
        try:
            from double_dip_analysis import analyze_double_elimination_final, store_double_dip_records
            record = analyze_double_elimination_final(payload)
            if record:
                store_double_dip_records(conn, [record])
        except Exception:
            # Double-dip analytics must never prevent the underlying ACL bracket
            # from being cached and normalized.
            pass
    upsert_manifest(
        conn,
        entity_type="event",
        entity_id=str(event_id),
        source_endpoint="bracket-data",
        local_path=path,
        completion_status="complete" if bracket_completed(payload) else "incomplete",
        metadata={"eventName": event.get("eventName"), "date": event.get("date")},
    )
    return payload, meta


SCHEDULE_ENDPOINTS = {
    "SWISS": "swiss-pairing-schedule-breakdown",
    "SWAP": "swap-schedule-breakdown",
}


def fetch_and_index_upcoming_schedule(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    schedule_format: str,
    source_timezone: str | None,
    force: bool = False,
    create_due: bool = True,
    lookahead_minutes: int = 180,
    event_start_at: str | None = None,
) -> dict[str, Any]:
    normalized_format = schedule_format.strip().upper()
    endpoint = SCHEDULE_ENDPOINTS.get(normalized_format)
    if endpoint is None:
        raise ValueError("schedule_format must be SWISS or SWAP")
    path = cache_path("schedules", f"{endpoint}_{event_id}.json")
    url = f"{ACL_BASE}/{endpoint}/{event_id}"

    def capture_private_player_fields(raw_payload: Any) -> None:
        try:
            from player_contact_directory import index_contact_payload

            index_contact_payload(
                conn,
                raw_payload,
                source_endpoint=endpoint,
                source_event_id=event_id,
                source_file=str(path),
            )
        except Exception:
            # Private contact capture must never block schedule ingestion.
            pass

    payload, meta = cached_get(
        conn,
        cache_key=f"schedule:{endpoint}:{event_id}",
        url=url,
        source_endpoint=endpoint,
        local_path=path,
        headers=FANZONE_HEADERS,
        force=force,
        completion_checker=schedule_completed,
        payload_sanitizer=lambda value: redact_discovery_payload(value)[0],
        payload_before_sanitize=capture_private_player_fields,
    )
    # Contact fields are private, but the same schedule response can enrich the
    # admin-only directory without another ACL request.
    try:
        from player_contact_directory import index_contact_payload

        index_contact_payload(
            conn,
            payload,
            source_endpoint=endpoint,
            source_event_id=event_id,
            source_file=str(path),
        )
    except Exception:
        # Contact enrichment must never block live schedule ingestion.
        pass
    ingestion = ingest_schedule_matchups(
        conn,
        event_id=event_id,
        payload=payload,
        source_endpoint=endpoint,
        format_name=normalized_format,
        source_timezone=source_timezone,
        event_start_at=event_start_at,
    )
    # The schedule-breakdown response is also the authoritative result feed
    # for both SWAP and SWISS/rounders events.  Previously only the separate
    # SWAP "schedule all" path resolved predictions, leaving completed
    # rounders matches permanently marked as awaiting a result.
    outcomes = ingest_completed_outcomes(
        conn,
        event_id=event_id,
        payload=payload,
        source_endpoint=endpoint,
        source_payload_id=meta.get("sourcePayloadId"),
    )
    due = (
        create_due_shadow_predictions(
            conn,
            lookahead_minutes=lookahead_minutes,
        )
        if create_due
        else None
    )
    return {
        "eventId": event_id,
        "format": normalized_format,
        "endpoint": endpoint,
        "source": meta.get("source"),
        "ingestion": ingestion,
        "outcomes": outcomes,
        "shadowCreation": due,
    }


def team_id(event_id: int, raw_team_id: Any) -> str:
    return f"{event_id}:{raw_team_id}"


def upsert_team(conn: sqlite3.Connection, event_id: int, entry: dict[str, Any]) -> None:
    raw_team_id = entry.get("bracketteamid") or entry.get("teamid")
    if raw_team_id in (None, ""):
        return
    tid = team_id(event_id, raw_team_id)
    conn.execute(
        """
        INSERT INTO teams (team_id, event_id, team_name)
        VALUES (?, ?, ?)
        ON CONFLICT(team_id) DO UPDATE SET team_name=excluded.team_name
        """,
        (tid, event_id, entry.get("bracketteamname") or entry.get("teamname")),
    )
    for player in entry.get("player_info", []) or []:
        pid = player.get("playerid")
        if not pid:
            continue
        upsert_player(
            conn,
            {
                "playerID": pid,
                "firstName": player.get("firstname"),
                "lastName": player.get("lastname"),
                "profileImage": player.get("photoimage"),
            },
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO team_members (team_id, player_id, event_id)
            VALUES (?, ?, ?)
            """,
            (tid, int(pid), event_id),
        )
    conn.commit()


def grouped_matches(bracket: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in bracket.get("bracketDetails", []) or []:
        if not isinstance(entry, dict):
            continue
        match_id = entry.get("bracketmatchid")
        if match_id not in (None, ""):
            groups[str(match_id)].append(entry)
    return groups


def match_has_player(pair: list[dict[str, Any]], player_ids: set[int]) -> bool:
    for entry in pair:
        for player in entry.get("player_info", []) or []:
            try:
                if int(player.get("playerid")) in player_ids:
                    return True
            except Exception:
                continue
    return False


def match_is_bye(pair: list[dict[str, Any]]) -> bool:
    for entry in pair:
        names = [
            entry.get("bracketteamname"),
            entry.get("teamname"),
            *[
                " ".join(filter(None, [player.get("firstname"), player.get("lastname")]))
                for player in (entry.get("player_info") or [])
            ],
        ]
        if any(
            str(name or "").strip().lower() == "bye"
            or str(name or "").strip().lower().startswith("bye user")
            for name in names
        ):
            return True
    return False


def game_targets_for_match(event_id: int, pair: list[dict[str, Any]]) -> list[dict[str, Any]]:
    top = next((entry for entry in pair if "T" in str(entry.get("bracketpos", ""))), pair[0] if pair else {})
    bottom = next((entry for entry in pair if "B" in str(entry.get("bracketpos", ""))), {})
    home_team_id = team_id(event_id, top.get("bracketteamid")) if top.get("bracketteamid") not in (None, "") else None
    away_team_id = team_id(event_id, bottom.get("bracketteamid")) if bottom.get("bracketteamid") not in (None, "") else None
    results = top.get("gameResults") or []
    if results:
        return [
            {
                "gameId": int(row.get("gameID") or 1),
                "statusId": row.get("matchStatusID", top.get("matchStatusID")),
                "homeScore": row.get("scoreHome"),
                "awayScore": row.get("scoreAway"),
                "homeTeamId": home_team_id,
                "awayTeamId": away_team_id,
            }
            for row in results
        ]
    return [
        {
            "gameId": 1,
            "statusId": top.get("matchStatusID"),
            "homeScore": None,
            "awayScore": None,
            "homeTeamId": home_team_id,
            "awayTeamId": away_team_id,
        }
    ]


def index_relevant_matches(conn: sqlite3.Connection, event: dict[str, Any], bracket: dict[str, Any], player_ids: set[int], *, full_event: bool = False) -> list[dict[str, Any]]:
    event_id = int(event["eventId"])
    targets = []
    for match_id, pair in grouped_matches(bracket).items():
        if match_is_bye(pair):
            # Preserve the raw bracket record, but do not index a bye as a game.
            continue
        if not full_event and not match_has_player(pair, player_ids):
            continue
        top = next((entry for entry in pair if "T" in str(entry.get("bracketpos", ""))), pair[0] if pair else {})
        for entry in pair:
            upsert_team(conn, event_id, entry)
        conn.execute(
            """
            INSERT INTO matches (event_id, match_id, court_id, round_desc, bracket_side, status_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, match_id) DO UPDATE SET
                court_id=excluded.court_id,
                round_desc=excluded.round_desc,
                bracket_side=excluded.bracket_side,
                status_id=excluded.status_id
            """,
            (
                event_id,
                match_id,
                str(top.get("courtid", "")),
                top.get("rounddesc"),
                top.get("bracketside"),
                top.get("matchStatusID"),
            ),
        )
        for game in game_targets_for_match(event_id, pair):
            conn.execute(
                """
                INSERT INTO games (event_id, match_id, game_id, status_id, home_team_id, away_team_id, home_score, away_score, completed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, match_id, game_id) DO UPDATE SET
                    status_id=excluded.status_id,
                    home_team_id=COALESCE(excluded.home_team_id, games.home_team_id),
                    away_team_id=COALESCE(excluded.away_team_id, games.away_team_id),
                    home_score=excluded.home_score,
                    away_score=excluded.away_score,
                    completed=CASE
                        WHEN games.stats_downloaded = 1 AND games.completed = 1 THEN games.completed
                        ELSE excluded.completed
                    END
                """,
                (
                    event_id,
                    match_id,
                    game["gameId"],
                    game.get("statusId"),
                    game.get("homeTeamId"),
                    game.get("awayTeamId"),
                    game.get("homeScore"),
                    game.get("awayScore"),
                    1 if str(game.get("statusId")) == "5" else 0,
                ),
            )
            targets.append({"eventId": event_id, "matchId": match_id, "gameId": game["gameId"]})
    conn.commit()
    return targets


def fetch_match_stats(
    conn: sqlite3.Connection,
    event_id: int,
    match_id: str,
    game_id: int,
    *,
    force: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    path = cache_path("match_stats", f"event_{event_id}_match_{match_id}_game_{game_id}.json")
    url = f"{ACL_BASE}/match-stats/eventid/{event_id}/matchid/{match_id}/gameid/{game_id}"
    try:
        payload, meta = cached_get(
            conn,
            cache_key=f"match-stats:{event_id}:{match_id}:{game_id}",
            url=url,
            source_endpoint="match-stats",
            local_path=path,
            headers=FANZONE_HEADERS,
            force=force,
            completion_checker=match_stats_completed,
        )
    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else None
        if status_code in AUTH_RETRY_STATUSES:
            return None, {
                "source": "auth_required",
                "authRequired": True,
                "statusCode": status_code,
                "message": (
                    "ACL blocked this match-stat file without authentication. "
                    "Season platform cookie fallback is disabled, so this game was skipped "
                    "and the leaderboard may show partial round-level coverage."
                ),
            }
        return None, {"source": "error", "error": str(e), "statusCode": status_code}

    completed = match_stats_completed(payload)
    home_team_id = team_id(event_id, payload.get("homeTeamID")) if payload.get("homeTeamID") is not None else None
    away_team_id = team_id(event_id, payload.get("awayTeamID")) if payload.get("awayTeamID") is not None else None
    conn.execute(
        """
        UPDATE games
        SET stats_downloaded=1,
            completed=?,
            home_team_id=COALESCE(?, home_team_id),
            away_team_id=COALESCE(?, away_team_id),
            home_score=COALESCE(?, home_score),
            away_score=COALESCE(?, away_score)
        WHERE event_id=? AND match_id=? AND game_id=?
        """,
        (
            1 if completed else 0,
            home_team_id,
            away_team_id,
            payload.get("homeScore"),
            payload.get("awayScore"),
            event_id,
            str(match_id),
            game_id,
        ),
    )
    conn.commit()
    upsert_manifest(
        conn,
        entity_type="game",
        entity_id=f"{event_id}:{match_id}:{game_id}",
        source_endpoint="match-stats",
        local_path=path,
        completion_status="complete" if completed else "incomplete",
        metadata={"eventId": event_id, "matchId": match_id, "gameId": game_id},
    )
    return payload, meta


def event_context(conn: sqlite3.Connection, event_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
    return dict(row) if row else {}


def normalize_match_stats_to_rounds(conn: sqlite3.Connection, event_id: int, match_id: str, game_id: int, payload: dict[str, Any]) -> int:
    context = event_context(conn, event_id)
    singles = str(context.get("match_type") or "").upper() == "S"
    court_id = str(payload.get("courtid") or "")
    completed = match_stats_completed(payload)
    raw_check = inspect_match_payload(
        payload,
        completed=completed,
        match_type=context.get("match_type"),
    )
    rows_by_round: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("event_match_inning_history", []) or []:
        try:
            rows_by_round[int(row.get("inningno"))].append(row)
        except Exception:
            continue

    if not completed:
        # V2 keeps live/incremental observations in the preserved raw payload,
        # never in the analytics ledger. All existing profile/model queries can
        # therefore read player_rounds knowing every row came from a verified
        # final response.
        conn.execute(
            "DELETE FROM player_rounds WHERE event_id=? AND match_id=? AND game_id=?",
            (event_id, str(match_id), game_id),
        )
        conn.execute(
            "DELETE FROM rounds WHERE event_id=? AND match_id=? AND game_id=?",
            (event_id, str(match_id), game_id),
        )
        record_game_integrity(
            conn, event_id, str(match_id), game_id,
            raw_status="LIVE", normalization_status="RAW_ONLY",
            integrity_status=PARTIAL, analytics_ready=False,
            expected_player_rows=int(raw_check["expectedPlayerRows"]), normalized_player_rows=0,
            expected_rounds=int(raw_check["expectedRounds"]), normalized_rounds=0,
            checks=raw_check, source_payload_hash=payload_hash(payload),
        )
        conn.commit()
        return 0

    if completed and not raw_check["passed"]:
        # Fail closed: an invalid final response cannot leave an earlier live
        # snapshot available to profiles, reports, rankings, or model training.
        conn.execute(
            "DELETE FROM player_rounds WHERE event_id=? AND match_id=? AND game_id=?",
            (event_id, str(match_id), game_id),
        )
        conn.execute(
            "DELETE FROM rounds WHERE event_id=? AND match_id=? AND game_id=?",
            (event_id, str(match_id), game_id),
        )
        record_game_integrity(
            conn, event_id, str(match_id), game_id,
            raw_status="FINAL", normalization_status="BLOCKED",
            integrity_status=QUARANTINED, analytics_ready=False,
            expected_player_rows=int(raw_check["expectedPlayerRows"]), normalized_player_rows=0,
            expected_rounds=int(raw_check["expectedRounds"]), normalized_rounds=0,
            checks=raw_check, source_payload_hash=payload_hash(payload),
        )
        conn.commit()
        return 0

    # Live match-stat responses are incremental. Once ACL marks a game final,
    # its inning history is the authoritative snapshot and must replace any
    # partial rows saved while the game was underway. Without this replacement,
    # an early one- or two-inning snapshot can remain in the analytics ledger
    # forever even though the cached ACL response later contains the full game.
    if rows_by_round and completed:
        conn.execute(
            "DELETE FROM player_rounds WHERE event_id=? AND match_id=? AND game_id=?",
            (event_id, str(match_id), game_id),
        )
        conn.execute(
            "DELETE FROM rounds WHERE event_id=? AND match_id=? AND game_id=?",
            (event_id, str(match_id), game_id),
        )

    saved = 0
    for round_no, rows in rows_by_round.items():
        if not rows:
            continue
        if len(rows) == 2:
            a, b = rows
            net = int(a.get("totalpoints", 0) or 0) - int(b.get("totalpoints", 0) or 0)
            scoring_team = (
                (a.get("playerid") if singles else a.get("teamid")) if net > 0
                else (b.get("playerid") if singles else b.get("teamid")) if net < 0
                else None
            )
            round_net = abs(net)
        else:
            scoring_team = None
            round_net = 0

        conn.execute(
            """
            INSERT INTO rounds (event_id, match_id, game_id, round_no, scoring_team_id, net_points)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, match_id, game_id, round_no) DO UPDATE SET
                scoring_team_id=excluded.scoring_team_id,
                net_points=excluded.net_points
            """,
            (event_id, str(match_id), game_id, round_no, str(scoring_team) if scoring_team is not None else None, round_net),
        )

        for row in rows:
            player_id = row.get("playerid")
            if not player_id:
                continue
            opponent = next((candidate for candidate in rows if candidate is not row), {})
            gross = int(row.get("totalpoints", 0) or 0)
            opp_points = int(opponent.get("totalpoints", 0) or 0)
            net_points = gross - opp_points
            result = "W" if net_points > 0 else "L" if net_points < 0 else "T"
            bags_in = int(row.get("bagsin", 0) or 0)
            bags_on = int(row.get("bagson", 0) or 0)
            bags_off = int(row.get("bagsoff", 0) or 0)
            first = row.get("playerfirstname")
            last = row.get("playerlastname")

            upsert_player(
                conn,
                {
                    "playerID": player_id,
                    "firstName": first,
                    "lastName": last,
                },
            )
            conn.execute(
                """
                INSERT INTO player_rounds (
                    event_id, match_id, game_id, round_no, player_id, player_name,
                    team_id, opponent_player_id, opponent_team_id, team_side, court_id, gross_points,
                    opponent_points, net_points, scored_points, bags_in, bags_on, bags_off,
                    four_bagger, round_result, event_date, location_id, location_name,
                    match_type, bracket_type, blind_draw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, match_id, game_id, round_no, player_id) DO UPDATE SET
                    player_name=excluded.player_name,
                    team_id=excluded.team_id,
                    opponent_player_id=excluded.opponent_player_id,
                    opponent_team_id=excluded.opponent_team_id,
                    team_side=excluded.team_side,
                    court_id=excluded.court_id,
                    gross_points=excluded.gross_points,
                    opponent_points=excluded.opponent_points,
                    net_points=excluded.net_points,
                    scored_points=excluded.scored_points,
                    bags_in=excluded.bags_in,
                    bags_on=excluded.bags_on,
                    bags_off=excluded.bags_off,
                    four_bagger=excluded.four_bagger,
                    round_result=excluded.round_result,
                    event_date=excluded.event_date,
                    location_id=excluded.location_id,
                    location_name=excluded.location_name,
                    match_type=excluded.match_type,
                    bracket_type=excluded.bracket_type,
                    blind_draw=excluded.blind_draw
                """,
                (
                    event_id,
                    str(match_id),
                    game_id,
                    round_no,
                    int(player_id),
                    display_name(first, last),
                    team_id(event_id, row.get("playerid") if singles else row.get("teamid"))
                    if (row.get("playerid") if singles else row.get("teamid")) is not None else None,
                    int(opponent.get("playerid")) if opponent.get("playerid") else None,
                    team_id(event_id, opponent.get("playerid") if singles else opponent.get("teamid"))
                    if (opponent.get("playerid") if singles else opponent.get("teamid")) is not None else None,
                    str(row.get("teamhomeaway") or "").upper() or None,
                    court_id,
                    gross,
                    opp_points,
                    net_points,
                    max(net_points, 0),
                    bags_in,
                    bags_on,
                    bags_off,
                    1 if bags_in == 4 else 0,
                    result,
                    context.get("event_date"),
                    context.get("location_id"),
                    context.get("location_name"),
                    context.get("match_type"),
                    context.get("bracket_type"),
                    context.get("blind_draw"),
                ),
            )
            saved += 1

    if completed:
        normalized_check = reconcile_normalized_game(conn, event_id, str(match_id), game_id, payload)
        combined_check = {
            "passed": bool(raw_check["passed"] and normalized_check["passed"]),
            "errors": [*raw_check["errors"], *normalized_check["errors"]],
            "warnings": raw_check["warnings"],
            "raw": raw_check,
            "normalized": normalized_check,
        }
        if not normalized_check["passed"]:
            conn.execute(
                "DELETE FROM player_rounds WHERE event_id=? AND match_id=? AND game_id=?",
                (event_id, str(match_id), game_id),
            )
            conn.execute(
                "DELETE FROM rounds WHERE event_id=? AND match_id=? AND game_id=?",
                (event_id, str(match_id), game_id),
            )
            saved = 0
        record_game_integrity(
            conn, event_id, str(match_id), game_id,
            raw_status="FINAL", normalization_status="RECONCILED" if normalized_check["passed"] else "BLOCKED",
            integrity_status=READY if normalized_check["passed"] else QUARANTINED,
            analytics_ready=bool(normalized_check["passed"]),
            expected_player_rows=int(raw_check["expectedPlayerRows"]),
            normalized_player_rows=int(normalized_check["normalizedPlayerRows"]),
            expected_rounds=int(raw_check["expectedRounds"]),
            normalized_rounds=int(normalized_check["normalizedRounds"]),
            checks=combined_check, source_payload_hash=payload_hash(payload),
        )
    conn.commit()
    return saved


def filters_where(filters: dict[str, Any], *, table_alias: str = "") -> tuple[str, list[Any]]:
    prefix = f"{table_alias}." if table_alias else ""
    clauses = []
    values: list[Any] = []
    if filters.get("player_ids"):
        ids = [int(pid) for pid in filters["player_ids"]]
        clauses.append(f"{prefix}player_id IN ({','.join('?' for _ in ids)})")
        values.extend(ids)
    if filters.get("start_date"):
        clauses.append(f"{prefix}event_date >= ?")
        values.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append(f"{prefix}event_date <= ?")
        values.append(filters["end_date"])
    if filters.get("location_id"):
        clauses.append(f"{prefix}location_id = ?")
        values.append(str(filters["location_id"]))
    if filters.get("partner_id"):
        clauses.append(f"{prefix}team_id IN (SELECT team_id FROM team_members WHERE player_id = ?)")
        values.append(int(filters["partner_id"]))
    if filters.get("opponent_id"):
        clauses.append(f"{prefix}opponent_player_id = ?")
        values.append(int(filters["opponent_id"]))
    if filters.get("court_id"):
        clauses.append(f"{prefix}court_id = ?")
        values.append(str(filters["court_id"]))
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", values


def leaderboard(conn: sqlite3.Connection, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where, values = filters_where(filters or {}, table_alias="pr")
    rows = conn.execute(
        f"""
        SELECT
            pr.player_id,
            COALESCE(MAX(NULLIF(pr.player_name, '')), MAX(p.display_name), 'Player ' || pr.player_id) AS name,
            COUNT(DISTINCT pr.event_id) AS events_played,
            COUNT(DISTINCT pr.event_id || ':' || pr.match_id) AS matches_played,
            COUNT(DISTINCT pr.event_id || ':' || pr.match_id || ':' || pr.game_id) AS games_played,
            COUNT(*) AS rounds_thrown,
            SUM(pr.scored_points) AS scored_points,
            AVG(pr.scored_points) AS scored_pts_per_round,
            SUM(pr.gross_points) AS points,
            AVG(pr.gross_points) AS ppr,
            AVG(pr.opponent_points) AS opp_ppr,
            AVG(pr.net_points) AS dpr,
            SUM(pr.opponent_points) AS points_conceded,
            AVG(pr.opponent_points) AS pcpr,
            SUM(pr.four_bagger) AS four_baggers,
            100.0 * SUM(pr.four_bagger) / NULLIF(COUNT(*), 0) AS four_bagger_pct,
            100.0 * SUM(CASE WHEN pr.round_result='W' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS round_win_pct,
            100.0 * SUM(CASE WHEN pr.round_result='L' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS round_loss_pct,
            100.0 * SUM(CASE WHEN pr.round_result='T' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS round_tie_pct,
            100.0 * SUM(pr.bags_in) / NULLIF(SUM(pr.bags_in + pr.bags_on + pr.bags_off), 0) AS bags_in_pct,
            100.0 * SUM(pr.bags_on) / NULLIF(SUM(pr.bags_in + pr.bags_on + pr.bags_off), 0) AS bags_on_pct,
            100.0 * SUM(pr.bags_off) / NULLIF(SUM(pr.bags_in + pr.bags_on + pr.bags_off), 0) AS bags_off_pct,
            COUNT(DISTINCT tm2.player_id) AS partners_used
        FROM player_rounds pr
        LEFT JOIN players p ON p.player_id = pr.player_id
        LEFT JOIN team_members tm1 ON tm1.team_id = pr.team_id AND tm1.player_id = pr.player_id
        LEFT JOIN team_members tm2 ON tm2.team_id = pr.team_id AND tm2.player_id != pr.player_id
        {where}
        GROUP BY pr.player_id
        ORDER BY ppr DESC, dpr DESC, rounds_thrown DESC
        """,
        values,
    ).fetchall()

    event_results = event_result_summary(conn, filters or {})
    out = []
    for row in rows:
        item = dict(row)
        er = event_results.get(item["player_id"], {})
        item["winPct"] = er.get("winPct")
        item["averageFinish"] = er.get("averageFinish")
        item["bestFinish"] = er.get("bestFinish")
        for key, value in list(item.items()):
            if isinstance(value, float):
                item[key] = round(value, 2)
        out.append(item)
    return out


def event_result_summary(conn: sqlite3.Connection, filters: dict[str, Any]) -> dict[int, dict[str, Any]]:
    clauses = []
    values: list[Any] = []
    if filters.get("player_ids"):
        ids = [int(pid) for pid in filters["player_ids"]]
        clauses.append(f"er.player_id IN ({','.join('?' for _ in ids)})")
        values.extend(ids)
    if filters.get("start_date"):
        clauses.append("e.event_date >= ?")
        values.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("e.event_date <= ?")
        values.append(filters["end_date"])
    if filters.get("location_id"):
        clauses.append("e.location_id = ?")
        values.append(str(filters["location_id"]))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT
            er.player_id,
            AVG(er.place) AS average_finish,
            MIN(er.place) AS best_finish,
            100.0 * SUM(CASE WHEN er.wins > er.losses THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS win_pct
        FROM event_results er
        LEFT JOIN events e ON e.event_id = er.event_id
        {where}
        GROUP BY er.player_id
        """,
        values,
    ).fetchall()
    return {
        int(row["player_id"]): {
            "averageFinish": round(row["average_finish"], 2) if row["average_finish"] is not None else None,
            "bestFinish": row["best_finish"],
            "winPct": round(row["win_pct"], 2) if row["win_pct"] is not None else None,
        }
        for row in rows
    }


def upsert_event_results(conn: sqlite3.Connection, event_id: int, rows: Iterable[dict[str, Any]]) -> int:
    saved = 0
    for row in rows:
        player_id = row.get("fldPlayerID") or row.get("playerID")
        if not player_id:
            continue
        first = row.get("fldPlayerFirstName") or row.get("playerFirstName")
        last = row.get("fldPlayerLastname") or row.get("playerLastName")
        upsert_player(conn, {"playerID": player_id, "firstName": first, "lastName": last})
        conn.execute(
            """
            INSERT INTO event_results (
                event_id, player_id, place, points, team_id, team_name, wins, losses, player_ppr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, player_id, team_id) DO UPDATE SET
                place=excluded.place,
                points=excluded.points,
                team_name=excluded.team_name,
                wins=excluded.wins,
                losses=excluded.losses,
                player_ppr=excluded.player_ppr
            """,
            (
                event_id,
                int(player_id),
                int(row.get("fldEventRank") or 0),
                float(row.get("fldEventWeekPoints") or 0),
                str(row.get("fldTeamID")) if row.get("fldTeamID") is not None else "",
                row.get("fldTeamName"),
                int(row.get("wins") or 0),
                int(row.get("losses") or 0),
                float(row.get("playerPPR") or 0),
            ),
        )
        saved += 1
    conn.commit()
    return saved


def upsert_swap_standings(conn: sqlite3.Connection, event_id: int, rows: Iterable[dict[str, Any]]) -> int:
    saved = 0
    for row in rows:
        player_id = row.get("fldPlayerID") or row.get("playerID")
        if not player_id:
            continue

        first = row.get("playerFirstName") or row.get("fldPlayerFirstName")
        last = row.get("playerLastName") or row.get("fldPlayerLastname")
        partner_history = row.get("partnerHistory") if isinstance(row.get("partnerHistory"), list) else []
        team_key = "-".join(str(pid) for pid in sorted([int(player_id), *[int(pid) for pid in partner_history if str(pid).isdigit()]]))

        upsert_player(
            conn,
            {
                "playerID": player_id,
                "firstName": first,
                "lastName": last,
                "city": row.get("playerCity"),
                "state": row.get("playerState"),
                "profileImage": row.get("playerPhoto"),
                "playerSkillLevel": row.get("playerSkillLevel"),
                "playerMembershipType": row.get("playerMembershipType"),
                "playerMembershipName": row.get("playerMembershipName"),
                "_classificationSource": "swap-standings.playerSkillLevel",
                "_membershipSource": "swap-standings",
            },
        )
        conn.execute(
            """
            INSERT INTO swap_standings (
                event_id, player_id, player_name, city, state, player_group, checked_in,
                skill_level, player_ppr, player_cpi, partner_history_json, wins, losses,
                differential_points, total_points, rank, finish_points, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, player_id) DO UPDATE SET
                player_name=excluded.player_name,
                city=excluded.city,
                state=excluded.state,
                player_group=excluded.player_group,
                checked_in=excluded.checked_in,
                skill_level=excluded.skill_level,
                player_ppr=excluded.player_ppr,
                player_cpi=excluded.player_cpi,
                partner_history_json=excluded.partner_history_json,
                wins=excluded.wins,
                losses=excluded.losses,
                differential_points=excluded.differential_points,
                total_points=excluded.total_points,
                rank=excluded.rank,
                finish_points=excluded.finish_points,
                updated_at=excluded.updated_at
            """,
            (
                event_id,
                int(player_id),
                display_name(first, last),
                row.get("playerCity"),
                row.get("playerState"),
                row.get("playerGroup"),
                row.get("playerCheckedIn"),
                row.get("playerSkillLevel"),
                float(row.get("playerPPR") or 0),
                float(row.get("playerCPI") or 0),
                json.dumps(partner_history),
                int(row.get("wins") or 0),
                int(row.get("losses") or 0),
                int(row.get("playerDifferentialPoints") or 0),
                int(row.get("playerTotalPoints") or 0),
                int(row.get("rank") or 0),
                float(row.get("totalfinishpoints") or 0),
                utc_now(),
            ),
        )
        conn.execute(
            """
            INSERT INTO event_results (
                event_id, player_id, place, points, team_id, team_name, wins, losses, player_ppr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, player_id, team_id) DO UPDATE SET
                place=excluded.place,
                points=excluded.points,
                team_name=excluded.team_name,
                wins=excluded.wins,
                losses=excluded.losses,
                player_ppr=excluded.player_ppr
            """,
            (
                event_id,
                int(player_id),
                int(row.get("rank") or 0),
                float(row.get("totalfinishpoints") or 0),
                team_key,
                "Swap / " + ", ".join(str(pid) for pid in partner_history) if partner_history else "Swap",
                int(row.get("wins") or 0),
                int(row.get("losses") or 0),
                float(row.get("playerPPR") or 0),
            ),
        )
        saved += 1
    conn.commit()
    return saved


def fetch_swap_standings(conn: sqlite3.Connection, event_id: int, *, force: bool = False) -> int:
    path = cache_path("swap_standings", f"event_{event_id}.json")
    url = f"{ACL_BASE}/swap-standings/{event_id}"
    try:
        payload, _ = cached_get(
            conn,
            cache_key=f"swap-standings:{event_id}",
            url=url,
            source_endpoint="swap-standings",
            local_path=path,
            headers=FANZONE_HEADERS,
            force=force,
            reuse_if_cached=True,
            payload_before_sanitize=lambda raw_payload: index_contact_payload(
                conn, raw_payload, source_endpoint="swap-standings",
                source_event_id=event_id, source_file=str(path),
            ),
        )
    except requests.HTTPError:
        return 0
    return upsert_swap_standings(conn, event_id, payload.get("data") or [])


def upsert_swap_up_next(conn: sqlite3.Connection, event_id: int, rows: Iterable[dict[str, Any]]) -> int:
    saved = 0
    fetched_at = utc_now()
    conn.execute("DELETE FROM swap_up_next WHERE event_id = ?", (event_id,))
    for row in rows:
        player_id = row.get("fldPlayerID") or row.get("playerID")
        if not player_id:
            continue

        first = row.get("playerFirstName") or row.get("fldPlayerFirstName")
        last = row.get("playerLastName") or row.get("fldPlayerLastname")
        partner_history = row.get("partnerHistory") if isinstance(row.get("partnerHistory"), list) else []
        upsert_player(
            conn,
            {
                "playerID": player_id,
                "firstName": first,
                "lastName": last,
                "city": row.get("playerCity"),
                "state": row.get("playerState"),
                "profileImage": row.get("playerPhoto"),
                "playerSkillLevel": row.get("playerSkillLevel"),
                "playerMembershipType": row.get("playerMembershipType"),
                "playerMembershipName": row.get("playerMembershipName"),
                "_classificationSource": "swap-up-next.playerSkillLevel",
                "_membershipSource": "swap-up-next",
            },
        )
        conn.execute(
            """
            INSERT INTO swap_up_next (
                event_id, player_id, player_name, city, state, player_group, checked_in,
                skill_level, player_ppr, player_cpi, partner_history_json, wins, losses,
                differential_points, total_points, rank, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                int(player_id),
                display_name(first, last),
                row.get("playerCity"),
                row.get("playerState"),
                row.get("playerGroup"),
                row.get("playerCheckedIn"),
                row.get("playerSkillLevel"),
                float(row.get("playerPPR") or 0),
                float(row.get("playerCPI") or 0),
                json.dumps(partner_history),
                int(row.get("wins") or 0),
                int(row.get("losses") or 0),
                int(row.get("playerDifferentialPoints") or 0),
                int(row.get("playerTotalPoints") or 0),
                int(row.get("rank") or 0),
                fetched_at,
            ),
        )
        saved += 1
    conn.commit()
    return saved


def fetch_swap_up_next(conn: sqlite3.Connection, event_id: int, *, force: bool = False) -> int:
    path = cache_path("swap_up_next", f"event_{event_id}.json")
    url = f"{ACL_BASE}/swap-up-next-players-list/{event_id}"
    try:
        payload, _ = cached_get(
            conn,
            cache_key=f"swap-up-next:{event_id}",
            url=url,
            source_endpoint="swap-up-next-players-list",
            local_path=path,
            headers=FANZONE_HEADERS,
            force=force,
            reuse_if_cached=True,
            payload_before_sanitize=lambda raw_payload: index_contact_payload(
                conn, raw_payload, source_endpoint="swap-up-next-players-list",
                source_event_id=event_id, source_file=str(path),
            ),
        )
    except requests.HTTPError:
        return 0
    return upsert_swap_up_next(conn, event_id, payload.get("data") or [])


def fetch_event_standings(conn: sqlite3.Connection, event_id: int, *, force: bool = False) -> int:
    path = cache_path("event_standings", f"event_{event_id}.json")
    url = f"{ACL_BASE}/event-standings/{event_id}"
    try:
        payload, _ = cached_get(
            conn,
            cache_key=f"event-standings:{event_id}",
            url=url,
            source_endpoint="event-standings",
            local_path=path,
            headers=FANZONE_HEADERS,
            force=force,
            reuse_if_cached=True,
        )
    except requests.HTTPError:
        return 0
    saved = upsert_event_results(conn, event_id, payload.get("data") or [])
    swap_saved = fetch_swap_standings(conn, event_id, force=force) if saved == 0 else 0
    up_next_saved = fetch_swap_up_next(conn, event_id, force=force) if saved == 0 else 0
    return saved or swap_saved or up_next_saved


def event_detail_cache_complete(conn: sqlite3.Connection, event_id: int, player_ids: set[int]) -> bool:
    event_row = conn.execute(
        """
        SELECT bracket_completed, match_stats_targets, match_stats_downloaded
        FROM events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    if not event_row or int(event_row["bracket_completed"] or 0) != 1:
        return False

    if player_ids:
        placeholders = ",".join("?" for _ in player_ids)
        result_count = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM event_results
            WHERE event_id = ? AND player_id IN ({placeholders})
            """,
            [event_id, *[int(player_id) for player_id in player_ids]],
        ).fetchone()["count"]
        if int(result_count or 0) == 0:
            return False

    entity_id = player_event_detail_entity_id(event_id, player_ids)
    manifest_row = conn.execute(
        """
        SELECT completion_status
        FROM api_manifest
        WHERE entity_type = 'event_player_detail'
          AND entity_id = ?
          AND source_endpoint = 'season-platform'
        """,
        (entity_id,),
    ).fetchone()
    if manifest_row and manifest_row["completion_status"] == "complete":
        return True

    targets = int(event_row["match_stats_targets"] or 0)
    downloaded = int(event_row["match_stats_downloaded"] or 0)
    if targets > 0 and downloaded >= targets:
        return True

    game_counts = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN stats_downloaded = 1 AND completed = 1 THEN 1 ELSE 0 END) AS complete
        FROM games
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    total = int(game_counts["total"] or 0)
    complete = int(game_counts["complete"] or 0)
    return total > 0 and total == complete


def player_event_detail_entity_id(event_id: int, player_ids: set[int]) -> str:
    players = "-".join(str(player_id) for player_id in sorted(player_ids))
    return f"{event_id}:{players or 'all'}"


def game_detail_cache_complete(
    conn: sqlite3.Connection,
    event_id: int,
    match_id: str,
    game_id: int,
    player_ids: set[int],
) -> bool:
    game_row = conn.execute(
        """
        SELECT stats_downloaded, completed, home_team_id, away_team_id
        FROM games
        WHERE event_id = ? AND match_id = ? AND game_id = ?
        """,
        (event_id, str(match_id), int(game_id)),
    ).fetchone()
    if not game_row:
        return False
    if int(game_row["stats_downloaded"] or 0) != 1 or int(game_row["completed"] or 0) != 1:
        return False
    if not game_row["home_team_id"] or not game_row["away_team_id"]:
        return False

    if not player_ids:
        return True

    placeholders = ",".join("?" for _ in player_ids)
    round_count = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM player_rounds
        WHERE event_id = ?
          AND match_id = ?
          AND game_id = ?
          AND player_id IN ({placeholders})
          AND team_side IS NOT NULL
          AND team_side != ''
        """,
        [event_id, str(match_id), int(game_id), *[int(player_id) for player_id in player_ids]],
    ).fetchone()["count"]
    return int(round_count or 0) > 0


def parse_player_ids(raw: str | Iterable[int]) -> list[int]:
    if isinstance(raw, str):
        return [int(part.strip()) for part in raw.split(",") if part.strip().isdigit()]
    return [int(pid) for pid in raw]


def season_definition_from_events(events: Iterable[dict[str, Any]], bucket_id: int | str) -> dict[str, Any]:
    rows = list(events)
    dates = sorted({event.get("date") for event in rows if event.get("date")})
    years: dict[str, int] = defaultdict(int)
    statuses: dict[str, int] = defaultdict(int)

    for event in rows:
        raw = event.get("raw") or {}
        year = raw.get("leagueYear")
        if year not in (None, ""):
            years[str(year)] += 1
        status = event.get("status")
        if status not in (None, ""):
            statuses[str(status)] += 1

    if dates:
        first_year = dates[0][:4]
        last_year = dates[-1][:4]
    else:
        first_year = last_year = None

    label = "Career / All Seasons" if str(bucket_id) == "career" else f"Bucket {bucket_id}"
    if str(bucket_id) == "career":
        pass
    elif first_year and last_year and first_year != last_year:
        label = f"{first_year}/{last_year[-2:]} Season"
    elif first_year:
        label = f"{first_year} Season"

    return {
        "source": "player-events-grouped",
        "method": "bucket_event_date_range",
        "bucketId": bucket_id,
        "label": label,
        "startDate": dates[0] if dates else None,
        "endDate": dates[-1] if dates else None,
        "eventCount": len(rows),
        "leagueYears": dict(sorted(years.items())),
        "statuses": dict(sorted(statuses.items())),
    }


def player_season_options(
    *,
    player_id: int,
    bucket_ids: Iterable[int] | None = None,
    refresh_index: bool = False,
) -> dict[str, Any]:
    seasons = []
    errors = []

    with db() as conn:
        if bucket_ids is not None:
            buckets = list(bucket_ids)
        elif refresh_index:
            buckets = list(range(1, 13))
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT bucket_id
                FROM events
                WHERE bucket_id IS NOT NULL
                ORDER BY bucket_id DESC
                """
            ).fetchall()
            buckets = [int(row["bucket_id"]) for row in rows if row["bucket_id"] not in (None, "")]
            if not buckets:
                buckets = [11]

        for bucket_id in buckets:
            try:
                events = fetch_player_events(
                    conn,
                    player_id,
                    int(bucket_id),
                    refresh_index=refresh_index,
                )
            except requests.HTTPError:
                errors.append({"bucketId": int(bucket_id), "type": "http"})
                continue
            except Exception as e:
                errors.append({"bucketId": int(bucket_id), "type": "error", "message": str(e)})
                continue

            definition = season_definition_from_events(events, int(bucket_id))
            if not definition.get("startDate") or not definition.get("endDate"):
                continue

            seasons.append(definition)

    seasons.sort(key=lambda item: (item.get("endDate") or "", item.get("bucketId") or 0), reverse=True)
    career_dates = sorted({
        date
        for season in seasons
        for date in (season.get("startDate"), season.get("endDate"))
        if date
    })
    if career_dates:
        seasons.insert(0, {
            "source": "player-events-grouped",
            "method": "all_bucket_event_date_range",
            "bucketId": "career",
            "bucketIds": [season["bucketId"] for season in seasons],
            "label": "Career / All Seasons",
            "startDate": career_dates[0],
            "endDate": career_dates[-1],
            "eventCount": sum(season.get("eventCount") or 0 for season in seasons),
            "leagueYears": {},
            "statuses": {},
        })
    return {
        "playerId": player_id,
        "seasons": seasons,
        "errors": errors,
    }


def gather_player_focused_season(
    *,
    player_ids: list[int],
    start_date: str | None,
    end_date: str | None,
    bucket_id: int | str = 11,
    bucket_ids: Iterable[int] | None = None,
    force: bool = False,
    refresh_index: bool = False,
    include_profiles: bool = False,
    full_event: bool = False,
    progress_callback=None,
) -> dict[str, Any]:
    with db() as conn:
        all_events: dict[int, dict[str, Any]] = {}
        coverage = {
            "players": len(player_ids),
            "eventsDiscovered": 0,
            "eventsInRange": 0,
            "eventsSkippedCached": 0,
            "bracketsChecked": 0,
            "bracketsFailed": 0,
            "matchesTargeted": 0,
            "matchStatsChecked": 0,
            "matchStatsSkippedCached": 0,
            "matchStatsAuthBlocked": 0,
            "matchStatsFailed": 0,
            "playerRoundsSaved": 0,
            "eventResultsSaved": 0,
        }
        notifications: list[dict[str, Any]] = []

        def report(stage: str, message: str, **extra: Any) -> None:
            if not progress_callback:
                return
            progress_callback({
                "stage": stage,
                "message": message,
                "coverage": dict(coverage),
                **extra,
            })

        bucket_list = list(bucket_ids or ([] if str(bucket_id) == "career" else [int(bucket_id)]))
        if not bucket_list:
            bucket_list = list(range(1, 13))
        report("starting", "Preparing season gather.", bucketIds=bucket_list)

        profiles = []
        for player_id in player_ids:
            report("player", f"Finding events for player {player_id}.", playerId=player_id)
            upsert_player(conn, {"playerID": player_id, "firstName": None, "lastName": None})
            if include_profiles:
                profile = fetch_player_profile(conn, player_id, force=force)
                if profile:
                    profiles.append(profile)

            for fetch_bucket_id in bucket_list:
                try:
                    events = fetch_player_events(
                        conn,
                        player_id,
                        int(fetch_bucket_id),
                        force=force,
                        refresh_index=refresh_index,
                    )
                except requests.HTTPError:
                    continue
                coverage["eventsDiscovered"] += len(events)
                report(
                    "events",
                    f"Found {len(events)} events in bucket {fetch_bucket_id}.",
                    playerId=player_id,
                    bucketId=fetch_bucket_id,
                )
                for event in events:
                    event_date = event.get("date")
                    if event_date and (not start_date or event_date >= start_date) and (not end_date or event_date <= end_date):
                        all_events[event["eventId"]] = event

        season_definition = season_definition_from_events(all_events.values(), bucket_id)
        start_date = start_date or season_definition.get("startDate")
        end_date = end_date or season_definition.get("endDate")
        season_definition["selectedStartDate"] = start_date
        season_definition["selectedEndDate"] = end_date
        coverage["eventsInRange"] = len(all_events)
        report("events", f"{coverage['eventsInRange']} events are in scope.", totalEvents=coverage["eventsInRange"])

        target_player_ids = set(player_ids)
        sorted_events = sorted(all_events.values(), key=lambda e: e.get("date") or "")
        for event_index, event in enumerate(sorted_events, start=1):
            event_id = int(event["eventId"])
            event_label = event.get("eventName") or f"Event {event_id}"
            if not force and event_detail_cache_complete(conn, event_id, target_player_ids):
                coverage["eventsSkippedCached"] += 1
                report(
                    "cached",
                    f"Skipped cached completed event {event_index} of {len(sorted_events)}: {event_label}",
                    eventId=event_id,
                    eventIndex=event_index,
                    totalEvents=len(sorted_events),
                )
                continue

            report(
                "event",
                f"Checking event {event_index} of {len(sorted_events)}: {event_label}",
                eventId=event_id,
                eventIndex=event_index,
                totalEvents=len(sorted_events),
            )
            coverage["eventResultsSaved"] += fetch_event_standings(conn, event_id, force=force)

            try:
                bracket, _ = fetch_bracket(conn, event_id, force=force)
            except requests.HTTPError as e:
                coverage["bracketsFailed"] += 1
                status_code = e.response.status_code if e.response is not None else None
                notifications.append({
                    "type": "bracket_failed",
                    "severity": "warning",
                    "eventId": event_id,
                    "statusCode": status_code,
                    "message": (
                        "ACL did not return bracket data for this event. "
                        "Event finishes can still be shown, but match, court, partner, "
                        "and round-level stats may be partial for this event."
                    ),
                })
                report("bracket_failed", f"Bracket unavailable for {event_label}.", eventId=event_id)
                continue

            bracket_event = event_from_bracket(bracket, fallback_event_id=event_id)
            coverage["bracketsChecked"] += 1
            targets = index_relevant_matches(conn, bracket_event, bracket, target_player_ids, full_event=full_event)
            coverage["matchesTargeted"] += len({(t["eventId"], t["matchId"]) for t in targets})
            report(
                "matches",
                f"Found {len(targets)} relevant game target{'s' if len(targets) != 1 else ''}.",
                eventId=event_id,
                targets=len(targets),
            )

            completed_targets = 0
            for target_index, target in enumerate(targets, start=1):
                if not force and game_detail_cache_complete(
                    conn,
                    target["eventId"],
                    target["matchId"],
                    target["gameId"],
                    target_player_ids,
                ):
                    coverage["matchStatsSkippedCached"] += 1
                    completed_targets += 1
                    report(
                        "cached_game",
                        f"Using saved game stats {target_index} of {len(targets)} for event {event_id}.",
                        eventId=target["eventId"],
                        matchId=target["matchId"],
                        gameId=target["gameId"],
                        targetIndex=target_index,
                        targetCount=len(targets),
                    )
                    continue

                report(
                    "match_stats",
                    f"Checking game stats {target_index} of {len(targets)} for event {event_id}.",
                    eventId=target["eventId"],
                    matchId=target["matchId"],
                    gameId=target["gameId"],
                    targetIndex=target_index,
                    targetCount=len(targets),
                )
                stats, stats_meta = fetch_match_stats(
                    conn,
                    target["eventId"],
                    target["matchId"],
                    target["gameId"],
                    force=force,
                )
                coverage["matchStatsChecked"] += 1
                if stats_meta.get("authRequired"):
                    coverage["matchStatsAuthBlocked"] += 1
                    notifications.append({
                        "type": "auth_required",
                        "severity": "warning",
                        "eventId": target["eventId"],
                        "matchId": target["matchId"],
                        "gameId": target["gameId"],
                        "message": stats_meta["message"],
                    })
                    continue
                if stats is None:
                    coverage["matchStatsFailed"] += 1
                    notifications.append({
                        "type": "match_stats_failed",
                        "severity": "warning",
                        "eventId": target["eventId"],
                        "matchId": target["matchId"],
                        "gameId": target["gameId"],
                        "message": "This match-stat file could not be downloaded, so round-level stats for this game are missing.",
                    })
                    continue
                if stats:
                    saved_rounds = normalize_match_stats_to_rounds(
                        conn,
                        target["eventId"],
                        target["matchId"],
                        target["gameId"],
                        stats,
                    )
                    coverage["playerRoundsSaved"] += saved_rounds
                    report(
                        "rounds",
                        f"Saved {saved_rounds} round rows. Total saved: {coverage['playerRoundsSaved']}.",
                        savedRounds=saved_rounds,
                    )
                    if game_detail_cache_complete(
                        conn,
                        target["eventId"],
                        target["matchId"],
                        target["gameId"],
                        target_player_ids,
                    ):
                        completed_targets += 1

            if targets:
                conn.execute(
                    """
                    UPDATE events
                    SET match_stats_targets = ?, match_stats_downloaded = ?
                    WHERE event_id = ?
                    """,
                    (len(targets), completed_targets, event_id),
                )
                conn.commit()
                if completed_targets == len(targets):
                    upsert_manifest(
                        conn,
                        entity_type="event_player_detail",
                        entity_id=player_event_detail_entity_id(event_id, target_player_ids),
                        source_endpoint="season-platform",
                        local_path=None,
                        completion_status="complete",
                        metadata={
                            "eventId": event_id,
                            "playerIds": sorted(target_player_ids),
                            "targets": len(targets),
                            "completedTargets": completed_targets,
                        },
                    )

        filters = {"player_ids": player_ids, "start_date": start_date, "end_date": end_date}
        board = leaderboard(conn, filters)
        individuals = [
            individual_player_package(
                conn,
                player_id=player_id,
                start_date=start_date,
                end_date=end_date,
            )
            for player_id in player_ids
        ]
        manifest = {
            "mode": "full_event" if full_event else "player_focused",
            "playerIds": player_ids,
            "bucketId": bucket_id,
            "bucketIds": bucket_list,
            "startDate": start_date,
            "endDate": end_date,
            "seasonDefinition": season_definition,
            "generatedAt": utc_now(),
            "coverage": coverage,
            "notifications": notifications,
            "events": [
                {
                    "eventId": event.get("eventId"),
                    "eventName": event.get("eventName"),
                    "date": event.get("date"),
                    "status": event.get("status"),
                    "locationId": event.get("locationId"),
                    "locationName": event.get("locationName"),
                }
                for event in sorted(all_events.values(), key=lambda e: e.get("date") or "")
            ],
        }
        manifest_path = cache_path(
            "manifests",
            f"players_{'-'.join(map(str, player_ids))}_bucket_{bucket_id}_{start_date}_{end_date}.json",
        )
        atomic_write_json(manifest_path, manifest)
        report("complete", "Season stats are ready.", done=True)
        return {
            "manifest": manifest,
            "profiles": profiles,
            "individual": individuals[0] if len(individuals) == 1 else None,
            "individuals": individuals,
            "leaderboard": board,
            "notifications": notifications,
            "database": DB_PATH,
            "manifestPath": manifest_path,
        }


def leaderboard_from_db(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    with db() as conn:
        return {"leaderboard": leaderboard(conn, filters or {})}


def player_event_results(conn: sqlite3.Connection, player_id: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = ["er.player_id = ?"]
    values: list[Any] = [int(player_id)]

    if filters.get("start_date"):
        clauses.append("e.event_date >= ?")
        values.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("e.event_date <= ?")
        values.append(filters["end_date"])
    if filters.get("location_id"):
        clauses.append("e.location_id = ?")
        values.append(str(filters["location_id"]))

    rows = conn.execute(
        f"""
        SELECT
            er.event_id,
            e.event_name,
            e.event_date,
            e.status,
            e.location_id,
            e.location_name,
            e.location_city,
            e.location_state,
            e.match_type,
            e.bracket_type,
            e.blind_draw,
            er.place,
            er.points,
            er.team_id,
            er.team_name,
            er.wins,
            er.losses,
            er.player_ppr
        FROM event_results er
        LEFT JOIN events e ON e.event_id = er.event_id
        WHERE {' AND '.join(clauses)}
        ORDER BY e.event_date DESC, er.place ASC
        """,
        values,
    ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        partner_rows = conn.execute(
            """
            SELECT er.player_id, COALESCE(p.display_name, 'Player ' || er.player_id) AS name
            FROM event_results er
            LEFT JOIN players p ON p.player_id = er.player_id
            WHERE er.event_id = ? AND er.team_id = ? AND er.player_id != ?
            ORDER BY name
            """,
            (item["event_id"], item["team_id"], int(player_id)),
        ).fetchall()
        item["partners"] = [dict(partner) for partner in partner_rows]
        swap_rows = conn.execute(
            """
            SELECT
                ss.player_id,
                COALESCE(p.display_name, ss.player_name, 'Player ' || ss.player_id) AS player_name,
                ss.player_group,
                ss.checked_in,
                ss.skill_level,
                ss.player_ppr,
                ss.player_cpi,
                ss.partner_history_json,
                ss.wins,
                ss.losses,
                ss.differential_points,
                ss.total_points,
                ss.rank,
                ss.finish_points
            FROM swap_standings ss
            LEFT JOIN players p ON p.player_id = ss.player_id
            WHERE ss.event_id = ?
            ORDER BY ss.rank ASC, ss.differential_points DESC, ss.total_points DESC, player_name
            """,
            (item["event_id"],),
        ).fetchall()
        item["swapStandings"] = []
        for swap_row in swap_rows:
            swap_item = dict(swap_row)
            swap_item["partnerHistory"] = read_json_value(swap_item.pop("partner_history_json"), [])
            item["swapStandings"].append(swap_item)
        up_next_rows = conn.execute(
            """
            SELECT
                sun.player_id,
                COALESCE(p.display_name, sun.player_name, 'Player ' || sun.player_id) AS player_name,
                sun.player_group,
                sun.checked_in,
                sun.skill_level,
                sun.player_ppr,
                sun.player_cpi,
                sun.partner_history_json,
                sun.wins,
                sun.losses,
                sun.differential_points,
                sun.total_points,
                sun.rank,
                sun.fetched_at
            FROM swap_up_next sun
            LEFT JOIN players p ON p.player_id = sun.player_id
            WHERE sun.event_id = ?
            ORDER BY sun.rank ASC, sun.differential_points DESC, sun.total_points DESC, player_name
            """,
            (item["event_id"],),
        ).fetchall()
        item["swapUpNext"] = []
        for up_next_row in up_next_rows:
            up_next_item = dict(up_next_row)
            up_next_item["partnerHistory"] = read_json_value(up_next_item.pop("partner_history_json"), [])
            item["swapUpNext"].append(up_next_item)
        results.append(item)
    return results


def read_json_value(raw: Any, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def round_metric_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    rounds = item.get("rounds") or 0
    bags = item.get("bags") or 0
    out = {
        key: item.get(key)
        for key in item
        if key not in {"bags"}
    }
    out["ppr"] = round((item.get("gross_points") or 0) / rounds, 2) if rounds else None
    out["dpr"] = round((item.get("net_points") or 0) / rounds, 2) if rounds else None
    out["fourBaggerPct"] = round(100.0 * (item.get("four_baggers") or 0) / rounds, 2) if rounds else None
    out["bagsInPct"] = round(100.0 * (item.get("bags_in") or 0) / bags, 2) if bags else None
    out["bagsOnPct"] = round(100.0 * (item.get("bags_on") or 0) / bags, 2) if bags else None
    out["bagsOffPct"] = round(100.0 * (item.get("bags_off") or 0) / bags, 2) if bags else None
    return out


METRIC_CATALOG = [
    {"key": "name", "label": "Player", "group": "Identity", "grains": ["summary"]},
    {"key": "events_played", "label": "Events Played", "group": "Volume", "grains": ["summary"]},
    {"key": "matches_played", "label": "Matches Played", "group": "Volume", "grains": ["summary"]},
    {"key": "games_played", "label": "Games Played", "group": "Volume", "grains": ["summary"]},
    {"key": "rounds_thrown", "label": "Rounds Thrown", "group": "Volume", "grains": ["summary"]},
    {"key": "points", "label": "Total Points", "group": "Scoring", "grains": ["summary"]},
    {"key": "scored_points", "label": "Scored Points", "group": "Scoring", "grains": ["summary"]},
    {"key": "scored_pts_per_round", "label": "Scored Pts/Rnd", "group": "Scoring", "grains": ["summary"]},
    {"key": "ppr", "label": "PPR", "group": "Scoring", "grains": ["summary", "games", "partners", "timeline"]},
    {"key": "opp_ppr", "label": "Opp PPR", "group": "Opponent", "grains": ["summary", "games"]},
    {"key": "dpr", "label": "DPR / +/-", "group": "Scoring", "grains": ["summary", "games", "partners", "timeline"]},
    {"key": "points_conceded", "label": "Points Conceded", "group": "Opponent", "grains": ["summary"]},
    {"key": "pcpr", "label": "PCPR", "group": "Opponent", "grains": ["summary"]},
    {"key": "four_baggers", "label": "4B#", "group": "Bags", "grains": ["summary"]},
    {"key": "four_bagger_pct", "label": "4B%", "group": "Bags", "grains": ["summary"]},
    {"key": "fourBaggerPct", "label": "4B%", "group": "Bags", "grains": ["games", "partners", "timeline"]},
    {"key": "round_win_pct", "label": "RW%", "group": "Rounds", "grains": ["summary"]},
    {"key": "round_loss_pct", "label": "RL%", "group": "Rounds", "grains": ["summary"]},
    {"key": "round_tie_pct", "label": "RT%", "group": "Rounds", "grains": ["summary"]},
    {"key": "bags_in_pct", "label": "Bags In%", "group": "Bags", "grains": ["summary"]},
    {"key": "bags_on_pct", "label": "Bags On%", "group": "Bags", "grains": ["summary"]},
    {"key": "bags_off_pct", "label": "Bags Off%", "group": "Bags", "grains": ["summary"]},
    {"key": "bagsInPct", "label": "Bags In%", "group": "Bags", "grains": ["games", "partners", "timeline"]},
    {"key": "bagsOnPct", "label": "Bags On%", "group": "Bags", "grains": ["games", "partners", "timeline"]},
    {"key": "bagsOffPct", "label": "Bags Off%", "group": "Bags", "grains": ["games", "partners", "timeline"]},
    {"key": "winPct", "label": "Win %", "group": "Results", "grains": ["summary"]},
    {"key": "averageFinish", "label": "Average Finish", "group": "Results", "grains": ["summary"]},
    {"key": "bestFinish", "label": "Best Finish", "group": "Results", "grains": ["summary"]},
    {"key": "partners_used", "label": "Partners Used", "group": "Partners", "grains": ["summary"]},
    {"key": "event_date", "label": "Date", "group": "Event", "grains": ["events", "games"]},
    {"key": "event_name", "label": "Event", "group": "Event", "grains": ["events", "games"]},
    {"key": "location_name", "label": "Location", "group": "Event", "grains": ["events", "games"]},
    {"key": "place", "label": "Place", "group": "Results", "grains": ["events"]},
    {"key": "points", "label": "Points", "group": "Results", "grains": ["events"]},
    {"key": "wins", "label": "Wins", "group": "Results", "grains": ["events"]},
    {"key": "losses", "label": "Losses", "group": "Results", "grains": ["events"]},
    {"key": "player_ppr", "label": "Event PPR", "group": "Scoring", "grains": ["events"]},
    {"key": "partner_name", "label": "Partner", "group": "Partners", "grains": ["partners"]},
    {"key": "first_date", "label": "First", "group": "Partners", "grains": ["partners"]},
    {"key": "last_date", "label": "Last", "group": "Partners", "grains": ["partners"]},
    {"key": "opponent_name", "label": "Opponent", "group": "Opponent", "grains": ["games"]},
    {"key": "court_id", "label": "Court", "group": "Game", "grains": ["games"]},
    {"key": "match_id", "label": "Match", "group": "Game", "grains": ["games"]},
    {"key": "game_id", "label": "Game", "group": "Game", "grains": ["games"]},
    {"key": "gameResult", "label": "Doubles Result", "group": "Doubles", "grains": ["games"]},
    {"key": "gameScore", "label": "Game Score", "group": "Game", "grains": ["games"]},
    {"key": "directResult", "label": "Head-to-Head Result", "group": "Head-to-Head", "grains": ["games"]},
    {"key": "directRecord", "label": "Head-to-Head Rounds", "group": "Head-to-Head", "grains": ["games"]},
    {"key": "rounds", "label": "Rounds", "group": "Volume", "grains": ["games", "partners", "timeline"]},
    {"key": "gross_points", "label": "Points", "group": "Scoring", "grains": ["games", "partners", "timeline"]},
    {"key": "net_points", "label": "+/-", "group": "Scoring", "grains": ["games", "partners", "timeline"]},
    {"key": "bags_in", "label": "Bags In", "group": "Bags", "grains": ["games", "partners", "timeline"]},
    {"key": "bags_on", "label": "Bags On", "group": "Bags", "grains": ["games", "partners", "timeline"]},
    {"key": "bags_off", "label": "Bags Off", "group": "Bags", "grains": ["games", "partners", "timeline"]},
    {"key": "date", "label": "Date", "group": "Timeline", "grains": ["timeline"]},
    {"key": "rollingPpr", "label": "Rolling PPR", "group": "Timeline", "grains": ["timeline"]},
    {"key": "rollingDpr", "label": "Rolling DPR", "group": "Timeline", "grains": ["timeline"]},
    {"key": "rollingFourBaggerPct", "label": "Rolling 4B%", "group": "Timeline", "grains": ["timeline"]},
]


def player_partner_stats(conn: sqlite3.Connection, player_id: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = ["pr.player_id = ?", "tm2.player_id != ?"]
    values: list[Any] = [int(player_id), int(player_id)]

    if filters.get("start_date"):
        clauses.append("pr.event_date >= ?")
        values.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("pr.event_date <= ?")
        values.append(filters["end_date"])
    if filters.get("location_id"):
        clauses.append("pr.location_id = ?")
        values.append(str(filters["location_id"]))

    rows = conn.execute(
        f"""
        SELECT
            tm2.player_id AS partner_id,
            COALESCE(MAX(p.display_name), 'Player ' || tm2.player_id) AS partner_name,
            MIN(pr.event_date) AS first_date,
            MAX(pr.event_date) AS last_date,
            COUNT(DISTINCT pr.event_id) AS events,
            COUNT(DISTINCT pr.event_id || ':' || pr.match_id) AS matches,
            COUNT(*) AS rounds,
            SUM(pr.gross_points) AS gross_points,
            SUM(pr.net_points) AS net_points,
            SUM(pr.four_bagger) AS four_baggers,
            SUM(pr.bags_in) AS bags_in,
            SUM(pr.bags_on) AS bags_on,
            SUM(pr.bags_off) AS bags_off,
            SUM(pr.bags_in + pr.bags_on + pr.bags_off) AS bags
        FROM player_rounds pr
        JOIN team_members tm2 ON tm2.team_id = pr.team_id AND tm2.event_id = pr.event_id
        LEFT JOIN players p ON p.player_id = tm2.player_id
        WHERE {' AND '.join(clauses)}
        GROUP BY tm2.player_id
        ORDER BY events DESC, rounds DESC, partner_name
        """,
        values,
    ).fetchall()

    return [round_metric_row(row) for row in rows]


def player_game_stats(conn: sqlite3.Connection, player_id: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = ["pr.player_id = ?"]
    values: list[Any] = [int(player_id)]

    if filters.get("start_date"):
        clauses.append("pr.event_date >= ?")
        values.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("pr.event_date <= ?")
        values.append(filters["end_date"])
    if filters.get("location_id"):
        clauses.append("pr.location_id = ?")
        values.append(str(filters["location_id"]))
    if filters.get("opponent_id"):
        clauses.append("pr.opponent_player_id = ?")
        values.append(int(filters["opponent_id"]))
    if filters.get("court_id"):
        clauses.append("pr.court_id = ?")
        values.append(str(filters["court_id"]))

    rows = conn.execute(
        f"""
        SELECT
            pr.event_id,
            MAX(e.event_name) AS event_name,
            pr.event_date,
            pr.location_id,
            pr.location_name,
            pr.match_id,
            pr.game_id,
            MAX(m.round_desc) AS round_desc,
            pr.court_id,
            pr.team_id,
            pr.opponent_team_id,
            MAX(e.match_type) AS match_type,
            MAX(e.bracket_type) AS bracket_type,
            tm2.player_id AS partner_id,
            COALESCE(MAX(NULLIF(partner.display_name, '')), MAX('Player ' || tm2.player_id)) AS partner_name,
            pr.opponent_player_id,
            COALESCE(MAX(NULLIF(opp.display_name, '')), MAX('Player ' || pr.opponent_player_id)) AS opponent_name,
            MAX(pr.team_side) AS team_side,
            MAX(g.home_team_id) AS home_team_id,
            MAX(g.away_team_id) AS away_team_id,
            MAX(g.home_score) AS home_score,
            MAX(g.away_score) AS away_score,
            COUNT(*) AS rounds,
            SUM(pr.gross_points) AS gross_points,
            SUM(pr.opponent_points) AS opponent_points,
            SUM(pr.net_points) AS net_points,
            SUM(pr.scored_points) AS scored_points,
            SUM(pr.four_bagger) AS four_baggers,
            SUM(pr.bags_in) AS bags_in,
            SUM(pr.bags_on) AS bags_on,
            SUM(pr.bags_off) AS bags_off,
            SUM(pr.bags_in + pr.bags_on + pr.bags_off) AS bags,
            SUM(CASE WHEN pr.round_result='W' THEN 1 ELSE 0 END) AS rounds_won,
            SUM(CASE WHEN pr.round_result='L' THEN 1 ELSE 0 END) AS rounds_lost,
            SUM(CASE WHEN pr.round_result='T' THEN 1 ELSE 0 END) AS rounds_tied
        FROM player_rounds pr
        LEFT JOIN players opp ON opp.player_id = pr.opponent_player_id
        LEFT JOIN team_members tm2 ON tm2.team_id = pr.team_id AND tm2.event_id = pr.event_id AND tm2.player_id != pr.player_id
        LEFT JOIN players partner ON partner.player_id = tm2.player_id
        LEFT JOIN events e ON e.event_id = pr.event_id
        LEFT JOIN matches m ON m.event_id = pr.event_id AND m.match_id = pr.match_id
        LEFT JOIN games g ON g.event_id = pr.event_id AND g.match_id = pr.match_id AND g.game_id = pr.game_id
        WHERE {' AND '.join(clauses)}
        GROUP BY pr.event_id, pr.match_id, pr.game_id, pr.player_id, pr.opponent_player_id, pr.team_id, pr.opponent_team_id, tm2.player_id
        ORDER BY pr.event_date DESC, pr.event_id DESC, pr.match_id, pr.game_id
        """,
        values,
    ).fetchall()

    games = []
    for row in rows:
        item = round_metric_row(row)
        rounds = item.get("rounds") or 0
        item["opp_ppr"] = round((item.get("opponent_points") or 0) / rounds, 2) if rounds else None
        item["round_win_pct"] = round(100.0 * (item.get("rounds_won") or 0) / rounds, 2) if rounds else None
        item["round_loss_pct"] = round(100.0 * (item.get("rounds_lost") or 0) / rounds, 2) if rounds else None
        item["round_tie_pct"] = round(100.0 * (item.get("rounds_tied") or 0) / rounds, 2) if rounds else None
        direct_diff = item.get("net_points") or 0
        item["directResult"] = "W" if direct_diff > 0 else "L" if direct_diff < 0 else "T"
        item["directRecord"] = f"{item.get('rounds_won') or 0}-{item.get('rounds_lost') or 0}-{item.get('rounds_tied') or 0}"

        team_side = str(item.get("team_side") or "").upper()
        if team_side not in {"HOME", "AWAY"}:
            if item.get("team_id") and item.get("team_id") == item.get("home_team_id"):
                team_side = "HOME"
            elif item.get("team_id") and item.get("team_id") == item.get("away_team_id"):
                team_side = "AWAY"
        home_score = item.get("home_score")
        away_score = item.get("away_score")
        if home_score is not None and away_score is not None and team_side in {"HOME", "AWAY"}:
            team_score = home_score if team_side == "HOME" else away_score
            opponent_team_score = away_score if team_side == "HOME" else home_score
            item["team_score"] = team_score
            item["opponent_team_score"] = opponent_team_score
            item["gameResult"] = "W" if team_score > opponent_team_score else "L" if team_score < opponent_team_score else "T"
            item["gameScore"] = f"{team_score}-{opponent_team_score}"
        else:
            item["gameResult"] = None
            item["gameScore"] = None
        item["result"] = item["gameResult"] or item["directResult"]
        games.append(item)
    return games


def player_daily_timeline(
    conn: sqlite3.Connection,
    player_id: int,
    filters: dict[str, Any],
    *,
    rolling_days: int = 30,
) -> list[dict[str, Any]]:
    clauses = ["player_id = ?", "event_date IS NOT NULL", "event_date != ''"]
    values: list[Any] = [int(player_id)]

    if filters.get("start_date"):
        clauses.append("event_date >= ?")
        values.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("event_date <= ?")
        values.append(filters["end_date"])
    if filters.get("location_id"):
        clauses.append("location_id = ?")
        values.append(str(filters["location_id"]))

    rows = conn.execute(
        f"""
        SELECT
            event_date AS date,
            COUNT(DISTINCT event_id) AS events,
            COUNT(DISTINCT event_id || ':' || match_id) AS matches,
            COUNT(*) AS rounds,
            SUM(gross_points) AS gross_points,
            SUM(net_points) AS net_points,
            SUM(four_bagger) AS four_baggers,
            SUM(bags_in) AS bags_in,
            SUM(bags_on) AS bags_on,
            SUM(bags_off) AS bags_off,
            SUM(bags_in + bags_on + bags_off) AS bags
        FROM player_rounds
        WHERE {' AND '.join(clauses)}
        GROUP BY event_date
        ORDER BY event_date ASC
        """,
        values,
    ).fetchall()

    raw_rows = [dict(row) for row in rows]
    timeline: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        day = round_metric_row(row)
        current_date = datetime.fromisoformat(str(row["date"])[:10])
        rolling_source = [
            candidate
            for candidate in raw_rows[:index + 1]
            if 0 <= (current_date - datetime.fromisoformat(str(candidate["date"])[:10])).days < rolling_days
        ]
        rolling_rounds = sum(candidate.get("rounds") or 0 for candidate in rolling_source)
        rolling_bags = sum(candidate.get("bags") or 0 for candidate in rolling_source)
        rolling_gross = sum(candidate.get("gross_points") or 0 for candidate in rolling_source)
        rolling_net = sum(candidate.get("net_points") or 0 for candidate in rolling_source)
        rolling_four_baggers = sum(candidate.get("four_baggers") or 0 for candidate in rolling_source)

        day["rollingDays"] = rolling_days
        day["rollingPpr"] = round(rolling_gross / rolling_rounds, 2) if rolling_rounds else None
        day["rollingDpr"] = round(rolling_net / rolling_rounds, 2) if rolling_rounds else None
        day["rollingFourBaggerPct"] = round(100.0 * rolling_four_baggers / rolling_rounds, 2) if rolling_rounds else None
        day["rollingRounds"] = rolling_rounds
        day["rollingBagsInPct"] = round(
            100.0 * sum(candidate.get("bags_in") or 0 for candidate in rolling_source) / rolling_bags,
            2,
        ) if rolling_bags else None
        timeline.append(day)

    return timeline


def individual_player_package(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    start_date: str,
    end_date: str,
    location_id: str | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "player_ids": [player_id],
        "start_date": start_date,
        "end_date": end_date,
    }
    if location_id:
        filters["location_id"] = location_id

    board = leaderboard(conn, filters)
    events = player_event_results(conn, player_id, filters)
    partners = player_partner_stats(conn, player_id, filters)
    games = player_game_stats(conn, player_id, filters)
    timeline = player_daily_timeline(conn, player_id, filters)
    player = board[0] if board else {
        "player_id": player_id,
        "name": f"Player {player_id}",
        "events_played": len(events),
    }

    locations = sorted({
        event.get("location_name")
        for event in events
        if event.get("location_name")
    })

    return {
        "player": player,
        "eventResults": events,
        "games": games,
        "partners": partners,
        "timeline": timeline,
        "metricCatalog": METRIC_CATALOG,
        "summary": {
            "eventsPlayed": len({event["event_id"] for event in events}),
            "eventResults": len(events),
            "locations": len(locations),
            "partners": len(partners),
            "timelineDays": len(timeline),
            "bestFinish": min((event["place"] for event in events if event.get("place")), default=None),
            "averageFinish": round(
                sum(event["place"] for event in events if event.get("place")) /
                max(1, len([event for event in events if event.get("place")])),
                2,
            ) if events else None,
        },
        "locations": locations,
    }
