from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from live_probability_evaluation import _rounds
from live_win_probability import FIRST_THROW_NET_EDGE


def clutch_ratings(conn: sqlite3.Connection, minimum_opportunities: int = 10, *, start_date: str | None = None, end_date: str | None = None) -> dict[int, dict[str, Any]]:
    clauses, params = [], []
    if start_date:
        clauses.append("e.event_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("e.event_date < ?")
        params.append(end_date)
    date_filter = f" AND {' AND '.join(clauses)}" if clauses else ""
    games = conn.execute(
        f"""
        SELECT g.event_id, g.match_id, g.game_id, g.home_team_id, g.away_team_id,
               g.home_score, g.away_score, e.event_date
        FROM games g JOIN events e ON e.event_id=g.event_id
        WHERE g.completed=1 AND e.event_date IS NOT NULL {date_filter}
        ORDER BY e.event_date, g.event_id, g.match_id, g.game_id
        """,
        params,
    ).fetchall()
    totals: dict[int, dict[str, Any]] = defaultdict(lambda: {
        "opportunities": 0, "adjustedNet": 0.0, "rawNet": 0,
        "scored": 0, "conceded": 0, "washes": 0,
    })
    for raw in games:
        game = dict(raw)
        for round_row in _rounds(conn, game):
            state = round_row.get("gameState") or {}
            scores = list((state.get("scoreBefore") or {}).values())
            if not scores or max(scores, default=0) < 15:
                continue
            if max(scores) - min(scores) > 5:
                continue
            scoring_team = state.get("roundScoringTeamId")
            first_team = state.get("firstThrowTeamId")
            net = int(state.get("netPoints") or 0)
            for player in round_row.get("players") or []:
                player_id = int(player["playerId"])
                team_id = str(player.get("teamId"))
                signed = net if scoring_team == team_id else -net if scoring_team else 0
                adjustment = (
                    FIRST_THROW_NET_EDGE if first_team == team_id
                    else -FIRST_THROW_NET_EDGE if first_team is not None
                    else 0.0
                )
                item = totals[player_id]
                item["opportunities"] += 1
                item["rawNet"] += signed
                item["adjustedNet"] += signed - adjustment
                item["scored"] += int(signed > 0)
                item["conceded"] += int(signed < 0)
                item["washes"] += int(signed == 0)

    baselines = {
        int(row[0]): float(row[1] or 0)
        for row in conn.execute(
            """
            SELECT player_id, AVG(net_points) FROM player_rounds
            WHERE (? IS NULL OR event_date >= ?) AND (? IS NULL OR event_date < ?)
            GROUP BY player_id
            """,
            (start_date, start_date, end_date, end_date),
        ).fetchall()
    }
    eligible = []
    for player_id, item in totals.items():
        opportunities = int(item["opportunities"])
        adjusted_mean = item["adjustedNet"] / opportunities
        delta = adjusted_mean - baselines.get(player_id, 0.0)
        reliability = opportunities / (opportunities + 30.0)
        item.update({
            "playerId": player_id,
            "adjustedNetPerRound": round(adjusted_mean, 4),
            "baselineNetPerRound": round(baselines.get(player_id, 0.0), 4),
            "performanceVsBaseline": round(delta, 4),
            "reliability": round(reliability, 4),
            "reliabilityAdjustedDelta": delta * reliability,
        })
        if opportunities >= minimum_opportunities:
            eligible.append(item)
    eligible.sort(key=lambda item: item["reliabilityAdjustedDelta"])
    count = len(eligible)
    for index, item in enumerate(eligible):
        percentile = (index + 0.5) / count if count else 0.5
        item["clutchRating"] = round(percentile * 100)
        item["percentile"] = round(percentile * 100, 1)
        item["label"] = _label(item["clutchRating"])
        item["ratedPlayers"] = count
    return {int(item["playerId"]): item for item in eligible}


def validate_clutch_rating(conn: sqlite3.Connection) -> dict[str, Any]:
    dates = [str(row[0]) for row in conn.execute(
        "SELECT DISTINCT event_date FROM events WHERE event_date IS NOT NULL ORDER BY event_date"
    ).fetchall()]
    if len(dates) < 4:
        return {"status": "INSUFFICIENT_DATA"}
    split_date = dates[int(len(dates) * 0.7)]
    development = clutch_ratings(conn, end_date=split_date)
    holdout = clutch_ratings(conn, start_date=split_date)
    common = sorted(set(development) & set(holdout))
    pairs = [(development[p]["reliabilityAdjustedDelta"], holdout[p]["reliabilityAdjustedDelta"]) for p in common]
    correlation = _correlation(pairs)
    return {
        "policy": "OLDEST_70_PERCENT_DATES_DEVELOPMENT_NEWEST_30_PERCENT_HOLDOUT",
        "splitDate": split_date,
        "developmentPlayers": len(development),
        "holdoutPlayers": len(holdout),
        "commonPlayers": len(common),
        "performanceCorrelation": round(correlation, 4) if correlation is not None else None,
        "status": "REPEATABLE" if correlation is not None and correlation > 0.15 and len(common) >= 30 else "DESCRIPTIVE_ONLY",
    }


def _label(rating: int) -> str:
    if rating >= 90: return "Elite"
    if rating >= 75: return "Very Good"
    if rating >= 60: return "Above Average"
    if rating >= 40: return "Average"
    if rating >= 25: return "Below Average"
    return "Developing"


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = (sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)) ** 0.5
    return numerator / denominator if denominator else None
