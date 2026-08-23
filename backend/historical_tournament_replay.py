from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from bracket_prediction_snapshots import _init_schema as init_snapshot_schema
from bracket_prediction_snapshots import _save_snapshot
from bracket_simulation import _extract_teams, simulate_bracket


REPLAY_VERSION = "historical-tournament-replay-v2-published-graph"
REPLAY_SNAPSHOT_TYPE = "PREGAME_V2"
REPLAY_STATE_KEY = "PREGAME::STRUCTURE_V2"
DEFAULT_SIMULATIONS = 2_000
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def start_historical_tournament_replay_worker(
    db_factory: Callable[[], sqlite3.Connection],
    *,
    data_dir: str | Path,
    simulations: int = DEFAULT_SIMULATIONS,
) -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True

    def run() -> None:
        time.sleep(20)
        while True:
            try:
                candidates = _candidate_brackets(db_factory, data_dir=data_dir)
                with db_factory() as conn:
                    _init_schema(conn)
                    _update_state(conn, discovered=len(candidates), status="RUNNING")
                if not candidates:
                    with db_factory() as conn:
                        _update_state(conn, discovered=0, status="CURRENT")
                    time.sleep(300)
                    continue
                for event_id, path in candidates:
                    try:
                        payload = _read_bracket_payload(path)
                        with db_factory() as conn:
                            result = replay_historical_tournament(
                                conn,
                                payload,
                                simulations=simulations,
                            )
                            _record_result(conn, event_id, result)
                    except Exception as exc:
                        with db_factory() as conn:
                            _record_failure(conn, event_id, str(exc))
                    time.sleep(0.2)
            except Exception as exc:
                print(f"Historical tournament replay scan failed: {exc}", flush=True)
                time.sleep(60)

    threading.Thread(
        target=run,
        name="historical-tournament-replay",
        daemon=True,
    ).start()


def replay_historical_tournament(
    conn: sqlite3.Connection,
    bracket: dict[str, Any],
    *,
    simulations: int = DEFAULT_SIMULATIONS,
) -> dict[str, Any]:
    _init_schema(conn)
    info = bracket.get("eventInfo") or {}
    event_id = _integer(info.get("eventID") or info.get("leagueID"))
    event_date = str(
        info.get("startdate")
        or info.get("leagueStartDate")
        or info.get("leaguestartdate")
        or ""
    )[:10]
    details = [row for row in bracket.get("bracketDetails") or [] if isinstance(row, dict)]
    teams = _extract_teams(details)
    if not event_id or not event_date or len(teams) < 2:
        return {"status": "SKIPPED_INVALID_ROSTER", "eventId": event_id}
    existing = conn.execute(
        "SELECT 1 FROM bracket_prediction_snapshots WHERE event_id=? AND state_key=?",
        (event_id, REPLAY_STATE_KEY),
    ).fetchone()
    if existing:
        return {"status": "ALREADY_EXISTS", "eventId": event_id}
    clean_bracket = {
        **bracket,
        "bracketDetails": details,
    }
    champion_ids = _champion_player_ids(clean_bracket)
    if not champion_ids:
        return {"status": "SKIPPED_NO_CHAMPION", "eventId": event_id}
    result = simulate_bracket(
        conn,
        clean_bracket,
        simulations=simulations,
        # Do not select a template learned from a later event. The historical
        # replay uses the event's known field and double-elimination flag only.
        data_dir=None,
        completed_match_ids=[],
    )
    if result.get("status") not in {"COMPLETE", "SUCCESS"}:
        return {
            "status": "SKIPPED_SIMULATION",
            "eventId": event_id,
            "reason": result.get("status"),
        }
    payload = {
        **result,
        "snapshotOrigin": "HISTORICAL_REPLAY",
        "historicalReplayVersion": REPLAY_VERSION,
        "dataCutoffAt": f"{event_date}T00:00:00+00:00",
        "cutoffPolicy": "STRICTLY_BEFORE_EVENT_DATE",
    }
    _save_snapshot(
        conn, event_id, REPLAY_SNAPSHOT_TYPE, REPLAY_STATE_KEY, 0, None, payload
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO historical_tournament_replay_outcomes(
          event_id, champion_player_ids_json, resolved_at
        ) VALUES(?,?,?)
        """,
        (event_id, json.dumps(sorted(champion_ids)), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return {"status": "CREATED", "eventId": event_id}


def historical_tournament_replay_status(conn: sqlite3.Connection) -> dict[str, Any]:
    _init_schema(conn)
    row = conn.execute(
        "SELECT * FROM historical_tournament_replay_state WHERE state_id=1"
    ).fetchone()
    origins = conn.execute(
        """
        SELECT
          SUM(CASE WHEN snapshot_type=? THEN 1 ELSE 0 END) AS replayed,
          SUM(CASE WHEN snapshot_type='PREGAME' THEN 1 ELSE 0 END) AS live_frozen
        FROM bracket_prediction_snapshots WHERE snapshot_type IN ('PREGAME', ?)
        """,
        (REPLAY_SNAPSHOT_TYPE, REPLAY_SNAPSHOT_TYPE),
    ).fetchone()
    return {
        "status": row["status"] if row else "NOT_STARTED",
        "candidatesRemaining": int(row["candidates_remaining"] or 0) if row else 0,
        "created": int(row["created"] or 0) if row else 0,
        "failed": int(row["failed"] or 0) if row else 0,
        "lastEventId": int(row["last_event_id"]) if row and row["last_event_id"] else None,
        "lastError": row["last_error"] if row else None,
        "updatedAt": row["updated_at"] if row else None,
        "historicalReplaySnapshots": int(origins["replayed"] or 0),
        "liveFrozenSnapshots": int(origins["live_frozen"] or 0),
        "replayVersion": REPLAY_VERSION,
    }


def _candidate_brackets(db_factory, *, data_dir: str | Path) -> list[tuple[int, Path]]:
    root = Path(data_dir)
    paths = list(root.glob("event_*.json"))
    paths.extend((root / "season_platform" / "raw" / "brackets").glob("event_*.json"))
    with db_factory() as conn:
        init_snapshot_schema(conn)
        corrected = {
            int(row[0])
            for row in conn.execute(
                "SELECT event_id FROM bracket_prediction_snapshots WHERE state_key=?",
                (REPLAY_STATE_KEY,),
            )
        }
        legacy = {
            int(row[0])
            for row in conn.execute(
                """SELECT event_id FROM bracket_prediction_snapshots
                   WHERE snapshot_type='PREGAME'
                     AND json_extract(payload_json, '$.structure.mode')='SEEDED_SINGLE_ELIMINATION_ABSTRACTION'"""
            )
        }
    # Retain only the small path/date index. Keeping every decoded bracket in
    # this list can consume the worker's entire memory on a large archive.
    candidates: dict[int, tuple[str, Path]] = {}
    for path in paths:
        try:
            payload = _read_bracket_payload(path)
            info = payload.get("eventInfo") or {}
            event_id = _integer(info.get("eventID") or info.get("leagueID"))
            event_date = str(
                info.get("startdate")
                or info.get("leagueStartDate")
                or info.get("leaguestartdate")
                or ""
            )[:10]
            details = [row for row in payload.get("bracketDetails") or [] if isinstance(row, dict)]
            if not event_id or event_id not in legacy or event_id in corrected or len(_extract_teams(details)) < 2:
                continue
            if not _champion_player_ids({**payload, "bracketDetails": details}):
                continue
            candidates[event_id] = (event_date, path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    # Recent events generally have more complete pre-event player histories and
    # immediately grow the useful evaluation pool; older events follow behind.
    return [
        (event_id, path)
        for event_id, (_, path) in sorted(
            candidates.items(), key=lambda item: (item[1][0], item[0]), reverse=True
        )
    ]


def _read_bracket_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
        payload = payload["payload"]
    if not isinstance(payload, dict):
        raise ValueError("Bracket cache is not an object")
    return payload


def _has_completed_final(details: list[dict[str, Any]]) -> bool:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in details:
        if str(row.get("rounddesc") or "").strip().upper() == "FINAL":
            groups.setdefault(str(row.get("bracketmatchid")), []).append(row)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        games = rows[0].get("gameResults") or rows[1].get("gameResults") or []
        if any(_integer(game.get("matchStatusID")) == 5 for game in games if isinstance(game, dict)):
            return True
    return False


def _champion_player_ids(payload: dict[str, Any]) -> set[int]:
    details = [row for row in payload.get("bracketDetails") or [] if isinstance(row, dict)]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in details:
        if str(row.get("rounddesc") or "").strip().upper() == "FINAL":
            groups.setdefault(str(row.get("bracketmatchid")), []).append(row)
    completed = []
    for match_id, rows in groups.items():
        if len(rows) < 2:
            continue
        games = rows[0].get("gameResults") or rows[1].get("gameResults") or []
        games = [
            game for game in games
            if isinstance(game, dict) and _integer(game.get("matchStatusID")) == 5
        ]
        if games:
            completed.append((_integer(match_id) or 0, rows, games))
    if not completed:
        return set()
    _, rows, games = max(completed, key=lambda item: item[0])
    top = next((row for row in rows if str(row.get("bracketpos") or "").upper().endswith("T")), rows[0])
    bottom = next((row for row in rows if str(row.get("bracketpos") or "").upper().endswith("B")), rows[1])
    game = max(games, key=lambda row: _integer(row.get("gameID") or row.get("gameId")) or 0)
    home, away = _integer(game.get("scoreHome")), _integer(game.get("scoreAway"))
    if home is None or away is None or home == away:
        return set()
    winner = top if home > away else bottom
    return {
        player_id
        for player in winner.get("player_info") or []
        if (player_id := _integer(player.get("playerid") or player.get("id"))) is not None
    }


def _init_schema(conn: sqlite3.Connection) -> None:
    init_snapshot_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS historical_tournament_replay_state(
          state_id INTEGER PRIMARY KEY CHECK(state_id=1), status TEXT NOT NULL,
          candidates_remaining INTEGER NOT NULL DEFAULT 0,
          created INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
          last_event_id INTEGER, last_error TEXT, updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS historical_tournament_replay_outcomes(
          event_id INTEGER PRIMARY KEY, champion_player_ids_json TEXT NOT NULL,
          resolved_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _update_state(conn, *, discovered: int, status: str) -> None:
    _init_schema(conn)
    conn.execute(
        """
        INSERT INTO historical_tournament_replay_state(state_id,status,candidates_remaining,updated_at)
        VALUES(1,?,?,?)
        ON CONFLICT(state_id) DO UPDATE SET status=excluded.status,
          candidates_remaining=excluded.candidates_remaining, updated_at=excluded.updated_at
        """,
        (status, discovered, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _record_result(conn, event_id: int, result: dict[str, Any]) -> None:
    _init_schema(conn)
    created = result.get("status") == "CREATED"
    conn.execute(
        """
        UPDATE historical_tournament_replay_state
        SET candidates_remaining=MAX(0,candidates_remaining-1),
            created=created+?, last_event_id=?, last_error=NULL, updated_at=?
        WHERE state_id=1
        """,
        (int(created), event_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _record_failure(conn, event_id: int, error: str) -> None:
    _init_schema(conn)
    conn.execute(
        """
        UPDATE historical_tournament_replay_state
        SET candidates_remaining=MAX(0,candidates_remaining-1), failed=failed+1,
            last_event_id=?, last_error=?, updated_at=? WHERE state_id=1
        """,
        (event_id, error[:500], datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
