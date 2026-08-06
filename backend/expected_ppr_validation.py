from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from typing import Any


def validate_expected_ppr(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = [dict(row) for row in conn.execute(
        """
        SELECT player_id, event_id, match_id, game_id, event_date, gross_points
        FROM player_rounds
        WHERE event_date IS NOT NULL
        ORDER BY event_date, event_id, match_id, game_id, round_no
        """
    ).fetchall()]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row["event_date"])].append(row)
    history: dict[int, list[dict[str, Any]]] = defaultdict(list)
    predictions: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for event_date in sorted(by_date):
        cutoff = date.fromisoformat(event_date)
        season_start = date(cutoff.year if cutoff.month >= 9 else cutoff.year - 1, 9, 1)
        prior_season = [
            float(row["gross_points"] or 0)
            for player_rows in history.values()
            for row in player_rows
            if str(row["event_date"]) >= season_start.isoformat()
        ]
        population = sum(prior_season) / len(prior_season) if prior_season else 7.0
        targets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in by_date[event_date]:
            targets[(int(row["player_id"]), row["event_id"], str(row["match_id"]), row["game_id"])].append(row)
        for (player_id, *_), target_rows in targets.items():
            prior = history[player_id]
            season = [
                row for row in prior
                if str(row["event_date"]) >= season_start.isoformat()
            ]
            if len(season) < 30:
                continue
            actual = sum(float(row["gross_points"] or 0) for row in target_rows) / len(target_rows)
            season_ppr = _ppr(season)
            reliability = len(season) / (len(season) + 30)
            predictions["seasonPpr"].append((season_ppr, actual))
            predictions["reliabilityAdjustedSeason"].append((
                reliability * season_ppr + (1 - reliability) * population,
                actual,
            ))
            for name, days in (("last90Days", 90), ("last30Days", 30), ("last7Days", 7)):
                start = (cutoff - timedelta(days=days)).isoformat()
                recent = [row for row in prior if str(row["event_date"]) >= start]
                if recent:
                    predictions[name].append((_ppr(recent), actual))
            predictions["last100Rounds"].append((_ppr(prior[-100:]), actual))
        for row in by_date[event_date]:
            history[int(row["player_id"])].append(row)
    metrics = {name: _metrics(values) for name, values in predictions.items()}
    season = metrics["seasonPpr"]
    adjusted = metrics["reliabilityAdjustedSeason"]
    supported = (
        adjusted["rmse"] < season["rmse"]
        and adjusted["mae"] < season["mae"]
    )
    return {
        "status": "COMPLETE",
        "validationVersion": "expected-ppr-chronological-v1",
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE",
        "candidates": metrics,
        "selectedExpectedPprBaseline": (
            "reliabilityAdjustedSeason" if supported else "seasonPpr"
        ),
        "reliabilityAdjustmentStatus": "SUPPORTED" if supported else "REJECTED_FOR_NOW",
        "notes": [
            "Each target is a player's PPR in one future game.",
            "Every estimate uses only rounds dated before that game.",
            "Window candidates have different coverage and are not yet blended.",
            "Lower MAE and RMSE are better.",
        ],
    }


def _ppr(rows: list[dict[str, Any]]) -> float:
    return sum(float(row["gross_points"] or 0) for row in rows) / len(rows)


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
