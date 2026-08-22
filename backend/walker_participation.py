from __future__ import annotations

import copy
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


WALKER_PARTICIPATION = "WALKER_SOLO_DOUBLES"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _name(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(primary) or row.get(fallback) or "").strip()
        for primary, fallback in (("playerfirstname", "firstname"), ("playerlastname", "lastname"))
    ).strip().casefold()


def is_definitive_placeholder(row: dict[str, Any]) -> bool:
    """Recognize ACL synthetic seats without treating real Walkers as placeholders."""
    try:
        player_id = int(row.get("playerid") or row.get("playerID") or row.get("id") or 0)
    except (TypeError, ValueError):
        player_id = 0
    name = _name(row)
    return (player_id == 99999 and name in {"ghost player", "ghost", "casper ghost"})


def ensure_walker_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS walker_participations (
            event_id INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            game_id INTEGER NOT NULL,
            team_id TEXT,
            actual_player_id INTEGER NOT NULL,
            placeholder_player_id INTEGER NOT NULL,
            placeholder_name TEXT,
            participation_type TEXT NOT NULL,
            detection_basis TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY(event_id, match_id, game_id, placeholder_player_id)
        );
        """
    )


def transform_walker_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Map a definitive synthetic doubles seat to its single real thrower.

    The returned payload is analytics-only. The caller retains the original ACL
    response for provenance and replay.
    """
    transformed = copy.deepcopy(payload)
    history = transformed.get("event_match_inning_history") or []
    team_details = transformed.get("event_team_details") or []
    candidates = [*history, *team_details]
    by_team: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in candidates:
        if not isinstance(row, dict) or row.get("teamid") is None or row.get("playerid") is None:
            continue
        try:
            by_team[str(row["teamid"])][int(row["playerid"])] = row
        except (TypeError, ValueError):
            continue

    aliases: dict[int, tuple[int, dict[str, Any], str]] = {}
    for team, players in by_team.items():
        placeholders = [(pid, row) for pid, row in players.items() if is_definitive_placeholder(row)]
        actual = [(pid, row) for pid, row in players.items() if not is_definitive_placeholder(row)]
        if len(placeholders) == 1 and len(actual) == 1:
            placeholder_id, placeholder_row = placeholders[0]
            actual_id, actual_row = actual[0]
            aliases[placeholder_id] = (actual_id, actual_row, team)

    if not aliases:
        return transformed, []

    attributions: list[dict[str, Any]] = []
    for placeholder_id, (actual_id, actual_row, team) in aliases.items():
        placeholder = next((r for r in candidates if isinstance(r, dict) and str(r.get("teamid")) == team and int(r.get("playerid") or 0) == placeholder_id), {})
        attributions.append({
            "teamId": team,
            "actualPlayerId": actual_id,
            "placeholderPlayerId": placeholder_id,
            "placeholderName": " ".join(str(placeholder.get(k) or "").strip() for k in ("playerfirstname", "playerlastname")).strip(),
            "participationType": WALKER_PARTICIPATION,
            "detectionBasis": "ACL_SYNTHETIC_PLAYER_99999_GHOST_WITH_ONE_REAL_TEAMMATE",
        })

    for row in history:
        try:
            alias = aliases.get(int(row.get("playerid") or 0))
        except (TypeError, ValueError):
            alias = None
        if alias:
            actual_id, actual_row, _ = alias
            row["attributed_from_player_id"] = row.get("playerid")
            row["playerid"] = actual_id
            row["playerfirstname"] = actual_row.get("playerfirstname")
            row["playerlastname"] = actual_row.get("playerlastname")
            row["participation_type"] = WALKER_PARTICIPATION

    # The integrity layer compares declared player totals with inning history.
    # Merge the two ACL position summaries into the real player summary.
    merged_details: list[dict[str, Any]] = []
    detail_groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in transformed.get("event_match_details") or []:
        try:
            pid = int(row.get("playerid") or 0)
        except (TypeError, ValueError):
            pid = 0
        target = aliases.get(pid)
        target_id = target[0] if target else pid
        detail_groups[(str(row.get("teamid") or ""), target_id)].append(row)
    additive = ("playedinnings", "rounds", "totalpts", "bagsin", "bagson", "bagsoff", "fourbaggers")
    for (_, target_id), rows in detail_groups.items():
        base = copy.deepcopy(next((r for r in rows if int(r.get("playerid") or 0) == target_id), rows[0]))
        base["playerid"] = target_id
        for field in additive:
            base[field] = sum(int(r.get(field) or 0) for r in rows)
        merged_details.append(base)
    if detail_groups:
        transformed["event_match_details"] = merged_details

    deduped: dict[tuple[str, int], dict[str, Any]] = {}
    for row in team_details:
        try:
            pid = int(row.get("playerid") or 0)
        except (TypeError, ValueError):
            pid = 0
        alias = aliases.get(pid)
        if alias:
            pid, actual_row, _ = alias
            row["playerid"] = pid
            row["playerfirstname"] = actual_row.get("playerfirstname")
            row["playerlastname"] = actual_row.get("playerlastname")
        deduped[(str(row.get("teamid") or ""), pid)] = row
    if team_details:
        transformed["event_team_details"] = list(deduped.values())
    return transformed, attributions


def record_walker_participations(conn: sqlite3.Connection, event_id: int, match_id: str, game_id: int, rows: list[dict[str, Any]]) -> None:
    ensure_walker_schema(conn)
    for row in rows:
        conn.execute(
            """
            INSERT INTO walker_participations(
                event_id, match_id, game_id, team_id, actual_player_id,
                placeholder_player_id, placeholder_name, participation_type,
                detection_basis, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, match_id, game_id, placeholder_player_id) DO UPDATE SET
                actual_player_id=excluded.actual_player_id,
                placeholder_name=excluded.placeholder_name,
                detection_basis=excluded.detection_basis,
                recorded_at=excluded.recorded_at
            """,
            (event_id, str(match_id), game_id, row["teamId"], row["actualPlayerId"],
             row["placeholderPlayerId"], row["placeholderName"], row["participationType"],
             row["detectionBasis"], _now()),
        )
