from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PROFILE_KEY = "temporary-global"
DEFAULT_PLAYER_ID = 142125


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _profile_path() -> Path | None:
    explicit = os.getenv("SHARED_VIEWER_PROFILE_PATH")
    data_dir = os.getenv("DATA_DIR")
    raw = explicit or (os.path.join(data_dir, "shared_viewer_profile.json") if data_dir else "")
    return Path(raw) if raw else None


def _read_file_profile() -> dict[str, Any] | None:
    path = _profile_path()
    if not path or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_file_profile(payload: dict[str, Any]) -> None:
    path = _profile_path()
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def ensure_shared_viewer_profile_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS shared_viewer_profiles (
            profile_key TEXT PRIMARY KEY,
            default_player_id INTEGER,
            favorite_players_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO shared_viewer_profiles(
            profile_key, default_player_id, favorite_players_json, updated_at
        ) VALUES (?, ?, ?, ?)
        """,
        (
            PROFILE_KEY,
            DEFAULT_PLAYER_ID,
            json.dumps([{"playerId": DEFAULT_PLAYER_ID, "name": "Adam Gershon"}]),
            _now(),
        ),
    )
    conn.commit()


def get_shared_viewer_profile(conn) -> dict[str, Any]:
    file_profile = _read_file_profile()
    if file_profile is not None:
        return file_profile
    ensure_shared_viewer_profile_schema(conn)
    row = conn.execute(
        "SELECT * FROM shared_viewer_profiles WHERE profile_key=?", (PROFILE_KEY,)
    ).fetchone()
    try:
        favorites = json.loads(row["favorite_players_json"] or "[]")
    except (TypeError, ValueError):
        favorites = []
    if not isinstance(favorites, list):
        favorites = []
    profile = {
        "profileKey": PROFILE_KEY,
        "mode": "SHARED_TEMPORARY",
        "defaultPlayerId": int(row["default_player_id"]) if row["default_player_id"] else None,
        "favoritePlayers": favorites,
        "updatedAt": row["updated_at"],
    }
    _write_file_profile(profile)
    return profile


def update_shared_viewer_profile(
    conn,
    *,
    default_player_id: int | None,
    favorite_players: list[dict[str, Any]],
) -> dict[str, Any]:
    ensure_shared_viewer_profile_schema(conn)
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for player in favorite_players:
        try:
            player_id = int(player.get("playerId"))
        except (TypeError, ValueError, AttributeError):
            continue
        if player_id <= 0 or player_id in seen:
            continue
        seen.add(player_id)
        item: dict[str, Any] = {"playerId": player_id}
        for field in ("name", "photo"):
            value = str(player.get(field) or "").strip()
            if value:
                item[field] = value
        normalized.append(item)
    if default_player_id and default_player_id not in seen:
        normalized.insert(0, {"playerId": int(default_player_id)})
    now = _now()
    profile = {
        "profileKey": PROFILE_KEY,
        "mode": "SHARED_TEMPORARY",
        "defaultPlayerId": int(default_player_id) if default_player_id else None,
        "favoritePlayers": normalized,
        "updatedAt": now,
    }
    # In production this tiny, atomic settings file is authoritative. It keeps
    # a phone changing favorites from waiting behind the analytics SQLite
    # writer. The main database remains the local-development fallback.
    if _profile_path():
        _write_file_profile(profile)
        return profile
    conn.execute(
        """
        UPDATE shared_viewer_profiles
        SET default_player_id=?, favorite_players_json=?, updated_at=?
        WHERE profile_key=?
        """,
        (
            int(default_player_id) if default_player_id else None,
            json.dumps(normalized, separators=(",", ":")),
            now,
            PROFILE_KEY,
        ),
    )
    conn.commit()
    return get_shared_viewer_profile(conn)


def enroll_default_player_brackets_from_collected_rosters(conn) -> dict[str, Any]:
    """Promote brackets found by the normal tournament polling pipeline.

    This performs no ACL request. It only examines rosters already written by
    existing event discovery/schedule polling, then marks matching monitored
    brackets for the durable frozen-prediction queue.
    """
    profile = get_shared_viewer_profile(conn)
    player_id = profile.get("defaultPlayerId")
    if not player_id:
        return {"status": "NO_DEFAULT_PLAYER", "matched": [], "newlyEnabled": []}

    # These normalized tables are populated by the same schedule/bracket calls
    # already made for monitored tournaments. Restricting the promotion to
    # schedule_format=BRACKET prevents a parent swap from being forecast.
    rows = conn.execute(
        """
        SELECT DISTINCT CAST(m.event_id AS INTEGER) AS event_id,
               m.auto_freeze_prediction
        FROM monitored_events m
        WHERE m.enabled=1 AND m.schedule_format='BRACKET'
          AND (
            EXISTS (
              SELECT 1 FROM team_members tm
              WHERE CAST(tm.event_id AS TEXT)=m.event_id AND tm.player_id=?
            )
            OR EXISTS (
              SELECT 1 FROM player_rounds pr
              WHERE CAST(pr.event_id AS TEXT)=m.event_id AND pr.player_id=?
            )
            OR EXISTS (
              SELECT 1 FROM swap_standings ss
              WHERE CAST(ss.event_id AS TEXT)=m.event_id AND ss.player_id=?
            )
          )
        """,
        (player_id, player_id, player_id),
    ).fetchall()
    matched = [int(row["event_id"]) for row in rows]
    newly_enabled = [
        int(row["event_id"])
        for row in rows
        if int(row["auto_freeze_prediction"] or 0) != 1
    ]
    if matched:
        placeholders = ",".join("?" for _ in matched)
        conn.execute(
            f"UPDATE monitored_events SET auto_freeze_prediction=1 WHERE CAST(event_id AS INTEGER) IN ({placeholders})",
            matched,
        )
        conn.commit()
    return {
        "status": "COMPLETE",
        "defaultPlayerId": player_id,
        "matched": matched,
        "newlyEnabled": newly_enabled,
    }
