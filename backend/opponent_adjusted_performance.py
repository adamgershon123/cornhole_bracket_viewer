from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Any

from strength_of_competition import _competition_records


MINIMUM_GAMES = 20


def opponent_adjusted_ratings(
    conn: sqlite3.Connection,
    *,
    end_date: str | None = None,
) -> dict[int, dict[str, Any]]:
    records = [
        row for row in _competition_records(conn, end_date=end_date)
        if row.get("performanceVsExpected") is not None
    ]
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[int(row["playerId"])].append(row)
    rated = []
    for player_id, player_records in grouped.items():
        if len(player_records) < MINIMUM_GAMES:
            continue
        strong = [
            row for row in player_records
            if row["opponentTier"] in {"STRONG", "ELITE"}
        ]
        elite = [row for row in player_records if row["opponentTier"] == "ELITE"]
        overall_residual = _mean_residual(player_records)
        strong_residual = _mean_residual(strong)
        elite_residual = _mean_residual(elite)
        strong_confidence = len(strong) / (len(strong) + 20)
        signal = (
            (strong_residual if strong_residual is not None else overall_residual)
            * strong_confidence
        )
        rated.append({
            "playerId": player_id,
            "games": len(player_records),
            "strongOpponentGames": len(strong),
            "eliteOpponentGames": len(elite),
            "overallPprVsExpected": round(overall_residual, 4),
            "strongOpponentPprVsExpected": (
                round(strong_residual, 4) if strong_residual is not None else None
            ),
            "eliteOpponentPprVsExpected": (
                round(elite_residual, 4) if elite_residual is not None else None
            ),
            "strongOpponentSampleConfidence": round(strong_confidence, 4),
            "opponentAdjustedSignal": signal,
            "tierPerformance": {
                tier: _tier_summary(player_records, tier)
                for tier in ("DEVELOPING", "AVERAGE", "ABOVE_AVERAGE", "STRONG", "ELITE")
            },
            "recentExamples": player_records[-10:][::-1],
        })
    ordered = sorted(rated, key=lambda row: row["opponentAdjustedSignal"])
    for index, row in enumerate(ordered):
        percentile = 100 * (index + 0.5) / len(ordered)
        row["opponentAdjustedRating"] = round(percentile)
        row["percentile"] = round(percentile, 1)
        row["label"] = _label(row["opponentAdjustedRating"])
        row["ratedPlayers"] = len(ordered)
        row["status"] = "DESCRIPTIVE"
        row["source"] = "ACTUAL_PPR_MINUS_PREGAME_EXPECTED_PPR_BY_OPPONENT_TIER"
    return {int(row["playerId"]): row for row in ordered}


def validate_opponent_adjustment(conn: sqlite3.Connection) -> dict[str, Any]:
    records = sorted(
        (
            row for row in _competition_records(conn)
            if row.get("performanceVsExpected") is not None
        ),
        key=lambda row: (
            row["eventDate"], row["eventId"], str(row["matchId"]), row["gameId"]
        ),
    )
    histories: dict[int, list[dict[str, Any]]] = defaultdict(list)
    predictions: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in records:
        player_id = int(row["playerId"])
        prior = histories[player_id]
        expected = float(row["playerExpectedPpr"])
        actual = float(row["actualPpr"])
        if len(prior) >= 10:
            predictions["rawExpectedPpr"].append((expected, actual))
            overall = _mean_residual(prior)
            overall_confidence = len(prior) / (len(prior) + 30)
            predictions["overallOpponentAdjusted"].append((
                expected + overall * overall_confidence,
                actual,
            ))
            same_tier = [
                item for item in prior
                if item["opponentTier"] == row["opponentTier"]
            ]
            tier_residual = _mean_residual(same_tier)
            if tier_residual is not None:
                tier_confidence = len(same_tier) / (len(same_tier) + 20)
                predictions["tierOpponentAdjusted"].append((
                    expected + tier_residual * tier_confidence,
                    actual,
                ))
        prior.append(row)
    metrics = {name: _metrics(values) for name, values in predictions.items()}
    raw = metrics["rawExpectedPpr"]
    overall = metrics["overallOpponentAdjusted"]
    supported = overall["mae"] < raw["mae"] and overall["rmse"] < raw["rmse"]
    return {
        "status": "COMPLETE",
        "validationVersion": "opponent-adjusted-ppr-chronological-v1",
        "cutoffPolicy": "ALL_EXPECTATIONS_AND_RESIDUALS_STRICTLY_PREGAME",
        "candidates": metrics,
        "selectedExpectedPprMethod": (
            "overallOpponentAdjusted" if supported else "rawExpectedPpr"
        ),
        "opponentAdjustmentStatus": "SUPPORTED" if supported else "REJECTED_FOR_NOW",
        "notes": [
            "Residual means actual game PPR minus the pregame Expected PPR.",
            "Each adjustment uses only that player's earlier residuals.",
            "Tier adjustment uses only earlier games against the same opponent tier.",
            "Lower MAE and RMSE are better.",
        ],
    }


def _mean_residual(rows: list[dict[str, Any]]) -> float | None:
    values = [
        float(row["performanceVsExpected"])
        for row in rows if row.get("performanceVsExpected") is not None
    ]
    return sum(values) / len(values) if values else None


def _tier_summary(rows: list[dict[str, Any]], tier: str) -> dict[str, Any]:
    selected = [row for row in rows if row["opponentTier"] == tier]
    residual = _mean_residual(selected)
    return {
        "games": len(selected),
        "pprVsExpected": round(residual, 4) if residual is not None else None,
        "sampleConfidence": round(len(selected) / (len(selected) + 20), 4),
    }


def _metrics(values: list[tuple[float, float]]) -> dict[str, Any]:
    if not values:
        return {"predictions": 0, "mae": None, "rmse": None, "bias": None}
    errors = [prediction - actual for prediction, actual in values]
    return {
        "predictions": len(values),
        "mae": round(sum(abs(error) for error in errors) / len(errors), 6),
        "rmse": round(math.sqrt(sum(error ** 2 for error in errors) / len(errors)), 6),
        "bias": round(sum(errors) / len(errors), 6),
    }


def _label(rating: int) -> str:
    if rating >= 90:
        return "Elite vs Strong Fields"
    if rating >= 75:
        return "Very Strong"
    if rating >= 60:
        return "Above Expected"
    if rating >= 40:
        return "As Expected"
    if rating >= 25:
        return "Below Expected"
    return "Below Expected vs Strong Fields"
