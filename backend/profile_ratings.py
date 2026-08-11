from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any


def profile_ratings(
    conn: sqlite3.Connection,
    minimum_rounds: int = 30,
    *,
    end_date: str | None = None,
) -> dict[int, dict[str, Any]]:
    rows = [dict(row) for row in conn.execute(
        """
        SELECT player_id, event_date, gross_points, net_points, round_result
        FROM player_rounds
        WHERE event_date IS NOT NULL AND (? IS NULL OR event_date < ?)
        ORDER BY player_id, event_date, event_id, match_id, game_id, round_no
        """,
        (end_date, end_date),
    ).fetchall()]
    latest = (
        date.fromisoformat(end_date)
        if end_date
        else max((date.fromisoformat(row["event_date"]) for row in rows), default=date.today())
    )
    recent_start = (latest - timedelta(days=365)).isoformat()
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["player_id"])].append(row)
    ratings = []
    for player_id, history in grouped.items():
        if len(history) < minimum_rounds:
            continue
        recent = [row for row in history if row["event_date"] >= recent_start][-100:]
        baseline = history[:-len(recent)] if recent and len(history) > len(recent) else history
        recent_stats, base_stats = _stats(recent), _stats(baseline)
        reliability = len(recent) / (len(recent) + 30)
        form_signal = (
            0.5 * (recent_stats["ppr"] - base_stats["ppr"])
            + 0.3 * (recent_stats["dpr"] - base_stats["dpr"])
            + 0.2 * 4 * (recent_stats["winRate"] - base_stats["winRate"])
        ) * reliability
        consistency_reliability = len(history) / (len(history) + 100)
        raw_consistency_stddev = _stddev(
            [float(row["gross_points"] or 0) for row in history]
        )
        ratings.append({
            "playerId": player_id,
            "recentRounds": len(recent),
            "baselineRounds": len(baseline),
            "consistencyRounds": len(history),
            "recentPpr": round(recent_stats["ppr"], 4),
            "baselinePpr": round(base_stats["ppr"], 4),
            "recentDpr": round(recent_stats["dpr"], 4),
            "baselineDpr": round(base_stats["dpr"], 4),
            "recentRoundWinRate": round(recent_stats["winRate"], 4),
            "baselineRoundWinRate": round(base_stats["winRate"], 4),
            "formReliability": round(reliability, 4),
            "formSignal": form_signal,
            "roundPprStdDev": round(raw_consistency_stddev, 4),
            "consistencyReliability": round(consistency_reliability, 4),
            "rawConsistencyVariance": raw_consistency_stddev ** 2,
            "recentWindow": "LAST_100_ROUNDS_WITHIN_365_DAYS",
        })
    # A small sample can look artificially stable by chance. Shrink every
    # player's observed variance toward the population's typical variance;
    # additional rounds progressively earn the right to move away from that
    # prior. The former formula multiplied -stddev by reliability, which
    # mistakenly rewarded low-confidence samples by pulling them toward zero.
    prior_variance = median(
        [float(row["rawConsistencyVariance"]) for row in ratings]
    ) if ratings else 0.0
    for row in ratings:
        reliability = float(row["consistencyReliability"])
        adjusted_variance = (
            reliability * float(row["rawConsistencyVariance"])
            + (1 - reliability) * prior_variance
        )
        row["adjustedRoundPprStdDev"] = round(math.sqrt(adjusted_variance), 4)
        row["consistencySignal"] = -math.sqrt(adjusted_variance)
        row["consistencyProvisional"] = int(row["consistencyRounds"]) < 100
        row.pop("rawConsistencyVariance", None)
    _assign_percentile(ratings, "formSignal", "currentFormRating")
    _assign_percentile(ratings, "consistencySignal", "consistencyRating")
    for row in ratings:
        row["currentFormLabel"] = _form_label(row["currentFormRating"])
        row["consistencyLabel"] = (
            "Provisional"
            if row["consistencyProvisional"]
            else _standard_label(row["consistencyRating"])
        )
        row["ratedPlayers"] = len(ratings)
    return {int(row["playerId"]): row for row in ratings}


def _stats(rows: list[dict[str, Any]]) -> dict[str, float]:
    count = len(rows)
    return {
        "ppr": sum(float(row["gross_points"] or 0) for row in rows) / count if count else 0,
        "dpr": sum(float(row["net_points"] or 0) for row in rows) / count if count else 0,
        "winRate": sum(row["round_result"] == "W" for row in rows) / count if count else 0,
    }


def _stddev(values: list[float]) -> float:
    if not values:
        return 0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _assign_percentile(rows: list[dict[str, Any]], key: str, output: str) -> None:
    ordered = sorted(rows, key=lambda row: row[key])
    count = len(ordered)
    for index, row in enumerate(ordered):
        row[output] = round(100 * (index + 0.5) / count) if count else 50


def _form_label(rating: int) -> str:
    if rating >= 85: return "On Fire"
    if rating >= 70: return "Hot"
    if rating >= 55: return "Trending Up"
    if rating >= 45: return "Steady"
    if rating >= 30: return "Trending Down"
    return "Cold"


def _standard_label(rating: int) -> str:
    if rating >= 90: return "Elite"
    if rating >= 75: return "Very Good"
    if rating >= 60: return "Above Average"
    if rating >= 40: return "Average"
    if rating >= 25: return "Below Average"
    return "Developing"
