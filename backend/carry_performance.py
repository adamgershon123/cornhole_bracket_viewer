from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any


MINIMUM_SKILL_GAP = 0.5
MINIMUM_OPPORTUNITIES = 8


def carry_performance_ratings(
    conn: sqlite3.Connection,
    *,
    end_date: str | None = None,
) -> dict[int, dict[str, Any]]:
    records = _carry_records(conn, end_date=end_date)
    global_cover_rate = (
        sum(record["coveredDeficit"] for record in records) / len(records)
        if records else 0.5
    )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[int(record["playerId"])].append(record)
    rated = []
    for player_id, opportunities in grouped.items():
        if len(opportunities) < MINIMUM_OPPORTUNITIES:
            continue
        total_weight = sum(1 + record["carryBurden"] for record in opportunities)
        weighted_outperformance = sum(
            record["outperformance"] * (1 + record["carryBurden"])
            for record in opportunities
        ) / total_weight
        cover_rate = sum(record["coveredDeficit"] for record in opportunities) / len(opportunities)
        reliability = len(opportunities) / (len(opportunities) + 20)
        signal = (
            weighted_outperformance + 0.5 * (cover_rate - global_cover_rate)
        ) * reliability
        rated.append({
            "playerId": player_id,
            "opportunities": len(opportunities),
            "weightedOutperformance": round(weighted_outperformance, 4),
            "averageOutperformance": round(
                sum(record["outperformance"] for record in opportunities) / len(opportunities), 4
            ),
            "deficitCoverageRate": round(cover_rate, 4),
            "averageCarryBurden": round(
                sum(record["carryBurden"] for record in opportunities) / len(opportunities), 4
            ),
            "averagePartnerSkillGap": round(
                sum(record["partnerSkillGap"] for record in opportunities) / len(opportunities), 4
            ),
            "reliability": round(reliability, 4),
            "carrySignal": signal,
            "lastCarryDate": max(record["eventDate"] for record in opportunities),
            "recentExamples": opportunities[-10:][::-1],
        })
    ordered = sorted(rated, key=lambda row: row["carrySignal"])
    for index, row in enumerate(ordered):
        percentile = 100 * (index + 0.5) / len(ordered)
        row["carryRating"] = round(percentile)
        row["percentile"] = round(percentile, 1)
        row["label"] = _label(row["carryRating"])
        row["ratedPlayers"] = len(ordered)
        row["status"] = "DESCRIPTIVE_ONLY"
    return {int(row["playerId"]): row for row in ordered}


def validate_carry_performance(conn: sqlite3.Connection) -> dict[str, Any]:
    records = _carry_records(conn)
    dates = sorted({record["eventDate"] for record in records})
    if len(dates) < 4:
        return {"status": "INSUFFICIENT_DATA"}
    split_date = dates[int(len(dates) * 0.7)]
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[int(record["playerId"])].append(record)
    pairs = []
    for player_records in grouped.values():
        development = [row for row in player_records if row["eventDate"] < split_date]
        holdout = [row for row in player_records if row["eventDate"] >= split_date]
        if len(development) < MINIMUM_OPPORTUNITIES or len(holdout) < 4:
            continue
        development_signal = sum(row["outperformance"] for row in development) / len(development)
        holdout_signal = sum(row["outperformance"] for row in holdout) / len(holdout)
        pairs.append((development_signal, holdout_signal))
    correlation = _correlation(pairs)
    supported = len(pairs) >= 20 and correlation is not None and correlation > 0.1
    return {
        "status": "COMPLETE",
        "splitDate": split_date,
        "policy": "OLDEST_70_PERCENT_CARRY_DATES_DEVELOPMENT_NEWEST_30_PERCENT_HOLDOUT",
        "qualifiedPlayers": len(pairs),
        "carryOutperformanceCorrelation": (
            round(correlation, 4) if correlation is not None else None
        ),
        "predictionStatus": "SUPPORTED" if supported else "DESCRIPTIVE_ONLY",
        "notes": [
            "Expected PPR and stronger-partner status use only data before each game.",
            "A carry opportunity requires at least a 0.50 Expected PPR partner gap.",
            "The rating rewards personal PPR outperformance and covering the projected partner deficit.",
            "Predictive use requires at least 20 qualified players and positive holdout correlation above 0.10.",
        ],
    }


def _carry_records(
    conn: sqlite3.Connection,
    *,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in conn.execute(
        """
        SELECT player_id, event_id, match_id, game_id, team_id, event_date,
               gross_points
        FROM player_rounds
        WHERE event_date IS NOT NULL AND team_id IS NOT NULL
          AND (? IS NULL OR event_date < ?)
        ORDER BY event_date, event_id, match_id, game_id, round_no
        """,
        (end_date, end_date),
    ).fetchall()]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row["event_date"])].append(row)
    histories: dict[int, list[dict[str, Any]]] = defaultdict(list)
    records = []
    for event_date in sorted(by_date):
        cutoff = date.fromisoformat(event_date)
        season_start = date(cutoff.year if cutoff.month >= 9 else cutoff.year - 1, 9, 1)
        expected = {
            player_id: _season_ppr(history, season_start)
            for player_id, history in histories.items()
        }
        games: dict[tuple[Any, ...], dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for row in by_date[event_date]:
            key = (row["event_id"], str(row["match_id"]), row["game_id"])
            games[key][str(row["team_id"])].append(row)
        for game_key, teams in games.items():
            eligible_teams = []
            for team_id, team_rows in teams.items():
                player_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
                for row in team_rows:
                    player_rows[int(row["player_id"])].append(row)
                if len(player_rows) != 2 or any(expected.get(player_id) is None for player_id in player_rows):
                    continue
                eligible_teams.append((team_id, player_rows))
            if len(eligible_teams) != 2:
                continue
            for index, (_team_id, player_rows) in enumerate(eligible_teams):
                opponent_rows = eligible_teams[1 - index][1]
                opponent_expected = sum(float(expected[player_id]) for player_id in opponent_rows) / 2
                ordered = sorted(
                    ((player_id, float(expected[player_id])) for player_id in player_rows),
                    key=lambda item: item[1],
                    reverse=True,
                )
                (strong_id, strong_expected), (_weak_id, weak_expected) = ordered
                gap = strong_expected - weak_expected
                if gap < MINIMUM_SKILL_GAP:
                    continue
                actual = sum(
                    float(row["gross_points"] or 0) for row in player_rows[strong_id]
                ) / len(player_rows[strong_id])
                required = max(2 * opponent_expected - weak_expected, 0.0)
                burden = max(required - strong_expected, 0.0)
                records.append({
                    "playerId": strong_id,
                    "eventId": int(game_key[0]),
                    "matchId": str(game_key[1]),
                    "gameId": int(game_key[2]),
                    "eventDate": event_date,
                    "expectedPpr": round(strong_expected, 4),
                    "actualPpr": round(actual, 4),
                    "outperformance": round(actual - strong_expected, 4),
                    "partnerExpectedPpr": round(weak_expected, 4),
                    "partnerSkillGap": round(gap, 4),
                    "opponentExpectedPpr": round(opponent_expected, 4),
                    "requiredCarryPpr": round(required, 4),
                    "carryBurden": round(burden, 4),
                    "coveredDeficit": actual >= required,
                })
        for row in by_date[event_date]:
            histories[int(row["player_id"])].append(row)
    return records


def _season_ppr(history: list[dict[str, Any]], season_start: date) -> float | None:
    rows = [row for row in history if str(row["event_date"]) >= season_start.isoformat()]
    if len(rows) < 30:
        return None
    return sum(float(row["gross_points"] or 0) for row in rows) / len(rows)


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mx) * (y - my) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def _label(rating: int) -> str:
    if rating >= 90:
        return "Elite Carrier"
    if rating >= 75:
        return "Strong Carrier"
    if rating >= 60:
        return "Above Average"
    if rating >= 40:
        return "Average"
    if rating >= 25:
        return "Below Average"
    return "Developing"
