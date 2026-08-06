from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from typing import Any


def validate_profile_ratings(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = [dict(row) for row in conn.execute(
        """
        SELECT player_id, event_date, gross_points, net_points, round_result
        FROM player_rounds WHERE event_date IS NOT NULL
        ORDER BY event_date, event_id, match_id, game_id, round_no
        """
    ).fetchall()]
    dates = sorted({row["event_date"] for row in rows})
    if len(dates) < 4:
        return {"status": "INSUFFICIENT_DATA"}
    split_date = dates[int(len(dates) * 0.7)]
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["player_id"])].append(row)
    windows = [(15, 30), (30, 90), (50, 180), (100, 365)]
    form_results = [
        _validate_form(grouped, split_date, rounds, days)
        for rounds, days in windows
    ]
    consistency = _validate_consistency(grouped, split_date)
    supported_form = [
        row for row in form_results
        if row["players"] >= 30
        and row["futurePprCorrelation"] is not None
        and row["futurePprCorrelation"] > 0.1
    ]
    best = max(supported_form, key=lambda row: row["futurePprCorrelation"], default=None)
    consistency_supported = (
        consistency["players"] >= 30
        and consistency["variationCorrelation"] is not None
        and consistency["variationCorrelation"] > 0.1
    )
    return {
        "status": "COMPLETE",
        "splitDate": split_date,
        "policy": "OLDEST_70_PERCENT_DATES_DEVELOPMENT_NEWEST_30_PERCENT_HOLDOUT",
        "currentFormWindows": form_results,
        "selectedCurrentFormWindow": (
            {"rounds": best["roundWindow"], "days": best["dayWindow"]}
            if best else None
        ),
        "currentFormStatus": "SUPPORTED" if best else "DESCRIPTIVE_ONLY",
        "consistency": consistency,
        "consistencyStatus": "SUPPORTED" if consistency_supported else "DESCRIPTIVE_ONLY",
        "notes": [
            "All development ratings use records before the split date.",
            "Holdout performance uses only records on or after the split date.",
            "Correlation measures ranking stability and does not by itself prove incremental matchup-model value.",
        ],
    }


def _validate_form(grouped: dict[int, list[dict[str, Any]]], split_date: str, round_window: int, day_window: int) -> dict[str, Any]:
    start = (date.fromisoformat(split_date) - timedelta(days=day_window)).isoformat()
    ppr_pairs, dpr_pairs = [], []
    for history in grouped.values():
        development = [row for row in history if row["event_date"] < split_date]
        recent = [row for row in development if row["event_date"] >= start][-round_window:]
        holdout = [row for row in history if row["event_date"] >= split_date]
        if len(development) < 50 or len(recent) < min(round_window, 15) or len(holdout) < 20:
            continue
        baseline = _mean(development, "gross_points")
        baseline_dpr = _mean(development, "net_points")
        reliability = len(recent) / (len(recent) + 30)
        ppr_signal = (_mean(recent, "gross_points") - baseline) * reliability
        dpr_signal = (_mean(recent, "net_points") - baseline_dpr) * reliability
        ppr_pairs.append((ppr_signal, _mean(holdout, "gross_points") - baseline))
        dpr_pairs.append((dpr_signal, _mean(holdout, "net_points") - baseline_dpr))
    return {
        "roundWindow": round_window,
        "dayWindow": day_window,
        "players": len(ppr_pairs),
        "futurePprCorrelation": _rounded(_correlation(ppr_pairs)),
        "futureDprCorrelation": _rounded(_correlation(dpr_pairs)),
    }


def _validate_consistency(grouped: dict[int, list[dict[str, Any]]], split_date: str) -> dict[str, Any]:
    pairs = []
    for history in grouped.values():
        development = [float(row["gross_points"] or 0) for row in history if row["event_date"] < split_date]
        holdout = [float(row["gross_points"] or 0) for row in history if row["event_date"] >= split_date]
        if len(development) < 50 or len(holdout) < 20:
            continue
        pairs.append((_stddev(development), _stddev(holdout)))
    return {
        "players": len(pairs),
        "variationCorrelation": _rounded(_correlation(pairs)),
        "interpretation": "Positive correlation means earlier round variation predicts later variation.",
    }


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key] or 0) for row in rows) / len(rows)


def _stddev(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mx) * (y - my) for x, y in pairs)
    denominator = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return numerator / denominator if denominator else None


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
