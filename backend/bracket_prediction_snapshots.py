from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from bracket_simulation import _extract_teams, simulate_bracket

MAX_NEW_TIMELINE_SNAPSHOTS_PER_REQUEST = 12
LIVE_REFORECAST_VERSION = "checkpoint-event-form-double-dip-v2"


def has_valid_pregame_snapshot(conn: sqlite3.Connection, event_id: int) -> bool:
    _init_schema(conn)
    snapshot = _load_snapshot(conn, event_id, "PREGAME")
    # Frozen means immutable, including when the initial evidence was sparse.
    # Data-quality concerns are surfaced on that artifact; only the explicit
    # reset endpoint is allowed to remove and recreate it.
    return snapshot is not None


def delete_prediction_timeline(conn: sqlite3.Connection, event_id: int) -> int:
    """Explicitly remove a forecast timeline, including its frozen pregame artifact."""
    _init_schema(conn)
    cursor = conn.execute(
        "DELETE FROM bracket_prediction_snapshots WHERE event_id=?",
        (int(event_id),),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def bracket_roster_ready(bracket: dict[str, Any]) -> bool:
    return len(_extract_teams(bracket.get("bracketDetails") or [])) >= 2


def bracket_player_ids(bracket: dict[str, Any]) -> list[int]:
    return sorted({
        int(player_id)
        for team in _extract_teams(bracket.get("bracketDetails") or [])
        for player_id in team.get("playerIds") or []
    })


def bracket_history_readiness(
    conn: sqlite3.Connection,
    player_ids: list[int],
    *,
    minimum_rounds: int = 20,
    maximum_attempts: int = 2,
) -> dict[str, Any]:
    ready: list[int] = []
    retryable: list[int] = []
    exhausted: list[int] = []
    for player_id in player_ids:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM player_rounds WHERE player_id=?) AS rounds,
              COALESCE((SELECT attempt_count FROM player_history_queue WHERE player_id=?), 0) AS attempts
            """,
            (player_id, player_id),
        ).fetchone()
        rounds = int(row["rounds"] or 0)
        attempts = int(row["attempts"] or 0)
        if rounds >= minimum_rounds:
            ready.append(player_id)
        elif attempts >= maximum_attempts:
            exhausted.append(player_id)
        else:
            retryable.append(player_id)
    return {
        "ready": ready,
        "retryable": retryable,
        "exhausted": exhausted,
        "authoritativeReady": not retryable,
    }


def bracket_prediction_timeline(
    conn: sqlite3.Connection,
    bracket: dict[str, Any],
    *,
    simulations: int,
    data_dir: str | None,
    max_new_snapshots: int = MAX_NEW_TIMELINE_SNAPSHOTS_PER_REQUEST,
) -> dict[str, Any]:
    _init_schema(conn)
    event_info = bracket.get("eventInfo") or {}
    event_id = int(event_info.get("eventID") or event_info.get("leagueID") or 0)
    teams = _extract_teams(bracket.get("bracketDetails") or [])
    if not event_id or len(teams) < 2:
        return simulate_bracket(conn, bracket, simulations=simulations, data_dir=data_dir)

    roster_key = _hash({
        "teams": [
            {"teamId": team["teamId"], "playerIds": sorted(team["playerIds"])}
            for team in sorted(teams, key=lambda item: item["teamId"])
        ]
    })
    pregame = _load_snapshot(conn, event_id, "PREGAME")
    if pregame is None:
        result = simulate_bracket(conn, bracket, simulations=simulations, data_dir=data_dir)
        pregame = _save_snapshot(
            conn, event_id, "PREGAME", roster_key, 0, None, result
        )

    completed = completed_bracket_matches(bracket)
    loss_limit = 2 if any(
        str(row.get("bracketside") or "").upper() == "L"
        for row in bracket.get("bracketDetails") or []
    ) else 1
    losses: dict[str, int] = {}
    active_ids = {team["teamId"] for team in teams}
    timeline = [snapshot_summary(pregame, label="Pregame")]
    prefix: list[dict[str, Any]] = []
    current = pregame
    new_snapshots = 0
    checkpoint_indexes = _timeline_checkpoint_indexes(bracket, completed)
    for match_index, match in enumerate(completed):
        prefix.append(match)
        loser_id = match["loserTeamId"]
        losses[loser_id] = losses.get(loser_id, 0) + 1
        if losses[loser_id] >= loss_limit:
            active_ids.discard(loser_id)
        if match_index not in checkpoint_indexes:
            continue
        state_key = _hash({
            "roster": roster_key,
            "completed": prefix,
            "reforecastVersion": LIVE_REFORECAST_VERSION,
        })
        snapshot = _load_snapshot(conn, event_id, state_key)
        if snapshot is None:
            if new_snapshots >= max_new_snapshots:
                break
            if len(active_ids) == 1:
                result = _resolved_result(pregame["payload"], next(iter(active_ids)))
            else:
                result = simulate_bracket(
                    conn,
                    bracket,
                    # Timeline points are directional live updates, so 2,000
                    # iterations provide stable movement without forcing a
                    # completed 50+ match bracket through 500,000 simulations.
                    simulations=min(simulations, 2_000),
                    data_dir=data_dir,
                    eligible_team_ids=set(active_ids),
                    completed_match_ids=[row["matchId"] for row in prefix],
                )
            snapshot = _save_snapshot(
                conn,
                event_id,
                "LIVE",
                state_key,
                len(prefix),
                match,
                result,
            )
            new_snapshots += 1
        timeline.append(snapshot_summary(
            snapshot,
            label=f"After match {match['matchId']}",
            trigger_match=match,
        ))
        current = snapshot

    response = dict(current["payload"])
    applied_matches = int(current.get("completedMatches") or 0)
    timeline_complete = applied_matches >= len(completed)
    response.update({
        "snapshotMode": "FROZEN_TIMELINE",
        "frozenAt": pregame["createdAt"],
        "currentSnapshotAt": current["createdAt"],
        "completedMatchesApplied": applied_matches,
        "completedMatchesAvailable": len(completed),
        "timelineBuildStatus": "COMPLETE" if timeline_complete else "BUILDING",
        "pregameSnapshot": snapshot_summary(pregame, label="Pregame"),
        "timeline": timeline,
        "roundProgress": bracket_round_progress(bracket),
        "finalStandings": bracket_final_standings(bracket, completed),
        "liveReforecastVersion": LIVE_REFORECAST_VERSION,
    })
    conn.commit()
    return response


def bracket_round_progress(bracket: dict[str, Any]) -> list[dict[str, Any]]:
    """Summarize playable winner/loser matches into combined round pages."""
    groups = _playable_match_groups(bracket)
    rounds: dict[str, dict[str, Any]] = {}
    for rows in groups.values():
        description = str(rows[0].get("rounddesc") or "Bracket round")
        key, title = _round_identity(description)
        item = rounds.setdefault(key, {
            "key": key,
            "title": title,
            "totalMatches": 0,
            "completedMatches": 0,
        })
        item["totalMatches"] += 1
        if len(rows) >= 2 and _is_complete(rows[0], rows[1]):
            item["completedMatches"] += 1
    return sorted(rounds.values(), key=lambda item: (
        int(item["key"].split(":", 1)[1]) if item["key"].startswith("round:") else 10_000,
        _stage_sort(item["title"]),
    ))


def _playable_match_groups(bracket: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in bracket.get("bracketDetails") or []:
        match_id = row.get("bracketmatchid")
        if match_id not in (None, ""):
            groups.setdefault(str(match_id), []).append(row)
    return {
        match_id: rows
        for match_id, rows in groups.items()
        if len(rows) >= 2
        and not any(_is_bye(row) or _is_placeholder(row) for row in rows)
        and len({str(row.get("bracketteamid")) for row in rows}) >= 2
    }


def _round_identity(description: Any) -> tuple[str, str]:
    text = str(description or "Bracket round").strip()
    number_match = re.search(r"(\d+)", text)
    if number_match:
        number = number_match.group(1)
        return f"round:{number}", f"Round {number}"
    return f"stage:{text}", text


def _stage_sort(title: str) -> int:
    text = str(title or "").lower()
    if "quarter" in text or "qtr" in text:
        return 1
    if "semi" in text:
        return 2
    if "loser final" in text:
        return 3
    if text == "final":
        return 4
    return 5


def _timeline_checkpoint_indexes(
    bracket: dict[str, Any], completed: list[dict[str, Any]]
) -> set[int]:
    """Return round boundaries plus every meaningful late-bracket state.

    Once four teams remain, every elimination is its own forecast checkpoint.
    Championship games are always checkpoints because game one can force a
    reset without eliminating either finalist.
    """
    totals: dict[str, int] = {}
    for rows in _playable_match_groups(bracket).values():
        key, _ = _round_identity(rows[0].get("rounddesc"))
        totals[key] = totals.get(key, 0) + 1
    seen: dict[str, int] = {}
    checkpoints: set[int] = set()
    for index, match in enumerate(completed):
        # A round page is a rolling forecast, not a round-end-only forecast.
        # Persist every newly completed competitive game so probabilities can
        # move while the other games in that round are still being played.
        # The frontend collapses these into the latest state for the round.
        checkpoints.add(index)
        key, _ = _round_identity(match.get("roundDescription"))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= totals.get(key, 0) > 0:
            checkpoints.add(index)
    loss_limit = 2 if any(
        str(row.get("bracketside") or "").upper() == "L"
        for row in bracket.get("bracketDetails") or []
    ) else 1
    active = {team["teamId"] for team in _extract_teams(bracket.get("bracketDetails") or [])}
    losses: dict[str, int] = {}
    for index, match in enumerate(completed):
        loser_id = str(match["loserTeamId"])
        losses[loser_id] = losses.get(loser_id, 0) + 1
        if losses[loser_id] >= loss_limit:
            active.discard(loser_id)
            if len(active) <= 4:
                checkpoints.add(index)
        if match.get("isChampionshipGame"):
            checkpoints.add(index)
    if completed:
        checkpoints.add(len(completed) - 1)
    return checkpoints


def completed_bracket_matches(bracket: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in bracket.get("bracketDetails") or []:
        match_id = row.get("bracketmatchid")
        if match_id in (None, "") or _is_bye(row):
            continue
        groups.setdefault(str(match_id), []).append(row)
    matches = []
    for match_id, rows in groups.items():
        sides = {}
        for row in rows:
            team_id = row.get("bracketteamid")
            if team_id in (None, ""):
                continue
            position = str(row.get("bracketpos") or "")
            sides["T" if position.endswith("T") else "B"] = row
        if len(sides) != 2:
            continue
        top, bottom = sides.get("T"), sides.get("B")
        if not top or not bottom or not _is_complete(top, bottom):
            continue
        top_id, bottom_id = str(top["bracketteamid"]), str(bottom["bracketteamid"])
        round_description = top.get("rounddesc") or bottom.get("rounddesc") or "Bracket round"
        is_championship = bool(re.search(r"final|champ", str(round_description), re.I))
        game_results = top.get("gameResults") or bottom.get("gameResults") or []
        # Ordinary bracket matches produce one outcome. A double-elimination
        # championship can contain both game one and the if-necessary reset;
        # those must remain two independent forecast checkpoints.
        games = game_results if is_championship and len(game_results) > 1 else game_results[-1:]
        if not games:
            games = [{}]
        for game_index, game in enumerate(games, start=1):
            home = _number(game.get("scoreHome"))
            away = _number(game.get("scoreAway"))
            if home is None or away is None or home == away:
                scores = (top.get("scores") or bottom.get("scores") or [{}])[-1]
                home = _number(scores.get("scorehome"))
                away = _number(scores.get("scoreaway"))
            if home is None or away is None or home == away:
                continue
            winner, loser = (top_id, bottom_id) if home > away else (bottom_id, top_id)
            game_id = int(game.get("gameID") or game_index)
            matches.append({
                "matchId": match_id,
                "gameId": game_id,
                "resultKey": f"{match_id}:{game_id}",
                "winnerTeamId": winner,
                "loserTeamId": loser,
                "score": f"{int(home)}-{int(away)}",
                "completedAt": game.get("matchEndTime") or game.get("matchStartTime"),
                "roundDescription": round_description,
                "bracketSide": top.get("bracketside") or bottom.get("bracketside") or "",
                "isChampionshipGame": is_championship,
            })
    return sorted(matches, key=lambda item: (
        item.get("completedAt") or "",
        _match_number(item["matchId"]),
        int(item.get("gameId") or 0),
    ))


def bracket_final_standings(
    bracket: dict[str, Any], completed: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Return bracket-derived finishing order after the tournament resolves."""
    teams = _extract_teams(bracket.get("bracketDetails") or [])
    outcomes = completed if completed is not None else completed_bracket_matches(bracket)
    loss_limit = 2 if any(
        str(row.get("bracketside") or "").upper() == "L"
        for row in bracket.get("bracketDetails") or []
    ) else 1
    active = {team["teamId"] for team in teams}
    losses: dict[str, int] = {}
    eliminated: list[str] = []
    for outcome in outcomes:
        loser_id = str(outcome["loserTeamId"])
        losses[loser_id] = losses.get(loser_id, 0) + 1
        if losses[loser_id] >= loss_limit and loser_id in active:
            active.remove(loser_id)
            eliminated.append(loser_id)
    if len(active) != 1:
        return []
    names = {team["teamId"]: team for team in teams}
    ordered = [next(iter(active)), *reversed(eliminated)]
    return [
        {
            "place": index + 1,
            "teamId": team_id,
            "teamName": names.get(team_id, {}).get("teamName") or f"Team {team_id}",
            "players": names.get(team_id, {}).get("players") or [],
        }
        for index, team_id in enumerate(ordered)
    ]


def snapshot_summary(
    snapshot: dict[str, Any],
    *,
    label: str,
    trigger_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = snapshot["payload"]
    return {
        "label": label,
        "snapshotType": snapshot["snapshotType"],
        "createdAt": snapshot["createdAt"],
        "completedMatches": snapshot["completedMatches"],
        "triggerMatch": trigger_match or snapshot.get("triggerMatch"),
        "simulationCount": payload.get("simulationCount"),
        "coverage": payload.get("coverage"),
        "teams": [
            {
                "teamId": team["teamId"],
                "teamName": team["teamName"],
                "players": team.get("players") or [],
                "winEventProbability": team["winEventProbability"],
            }
            for team in payload.get("teams") or []
        ],
    }


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bracket_prediction_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            snapshot_type TEXT NOT NULL,
            state_key TEXT NOT NULL,
            completed_matches INTEGER NOT NULL DEFAULT 0,
            trigger_match_json TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(event_id, state_key)
        )
        """
    )


def _load_snapshot(
    conn: sqlite3.Connection, event_id: int, state_key: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM bracket_prediction_snapshots
        WHERE event_id=? AND (state_key=? OR snapshot_type=?)
        ORDER BY snapshot_id LIMIT 1
        """,
        (event_id, state_key, state_key),
    ).fetchone()
    if not row:
        return None
    return _row(row)


def _save_snapshot(
    conn: sqlite3.Connection,
    event_id: int,
    snapshot_type: str,
    state_key: str,
    completed_matches: int,
    trigger_match: dict[str, Any] | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO bracket_prediction_snapshots(
            event_id, snapshot_type, state_key, completed_matches,
            trigger_match_json, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, snapshot_type, state_key, completed_matches,
            json.dumps(trigger_match) if trigger_match else None,
            json.dumps(payload), created_at,
        ),
    )
    return _load_snapshot(conn, event_id, state_key) or {
        "snapshotType": snapshot_type,
        "completedMatches": completed_matches,
        "triggerMatch": trigger_match,
        "payload": payload,
        "createdAt": created_at,
    }


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "snapshotType": row["snapshot_type"],
        "completedMatches": int(row["completed_matches"]),
        "triggerMatch": json.loads(row["trigger_match_json"]) if row["trigger_match_json"] else None,
        "payload": json.loads(row["payload_json"]),
        "createdAt": row["created_at"],
    }


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _resolved_result(pregame: dict[str, Any], champion_id: str) -> dict[str, Any]:
    result = dict(pregame)
    result["generatedAt"] = datetime.now(timezone.utc).isoformat()
    result["status"] = "COMPLETE"
    result["teams"] = [
            {
                **team,
                "reachSemifinalProbability": 1.0,
                "reachFinalProbability": 1.0,
                "winEventProbability": 1.0,
            }
            for team in pregame.get("teams") or []
            if team["teamId"] == champion_id
        ]
    return result


def _is_complete(*rows: dict[str, Any]) -> bool:
    return any(
        int(row.get("matchStatusID") or 0) == 5
        or any(int(game.get("matchStatusID") or 0) == 5 for game in row.get("gameResults") or [])
        for row in rows
    )


def _is_bye(row: dict[str, Any]) -> bool:
    return any(
        str(player.get("firstname") or "").strip().lower() == "bye"
        or str(player.get("firstname") or "").strip().lower().startswith("bye user")
        for player in row.get("player_info") or []
    ) or str(row.get("bracketteamname") or "").strip().lower().startswith("bye")


def _is_placeholder(row: dict[str, Any]) -> bool:
    try:
        return int(row.get("bracketteamid")) <= 0
    except (TypeError, ValueError):
        return True


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _match_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _valid_frozen_roster(snapshot: dict[str, Any]) -> bool:
    teams = snapshot.get("payload", {}).get("teams") or []
    if len(teams) < 2:
        return False
    for team in teams:
        try:
            if int(team.get("teamId")) <= 0:
                return False
        except (TypeError, ValueError):
            return False
        if not team.get("playerIds") and not team.get("players"):
            return False
    return True


def _structure_only_snapshot_needs_refresh(
    conn: sqlite3.Connection,
    snapshot: dict[str, Any],
) -> bool:
    payload = snapshot.get("payload") or {}
    coverage = payload.get("coverage") or {}
    if float(coverage.get("modelCoverageRate") or 0) > 0:
        return False
    player_ids = sorted({
        int(player_id)
        for team in payload.get("teams") or []
        for player_id in team.get("playerIds") or []
    })
    if not player_ids:
        return False
    try:
        readiness = bracket_history_readiness(conn, player_ids)
    except sqlite3.OperationalError:
        return False
    # A zero-coverage snapshot is retained only after every missing player has
    # genuinely exhausted the configured retrieval attempts. If history now
    # exists, recalculate rather than preserving the obsolete fallback.
    return bool(readiness["ready"] or readiness["retryable"])
