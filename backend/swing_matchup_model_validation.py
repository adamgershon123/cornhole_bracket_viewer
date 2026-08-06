from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any

from chronological_evaluation import _metric_summary
from holdout_evaluation import (
    _prediction_rows,
    build_evaluation_dataset,
    fit_logistic,
    logistic_probability,
)
from rolling_origin_evaluation import rolling_origin_folds
from swing_performance import swing_performance_ratings


SWING_FEATURES = {
    "avoidance": "swingAvoidanceDelta",
    "resilience": "swingResilienceDelta",
    "surprise": "swingSurpriseDelta",
    "exposure": "swingExposureDelta",
    "recovery": "swingRecoveryDelta",
}


def validate_swing_matchup_features(
    conn: sqlite3.Connection,
    *,
    minimum_development_dates: int = 10,
    test_dates_per_fold: int = 5,
) -> dict[str, Any]:
    examples = build_evaluation_dataset(conn, window_days=365)
    _add_cutoff_safe_swing_features(conn, examples)
    candidates = {
        "pprPlusSwingAvoidance": ("pprDelta", SWING_FEATURES["avoidance"]),
        "pprPlusSwingResilience": ("pprDelta", SWING_FEATURES["resilience"]),
        "pprPlusSwingSurprise": ("pprDelta", SWING_FEATURES["surprise"]),
        "pprPlusSwingExposure": ("pprDelta", SWING_FEATURES["exposure"]),
        "pprPlusSwingRecovery": ("pprDelta", SWING_FEATURES["recovery"]),
        "pprPlusAllSwing": ("pprDelta", *SWING_FEATURES.values()),
        "bagEfficiencyPlusAllSwing": (
            "pprDelta", "fourBaggerDelta", "bagsInDelta", *SWING_FEATURES.values()
        ),
    }
    results = {}
    for name, feature_names in candidates.items():
        eligible = [
            example for example in examples
            if all(example["features"].get(feature) is not None for feature in feature_names)
        ]
        baseline_names = ("pprDelta",)
        bag_names = ("pprDelta", "fourBaggerDelta", "bagsInDelta")
        models = {
            "pprOnly": baseline_names,
            "bagEfficiency": bag_names,
            name: feature_names,
        }
        predictions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        folds = rolling_origin_folds(
            eligible,
            minimum_development_dates=minimum_development_dates,
            test_dates_per_fold=test_dates_per_fold,
        )
        evaluated_folds = 0
        for development, test, _metadata in folds:
            if not development or not test:
                continue
            evaluated_folds += 1
            for model_name, names in models.items():
                model = fit_logistic(development, feature_names=names, l2=0.1)
                predictions[model_name].extend(_prediction_rows(
                    test,
                    lambda example, fitted=model: logistic_probability(fitted, example),
                ))
        metrics = {
            model_name: _metric_summary(rows)
            for model_name, rows in predictions.items()
        }
        candidate_metrics = metrics[name]
        bag_metrics = metrics["bagEfficiency"]
        results[name] = {
            "eligibleMatchups": len(eligible),
            "coverageRate": round(len(eligible) / len(examples), 6) if examples else 0,
            "evaluatedFolds": evaluated_folds,
            "testMatchups": candidate_metrics["predictions"],
            "features": list(feature_names),
            "models": metrics,
            "changeVsBagEfficiency": {
                "brierScore": _difference(
                    candidate_metrics["brierScore"], bag_metrics["brierScore"]
                ),
                "logLoss": _difference(
                    candidate_metrics["logLoss"], bag_metrics["logLoss"]
                ),
                "accuracy": _difference(
                    candidate_metrics["accuracy"], bag_metrics["accuracy"]
                ),
            },
            "promotionStatus": (
                "SUPPORTED"
                if _improves(candidate_metrics, bag_metrics)
                else "REJECTED_FOR_NOW"
            ),
        }
    supported = [
        name for name, result in results.items()
        if result["promotionStatus"] == "SUPPORTED"
    ]
    return {
        "status": "COMPLETE",
        "validationVersion": "swing-matchup-rolling-origin-v1",
        "sourceMatchups": len(examples),
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE",
        "results": results,
        "supportedCandidates": supported,
        "decision": (
            f"Advance {', '.join(supported)} to prospective shadow testing."
            if supported
            else "Keep swing parameters descriptive; none improved both Brier score "
                 "and log loss over bag efficiency on its common eligible sample."
        ),
    }


def _add_cutoff_safe_swing_features(
    conn: sqlite3.Connection,
    examples: list[dict[str, Any]],
) -> None:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        by_date[str(example["eventDate"])].append(example)
    for event_date in sorted(by_date):
        ratings = swing_performance_ratings(conn, end_date=event_date)
        for example in by_date[event_date]:
            side_a = _side(ratings, example["sideAPlayerIds"])
            side_b = _side(ratings, example["sideBPlayerIds"])
            mapping = {
                "swingAvoidanceDelta": "largeSwingAvoidanceRating",
                "swingResilienceDelta": "largeSwingResilienceRating",
                "swingSurpriseDelta": "averageSwingSurprise",
                "swingExposureDelta": "largeSwingRate",
                "swingRecoveryDelta": "recoveryNetVsExpected",
            }
            for output, source in mapping.items():
                a_value = side_a.get(source)
                b_value = side_b.get(source)
                example["features"][output] = (
                    round(float(a_value) - float(b_value), 6)
                    if a_value is not None and b_value is not None else None
                )


def _side(
    ratings: dict[int, dict[str, Any]],
    player_ids: list[int],
) -> dict[str, float | None]:
    rows = [ratings.get(int(player_id)) for player_id in player_ids]
    fields = (
        "largeSwingAvoidanceRating",
        "largeSwingResilienceRating",
        "averageSwingSurprise",
        "largeSwingRate",
        "recoveryNetVsExpected",
    )
    result = {}
    for field in fields:
        values = [
            float(row[field]) for row in rows
            if row is not None and row.get(field) is not None
        ]
        result[field] = (
            sum(values) / len(values)
            if rows and len(values) == len(rows) else None
        )
    return result


def _difference(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return round(value - baseline, 6)


def _improves(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        candidate.get("brierScore") is not None
        and baseline.get("brierScore") is not None
        and candidate["brierScore"] < baseline["brierScore"]
        and candidate["logLoss"] < baseline["logLoss"]
    )


if __name__ == "__main__":
    from season_platform import db

    connection = db()
    try:
        print(json.dumps(validate_swing_matchup_features(connection), indent=2))
    finally:
        connection.close()
