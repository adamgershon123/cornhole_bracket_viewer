from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any


METRICS = (
    ("seasonPpr", "Season PPR", "decimal"),
    ("seasonDpr", "Season DPR", "decimal"),
    ("opponentPpr", "Opponent PPR", "decimal"),
    ("roundWinRate", "Round win rate", "percent"),
    ("fourBaggerRate", "Four-bagger rate", "percent"),
    ("bagsInRate", "Bags in", "percent"),
    ("bagsOnRate", "Bags on", "percent"),
    ("bagsOffRate", "Bags off", "percent"),
)


def match_profile_trajectories(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    rounds: list[dict[str, Any]],
) -> dict[str, Any]:
    event = conn.execute(
        "SELECT event_date FROM events WHERE event_id=?",
        (int(event_id),),
    ).fetchone()
    if not event or not event["event_date"]:
        return {
            "status": "UNAVAILABLE",
            "reason": "EVENT_DATE_UNAVAILABLE",
            "players": [],
        }
    event_date = str(event["event_date"])
    season_start = _season_start(date.fromisoformat(event_date)).isoformat()
    player_ids = sorted({
        int(player["playerId"])
        for round_row in rounds
        for player in round_row.get("players") or []
        if player.get("playerId") not in (None, "")
    })
    players = [
        _player_trajectory(
            conn,
            player_id=player_id,
            event_date=event_date,
            season_start=season_start,
            rounds=rounds,
        )
        for player_id in player_ids
    ]
    return {
        "status": "READY" if players else "AWAITING_ROUND_DATA",
        "source": "CHEESEBAGGERS_CALCULATED_FROM_ACL_MATCH_ROUNDS",
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE",
        "eventDate": event_date,
        "seasonStart": season_start,
        "players": players,
        "livePolicy": (
            "General statistics update through the selected round. Population-relative "
            "profile ratings are recalculated after completed data is indexed."
        ),
    }


def _player_trajectory(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    event_date: str,
    season_start: str,
    rounds: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_rows = conn.execute(
        """
        SELECT gross_points, opponent_points, net_points, bags_in, bags_on,
               bags_off, four_bagger, round_result
        FROM player_rounds
        WHERE player_id=? AND event_date>=? AND event_date<?
        ORDER BY event_date,event_id,match_id,game_id,round_no
        """,
        (int(player_id), season_start, event_date),
    ).fetchall()
    totals = _empty_totals()
    for row in baseline_rows:
        _add_history_row(totals, row)
    baseline = _metrics(totals)
    current = dict(totals)
    snapshots = [{
        "round": 0,
        "metrics": _metric_rows(baseline, baseline),
        "matchRounds": 0,
    }]
    match_rounds = 0
    name = None
    for round_row in sorted(rounds, key=lambda item: int(item.get("round") or 0)):
        own = next(
            (
                player for player in round_row.get("players") or []
                if int(player.get("playerId") or -1) == int(player_id)
            ),
            None,
        )
        if own is not None:
            name = own.get("name") or name
            opponent = next(
                (
                    player for player in round_row.get("players") or []
                    if str(player.get("teamId")) != str(own.get("teamId"))
                ),
                None,
            )
            _add_live_round(current, own, opponent)
            match_rounds += 1
        snapshots.append({
            "round": int(round_row.get("round") or 0),
            "metrics": _metric_rows(baseline, _metrics(current)),
            "matchRounds": match_rounds,
        })
    player = conn.execute(
        "SELECT display_name FROM players WHERE player_id=?",
        (int(player_id),),
    ).fetchone()
    return {
        "playerId": int(player_id),
        "name": (player["display_name"] if player else None) or name or f"Player {player_id}",
        "baselineRounds": len(baseline_rows),
        "baseline": baseline,
        "snapshots": snapshots,
    }


def _metric_rows(
    baseline: dict[str, float | int | None],
    current: dict[str, float | int | None],
) -> list[dict[str, Any]]:
    rows = []
    for key, label, kind in METRICS:
        before = baseline.get(key)
        after = current.get(key)
        delta = (
            float(after) - float(before)
            if before is not None and after is not None else None
        )
        rows.append({
            "key": key,
            "label": label,
            "kind": kind,
            "before": _round(before),
            "current": _round(after),
            "delta": _round(delta),
            "direction": _direction(delta, kind),
            "impact": _impact(delta, kind),
        })
    return rows


def _empty_totals() -> dict[str, float]:
    return {
        "rounds": 0, "points": 0, "opponentPoints": 0, "netPoints": 0,
        "bagsIn": 0, "bagsOn": 0, "bagsOff": 0, "fourBaggers": 0,
        "roundsWon": 0, "roundsLost": 0, "roundsTied": 0,
    }


def _add_history_row(totals: dict[str, float], row: sqlite3.Row) -> None:
    totals["rounds"] += 1
    totals["points"] += float(row["gross_points"] or 0)
    totals["opponentPoints"] += float(row["opponent_points"] or 0)
    totals["netPoints"] += float(row["net_points"] or 0)
    totals["bagsIn"] += int(row["bags_in"] or 0)
    totals["bagsOn"] += int(row["bags_on"] or 0)
    totals["bagsOff"] += int(row["bags_off"] or 0)
    totals["fourBaggers"] += int(row["four_bagger"] or 0)
    result = str(row["round_result"] or "")
    totals["roundsWon"] += int(result == "W")
    totals["roundsLost"] += int(result == "L")
    totals["roundsTied"] += int(result == "T")


def _add_live_round(
    totals: dict[str, float],
    own: dict[str, Any],
    opponent: dict[str, Any] | None,
) -> None:
    own_points = float(own.get("grossPoints") or 0)
    opponent_points = float((opponent or {}).get("grossPoints") or 0)
    totals["rounds"] += 1
    totals["points"] += own_points
    totals["opponentPoints"] += opponent_points
    totals["netPoints"] += own_points - opponent_points
    totals["bagsIn"] += int(own.get("bagsIn") or 0)
    totals["bagsOn"] += int(own.get("bagsOn") or 0)
    totals["bagsOff"] += int(own.get("bagsOff") or 0)
    totals["fourBaggers"] += int(bool(own.get("fourBagger") or int(own.get("bagsIn") or 0) == 4))
    totals["roundsWon"] += int(own_points > opponent_points)
    totals["roundsLost"] += int(own_points < opponent_points)
    totals["roundsTied"] += int(own_points == opponent_points)


def _metrics(totals: dict[str, float]) -> dict[str, float | int | None]:
    rounds = int(totals["rounds"])
    bags = int(totals["bagsIn"] + totals["bagsOn"] + totals["bagsOff"])
    return {
        "rounds": rounds,
        "seasonPpr": totals["points"] / rounds if rounds else None,
        "seasonDpr": totals["netPoints"] / rounds if rounds else None,
        "opponentPpr": totals["opponentPoints"] / rounds if rounds else None,
        "roundWinRate": 100 * totals["roundsWon"] / rounds if rounds else None,
        "fourBaggerRate": 100 * totals["fourBaggers"] / rounds if rounds else None,
        "bagsInRate": 100 * totals["bagsIn"] / bags if bags else None,
        "bagsOnRate": 100 * totals["bagsOn"] / bags if bags else None,
        "bagsOffRate": 100 * totals["bagsOff"] / bags if bags else None,
    }


def _direction(delta: float | None, kind: str) -> str:
    if delta is None:
        return "UNKNOWN"
    epsilon = 0.005 if kind == "decimal" else 0.05
    if delta > epsilon:
        return "UP"
    if delta < -epsilon:
        return "DOWN"
    return "FLAT"


def _impact(delta: float | None, kind: str) -> dict[str, Any]:
    if delta is None:
        return {"score": None, "label": "Unknown"}
    magnitude = abs(delta)
    scale = 0.05 if kind == "decimal" else 1.0
    score = min(round(100 * magnitude / scale), 100)
    label = "Major" if score >= 75 else "Notable" if score >= 35 else "Small" if score >= 10 else "Minimal"
    return {"score": score, "label": label}


def _round(value: Any) -> float | int | None:
    if value is None:
        return None
    return round(float(value), 4)


def _season_start(value: date) -> date:
    return date(value.year if value.month >= 9 else value.year - 1, 9, 1)
