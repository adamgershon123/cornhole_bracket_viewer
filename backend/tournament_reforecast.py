from __future__ import annotations

import sqlite3
from statistics import mean
from typing import Any, Iterable


# Same-event evidence must earn influence. Forty player-rounds makes the event
# sample as influential as the pre-event baseline; a single round contributes
# only 1/41 of its observed departure from that baseline.
EVENT_FORM_PRIOR_ROUNDS = 40.0
MAX_EVENT_FORM_PPR_SHIFT = 1.5


def checkpoint_team_form(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    teams: list[dict[str, Any]],
    completed_match_ids: Iterable[str | int],
    historical_team_ppr: dict[str, float | None],
) -> dict[str, dict[str, Any]]:
    """Return leakage-safe, sample-weighted team strength at a checkpoint.

    Only match IDs explicitly completed at the checkpoint are eligible. This
    remains safe when replaying an already-completed historical tournament,
    because later event rows cannot enter an earlier checkpoint.
    """
    match_ids = sorted({str(value) for value in completed_match_ids if value not in (None, "")})
    if not match_ids:
        return {
            str(team["teamId"]): _empty_form(historical_team_ppr.get(str(team["teamId"])))
            for team in teams
        }

    placeholders = ",".join("?" for _ in match_ids)
    rows = conn.execute(
        f"""
        SELECT player_id,
               COUNT(*) AS rounds,
               SUM(COALESCE(gross_points, 0)) AS gross_points,
               SUM(CASE WHEN UPPER(COALESCE(round_result, ''))='W' THEN 1 ELSE 0 END) AS rounds_won,
               SUM(CASE WHEN UPPER(COALESCE(round_result, ''))='L' THEN 1 ELSE 0 END) AS rounds_lost,
               SUM(COALESCE(four_bagger, 0)) AS four_baggers,
               SUM(COALESCE(net_points, 0)) AS net_points
        FROM player_rounds
        WHERE event_id=? AND CAST(match_id AS TEXT) IN ({placeholders})
        GROUP BY player_id
        """,
        (int(event_id), *match_ids),
    ).fetchall()
    by_player = {int(row["player_id"]): row for row in rows}
    output: dict[str, dict[str, Any]] = {}
    for team in teams:
        team_id = str(team["teamId"])
        baseline = historical_team_ppr.get(team_id)
        players = []
        for player_id in team.get("playerIds") or []:
            row = by_player.get(int(player_id))
            if not row:
                continue
            rounds = int(row["rounds"] or 0)
            gross = float(row["gross_points"] or 0)
            players.append({
                "playerId": int(player_id),
                "rounds": rounds,
                "ppr": round(gross / rounds, 4) if rounds else None,
                "roundWinRate": round(float(row["rounds_won"] or 0) / rounds, 6) if rounds else None,
                "roundLossRate": round(float(row["rounds_lost"] or 0) / rounds, 6) if rounds else None,
                "fourBaggerRate": round(float(row["four_baggers"] or 0) / rounds, 6) if rounds else None,
                "dpr": round(float(row["net_points"] or 0) / rounds, 4) if rounds else None,
            })
        player_pprs = [float(row["ppr"]) for row in players if row.get("ppr") is not None]
        event_ppr = mean(player_pprs) if player_pprs else None
        rounds = sum(int(row["rounds"]) for row in players)
        reliability = rounds / (rounds + EVENT_FORM_PRIOR_ROUNDS) if rounds else 0.0
        raw_delta = event_ppr - baseline if event_ppr is not None and baseline is not None else 0.0
        applied_delta = max(-MAX_EVENT_FORM_PPR_SHIFT, min(MAX_EVENT_FORM_PPR_SHIFT, reliability * raw_delta))
        output[team_id] = {
            "historicalPpr": round(float(baseline), 4) if baseline is not None else None,
            "eventPpr": round(float(event_ppr), 4) if event_ppr is not None else None,
            "eventRounds": rounds,
            "sampleWeight": round(reliability, 6),
            "rawPprDelta": round(raw_delta, 4),
            "appliedPprDelta": round(applied_delta, 4),
            "adjustedPpr": round(float(baseline) + applied_delta, 4) if baseline is not None else None,
            "players": players,
        }
    return output


def _empty_form(baseline: float | None) -> dict[str, Any]:
    return {
        "historicalPpr": round(float(baseline), 4) if baseline is not None else None,
        "eventPpr": None,
        "eventRounds": 0,
        "sampleWeight": 0.0,
        "rawPprDelta": 0.0,
        "appliedPprDelta": 0.0,
        "adjustedPpr": round(float(baseline), 4) if baseline is not None else None,
        "players": [],
    }
