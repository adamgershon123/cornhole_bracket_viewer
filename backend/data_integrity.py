from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


INTEGRITY_VERSION = "data-integrity-v2.0"
READY = "VERIFIED"
QUARANTINED = "QUARANTINED"
PARTIAL = "PARTIAL"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_integrity_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS game_data_integrity (
            event_id INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            game_id INTEGER NOT NULL,
            integrity_version TEXT NOT NULL,
            raw_status TEXT NOT NULL,
            normalization_status TEXT NOT NULL,
            integrity_status TEXT NOT NULL,
            analytics_ready INTEGER NOT NULL DEFAULT 0,
            expected_player_rows INTEGER NOT NULL DEFAULT 0,
            normalized_player_rows INTEGER NOT NULL DEFAULT 0,
            expected_rounds INTEGER NOT NULL DEFAULT 0,
            normalized_rounds INTEGER NOT NULL DEFAULT 0,
            source_payload_hash TEXT,
            checks_json TEXT NOT NULL DEFAULT '{}',
            checked_at TEXT NOT NULL,
            PRIMARY KEY(event_id, match_id, game_id)
        );

        CREATE TABLE IF NOT EXISTS data_integrity_issues (
            issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            game_id INTEGER NOT NULL,
            integrity_version TEXT NOT NULL,
            issue_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            detected_at TEXT NOT NULL,
            resolved_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_integrity_status
            ON game_data_integrity(integrity_status, analytics_ready);
        CREATE INDEX IF NOT EXISTS idx_integrity_event
            ON game_data_integrity(event_id, integrity_status);
        CREATE INDEX IF NOT EXISTS idx_integrity_issues_open
            ON data_integrity_issues(resolved_at, issue_code);

        CREATE TABLE IF NOT EXISTS derived_artifact_lineage (
            artifact_type TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            integrity_version TEXT NOT NULL,
            calculation_version TEXT NOT NULL,
            source_fingerprint TEXT,
            integrity_status TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(artifact_type, artifact_id)
        );
        """
    )


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def inspect_match_payload(
    payload: dict[str, Any],
    *,
    completed: bool,
    match_type: str | None = None,
) -> dict[str, Any]:
    singles = str(match_type or "").upper() == "S"
    history = payload.get("event_match_inning_history", []) or []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    by_round: dict[int, list[dict[str, Any]]] = defaultdict(list)
    player_totals: Counter[int] = Counter()
    player_rounds: Counter[int] = Counter()
    player_teams: dict[int, set[str]] = defaultdict(set)
    teams: set[str] = set()
    seen: set[tuple[int, int]] = set()

    for index, raw in enumerate(history):
        if not isinstance(raw, dict):
            errors.append({"code": "INVALID_HISTORY_ROW", "index": index})
            continue
        round_no = _integer(raw.get("inningno"))
        player_id = _integer(raw.get("playerid"))
        if not round_no or round_no < 1 or not player_id:
            errors.append({"code": "MISSING_ROUND_OR_PLAYER", "index": index})
            continue
        key = (round_no, player_id)
        if key in seen:
            errors.append({"code": "DUPLICATE_PLAYER_ROUND", "round": round_no, "playerId": player_id})
        seen.add(key)
        gross = _integer(raw.get("totalpoints"))
        if gross is None or not 0 <= gross <= 12:
            errors.append({"code": "IMPOSSIBLE_ROUND_SCORE", "round": round_no, "playerId": player_id, "value": gross})
        bag_values = [_integer(raw.get(key)) for key in ("bagsin", "bagson", "bagsoff")]
        if any(value is not None for value in bag_values):
            if any(value is None or value < 0 for value in bag_values) or sum(value or 0 for value in bag_values) != 4:
                errors.append({"code": "INVALID_BAG_TOTAL", "round": round_no, "playerId": player_id, "values": bag_values})
        by_round[round_no].append(raw)
        team_value = raw.get("teamid")
        if team_value not in (None, ""):
            normalized_team = str(team_value)
            teams.add(normalized_team)
            player_teams[player_id].add(normalized_team)
        player_rounds[player_id] += 1
        player_totals[player_id] += gross or 0

    if completed and not by_round:
        errors.append({"code": "COMPLETED_WITHOUT_HISTORY"})
    for round_no, rows in sorted(by_round.items()):
        if len(rows) != 2:
            errors.append({"code": "ROUND_PLAYER_COUNT", "round": round_no, "count": len(rows), "expected": 2})
        elif not singles and str(rows[0].get("teamid")) == str(rows[1].get("teamid")):
            errors.append({"code": "ROUND_SAME_TEAM", "round": round_no})

    if completed and by_round:
        expected_sequence = list(range(1, max(by_round) + 1))
        actual_sequence = sorted(by_round)
        if actual_sequence != expected_sequence:
            errors.append({"code": "ROUND_SEQUENCE_GAP", "expected": expected_sequence, "actual": actual_sequence})
        if not singles and len(teams) != 2:
            errors.append({"code": "GAME_TEAM_COUNT", "count": len(teams), "expected": 2, "teams": sorted(teams)})
        for player_id, assigned_teams in sorted(player_teams.items()):
            if not singles and len(assigned_teams) > 1:
                errors.append({"code": "PLAYER_TEAM_CHANGED", "playerId": player_id, "teams": sorted(assigned_teams)})

    details = payload.get("event_match_details", []) or []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        player_id = _integer(_value(detail, "playerid", "playerID"))
        if not player_id:
            continue
        declared_rounds = _integer(_value(detail, "playedinnings", "playedInnings", "rdsTotal"))
        declared_points = _integer(_value(detail, "totalpts", "totalPts", "totPtsTotal"))
        if declared_rounds is not None and declared_rounds != player_rounds[player_id]:
            errors.append({"code": "PLAYER_ROUND_TOTAL_MISMATCH", "playerId": player_id, "declared": declared_rounds, "history": player_rounds[player_id]})
        if declared_points is not None and declared_points != player_totals[player_id]:
            errors.append({"code": "PLAYER_POINT_TOTAL_MISMATCH", "playerId": player_id, "declared": declared_points, "history": player_totals[player_id]})

    return {
        "passed": not errors,
        "completed": completed,
        "expectedPlayerRows": sum(len(rows) for rows in by_round.values()),
        "expectedRounds": len(by_round),
        "errors": errors,
        "warnings": warnings,
    }


def reconcile_normalized_game(
    conn: sqlite3.Connection,
    event_id: int,
    match_id: str,
    game_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    expected: dict[tuple[int, int], tuple[int, int, int, int, int, int]] = {}
    by_round: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("event_match_inning_history", []) or []:
        round_no = _integer(row.get("inningno")) if isinstance(row, dict) else None
        player_id = _integer(row.get("playerid")) if isinstance(row, dict) else None
        if round_no and player_id:
            by_round[round_no].append(row)
    for round_no, rows in by_round.items():
        for row in rows:
            player_id = int(row["playerid"])
            opponent = next((candidate for candidate in rows if candidate is not row), {})
            bags_in = int(row.get("bagsin", 0) or 0)
            expected[(round_no, player_id)] = (
                int(row.get("totalpoints", 0) or 0),
                int(opponent.get("totalpoints", 0) or 0),
                bags_in,
                int(row.get("bagson", 0) or 0),
                int(row.get("bagsoff", 0) or 0),
                1 if bags_in == 4 else 0,
            )
    actual_rows = conn.execute(
        """
        SELECT round_no, player_id, gross_points, opponent_points,
               bags_in, bags_on, bags_off, four_bagger
        FROM player_rounds
        WHERE event_id=? AND match_id=? AND game_id=?
        """,
        (event_id, str(match_id), game_id),
    ).fetchall()
    actual = {
        (int(row["round_no"]), int(row["player_id"])): (
            int(row["gross_points"]), int(row["opponent_points"]),
            int(row["bags_in"]), int(row["bags_on"]), int(row["bags_off"]), int(row["four_bagger"]),
        )
        for row in actual_rows
    }
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(key for key in set(expected) & set(actual) if expected[key] != actual[key])
    normalized_rounds = int(conn.execute(
        "SELECT COUNT(*) FROM rounds WHERE event_id=? AND match_id=? AND game_id=?",
        (event_id, str(match_id), game_id),
    ).fetchone()[0])
    errors = []
    if missing:
        errors.append({"code": "NORMALIZED_ROWS_MISSING", "count": len(missing), "examples": missing[:10]})
    if extra:
        errors.append({"code": "NORMALIZED_ROWS_EXTRA", "count": len(extra), "examples": extra[:10]})
    if changed:
        errors.append({"code": "NORMALIZED_VALUES_DIFFER", "count": len(changed), "examples": changed[:10]})
    if normalized_rounds != len(by_round):
        errors.append({"code": "NORMALIZED_ROUND_COUNT", "expected": len(by_round), "actual": normalized_rounds})
    return {
        "passed": not errors,
        "normalizedPlayerRows": len(actual),
        "normalizedRounds": normalized_rounds,
        "errors": errors,
    }


def record_game_integrity(
    conn: sqlite3.Connection,
    event_id: int,
    match_id: str,
    game_id: int,
    *,
    raw_status: str,
    normalization_status: str,
    integrity_status: str,
    analytics_ready: bool,
    expected_player_rows: int,
    normalized_player_rows: int,
    expected_rounds: int,
    normalized_rounds: int,
    checks: dict[str, Any],
    source_payload_hash: str | None = None,
) -> None:
    ensure_integrity_schema(conn)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO game_data_integrity(
            event_id, match_id, game_id, integrity_version, raw_status,
            normalization_status, integrity_status, analytics_ready,
            expected_player_rows, normalized_player_rows, expected_rounds,
            normalized_rounds, source_payload_hash, checks_json, checked_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id, match_id, game_id) DO UPDATE SET
            integrity_version=excluded.integrity_version,
            raw_status=excluded.raw_status,
            normalization_status=excluded.normalization_status,
            integrity_status=excluded.integrity_status,
            analytics_ready=excluded.analytics_ready,
            expected_player_rows=excluded.expected_player_rows,
            normalized_player_rows=excluded.normalized_player_rows,
            expected_rounds=excluded.expected_rounds,
            normalized_rounds=excluded.normalized_rounds,
            source_payload_hash=excluded.source_payload_hash,
            checks_json=excluded.checks_json,
            checked_at=excluded.checked_at
        """,
        (event_id, str(match_id), game_id, INTEGRITY_VERSION, raw_status,
         normalization_status, integrity_status, 1 if analytics_ready else 0,
         expected_player_rows, normalized_player_rows, expected_rounds,
         normalized_rounds, source_payload_hash, json.dumps(checks, sort_keys=True), now),
    )
    conn.execute(
        """UPDATE data_integrity_issues SET resolved_at=?
           WHERE event_id=? AND match_id=? AND game_id=? AND resolved_at IS NULL""",
        (now, event_id, str(match_id), game_id),
    )
    for error in checks.get("errors", []):
        conn.execute(
            """
            INSERT INTO data_integrity_issues(
                event_id, match_id, game_id, integrity_version, issue_code,
                severity, details_json, detected_at
            ) VALUES (?, ?, ?, ?, ?, 'ERROR', ?, ?)
            """,
            (event_id, str(match_id), game_id, INTEGRITY_VERSION,
             str(error.get("code") or "UNKNOWN"), json.dumps(error, sort_keys=True), now),
        )


def game_is_analytics_ready(conn: sqlite3.Connection, event_id: int, match_id: str, game_id: int) -> bool:
    ensure_integrity_schema(conn)
    row = conn.execute(
        """SELECT analytics_ready FROM game_data_integrity
           WHERE event_id=? AND match_id=? AND game_id=?""",
        (event_id, str(match_id), game_id),
    ).fetchone()
    return bool(row and row[0])


def integrity_summary(conn: sqlite3.Connection, event_id: int | None = None) -> dict[str, Any]:
    ensure_integrity_schema(conn)
    where = "WHERE event_id=?" if event_id is not None else ""
    params = (event_id,) if event_id is not None else ()
    rows = conn.execute(
        f"SELECT integrity_status, COUNT(*) AS count FROM game_data_integrity {where} GROUP BY integrity_status",
        params,
    ).fetchall()
    counts = {str(row[0]): int(row[1]) for row in rows}
    games = conn.execute(
        f"""SELECT event_id, match_id, game_id, integrity_status, analytics_ready,
                   expected_player_rows, normalized_player_rows, expected_rounds,
                   normalized_rounds, checks_json, checked_at
            FROM game_data_integrity {where}
            ORDER BY checked_at DESC LIMIT 500""",
        params,
    ).fetchall()
    legacy_where = "AND pr.event_id=?" if event_id is not None else ""
    legacy_params = (event_id,) if event_id is not None else ()
    legacy_unverified = int(conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT pr.event_id, pr.match_id, pr.game_id
            FROM player_rounds pr
            LEFT JOIN game_data_integrity gdi
              ON gdi.event_id=pr.event_id
             AND gdi.match_id=pr.match_id
             AND gdi.game_id=pr.game_id
             AND gdi.integrity_version=?
             AND gdi.analytics_ready=1
            WHERE gdi.event_id IS NULL {legacy_where}
        )
        """,
        (INTEGRITY_VERSION, *legacy_params),
    ).fetchone()[0])
    return {
        "integrityVersion": INTEGRITY_VERSION,
        "counts": counts,
        "analyticsReady": counts.get(READY, 0),
        "blocked": counts.get(QUARANTINED, 0),
        "partial": counts.get(PARTIAL, 0),
        "legacyUnverifiedGames": legacy_unverified,
        "migrationReady": legacy_unverified == 0 and counts.get(QUARANTINED, 0) == 0,
        "games": [dict(row) | {"checks": json.loads(row["checks_json"] or "{}")} for row in games],
    }


def record_artifact_lineage(
    conn: sqlite3.Connection,
    artifact_type: str,
    artifact_id: str,
    calculation_version: str,
    integrity_status: str,
    metadata: dict[str, Any] | None = None,
    source_fingerprint: str | None = None,
) -> None:
    ensure_integrity_schema(conn)
    conn.execute(
        """
        INSERT INTO derived_artifact_lineage(
            artifact_type, artifact_id, integrity_version, calculation_version,
            source_fingerprint, integrity_status, generated_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(artifact_type, artifact_id) DO UPDATE SET
            integrity_version=excluded.integrity_version,
            calculation_version=excluded.calculation_version,
            source_fingerprint=excluded.source_fingerprint,
            integrity_status=excluded.integrity_status,
            generated_at=excluded.generated_at,
            metadata_json=excluded.metadata_json
        """,
        (artifact_type, artifact_id, INTEGRITY_VERSION, calculation_version,
         source_fingerprint, integrity_status, utc_now(), json.dumps(metadata or {}, sort_keys=True)),
    )
