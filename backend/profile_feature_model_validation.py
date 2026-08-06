from __future__ import annotations

import math
import sqlite3
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from chronological_evaluation import _metric_summary
from holdout_evaluation import (
    _prediction_rows,
    build_evaluation_dataset,
    fit_logistic,
    logistic_probability,
)
from rolling_origin_evaluation import rolling_origin_folds


MODEL_CANDIDATES = {
    "pprOnly": ("pprDelta",),
    "pprPlusCurrentForm": ("pprDelta", "currentFormDelta"),
    "pprPlusConsistency": ("pprDelta", "consistencyDelta"),
    "pprPlusFormAndConsistency": (
        "pprDelta",
        "currentFormDelta",
        "consistencyDelta",
    ),
    "pprPlusTeamBalance": ("pprDelta", "partnerSkillGapDelta"),
    "pprPlusCarryDynamics": (
        "pprDelta",
        "partnerSkillGapDelta",
        "carryBurdenDelta",
        "weakLinkExposureDelta",
    ),
    "pprPlusScoringDistribution": (
        "pprDelta",
        "ceilingRateDelta",
        "floorAvoidanceDelta",
        "dprDelta",
    ),
    "pprPlusNonlinearScoringDistribution": (
        "pprDelta",
        "pprDeltaSignedSquare",
        "ceilingRateDelta",
        "ceilingRateDeltaSignedSquare",
        "floorAvoidanceDelta",
        "floorAvoidanceDeltaSignedSquare",
        "dprDelta",
        "dprDeltaSignedSquare",
    ),
    "pprPlusFormatAwareScoringDistribution": (
        "pprDelta",
        "ceilingRateDelta",
        "floorAvoidanceDelta",
        "dprDelta",
        "pprDeltaSingles",
        "pprDeltaDoubles",
        "pprDeltaBracketP",
        "pprDeltaBracketW",
        "ceilingRateDeltaSingles",
        "floorAvoidanceDeltaSingles",
        "dprDeltaSingles",
    ),
    "pprPlusBagEfficiency": (
        "pprDelta",
        "fourBaggerRateDelta",
        "bagsInRateDelta",
    ),
    "pprPlusBagEfficiencyAndScoringDistribution": (
        "pprDelta",
        "fourBaggerRateDelta",
        "bagsInRateDelta",
        "ceilingRateDelta",
        "floorAvoidanceDelta",
        "dprDelta",
    ),
    "advancedProfileChallenger": (
        "pprDelta",
        "currentFormDelta",
        "ceilingRateDelta",
        "floorAvoidanceDelta",
        "dprDelta",
        "weakLinkExposureDelta",
    ),
}

ENSEMBLE_SCORING_WEIGHTS = (0.25, 0.5, 0.75)


def validate_profile_features_in_matchup_model(
    conn: sqlite3.Connection,
    *,
    minimum_development_dates: int = 10,
    test_dates_per_fold: int = 5,
) -> dict[str, Any]:
    examples = build_evaluation_dataset(conn, window_days=365)
    _add_cutoff_safe_profile_features(conn, examples)
    _add_nonlinear_and_format_features(examples)
    common = [
        example
        for example in examples
        if example["features"].get("pprDelta") is not None
        and example["features"].get("currentFormDelta") is not None
        and example["features"].get("consistencyDelta") is not None
        and example["features"].get("partnerSkillGapDelta") is not None
        and example["features"].get("ceilingRateDelta") is not None
        and example["features"].get("floorAvoidanceDelta") is not None
        and example["features"].get("dprDelta") is not None
        and example["features"].get("fourBaggerRateDelta") is not None
        and example["features"].get("bagsInRateDelta") is not None
    ]
    folds = rolling_origin_folds(
        common,
        minimum_development_dates=minimum_development_dates,
        test_dates_per_fold=test_dates_per_fold,
    )
    predictions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evaluated_folds = 0
    test_matchups = 0
    for development, test, _metadata in folds:
        if not development or not test:
            continue
        evaluated_folds += 1
        test_matchups += len(test)
        fold_predictions: dict[str, list[dict[str, Any]]] = {}
        for name, features in MODEL_CANDIDATES.items():
            model = fit_logistic(development, feature_names=features, l2=0.1)
            fold_predictions[name] = _prediction_rows(
                test,
                lambda example, fitted=model: logistic_probability(fitted, example),
            )
            predictions[name].extend(fold_predictions[name])
        for scoring_weight in ENSEMBLE_SCORING_WEIGHTS:
            name = f"bagEfficiencyScoringBlend{int(scoring_weight * 100)}"
            blended = _blend_predictions(
                fold_predictions["pprPlusBagEfficiency"],
                fold_predictions["pprPlusScoringDistribution"],
                scoring_weight=scoring_weight,
            )
            predictions[name].extend(blended)
    results = {
        name: _metric_summary(predictions[name])
        for name in predictions
    }
    baseline = results["pprOnly"]
    for name, result in results.items():
        result["brierChangeVsPprOnly"] = _difference(
            result["brierScore"], baseline["brierScore"]
        )
        result["logLossChangeVsPprOnly"] = _difference(
            result["logLoss"], baseline["logLoss"]
        )
        result["accuracyChangeVsPprOnly"] = _difference(
            result["accuracy"], baseline["accuracy"]
        )
    qualifying = [
        name for name, result in results.items()
        if name != "pprOnly"
        and result["brierChangeVsPprOnly"] < 0
        and result["logLossChangeVsPprOnly"] < 0
        and result["accuracyChangeVsPprOnly"] >= 0
    ]
    best_name = (
        max(
            qualifying,
            key=lambda name: (
                results[name]["accuracy"],
                -results[name]["brierScore"],
                -results[name]["logLoss"],
            ),
        )
        if qualifying else "pprOnly"
    )
    best = results[best_name]
    supported = best_name != "pprOnly"
    deployment_model = (
        fit_logistic(
            common,
            feature_names=MODEL_CANDIDATES[best_name],
            l2=0.1,
        )
        if supported and best_name in MODEL_CANDIDATES
        else None
    )
    return {
        "status": "COMPLETE",
        "validationVersion": "profile-features-matchup-rolling-origin-v1",
        "sourceMatchups": len(examples),
        "commonEligibleMatchups": len(common),
        "coverageRate": round(len(common) / len(examples), 6) if examples else 0,
        "evaluatedFolds": evaluated_folds,
        "rollingTestMatchups": test_matchups,
        "candidates": results,
        "selectedCandidate": best_name if supported else "pprOnly",
        "selectionObjective": (
            "MAXIMIZE_ACCURACY_SUBJECT_TO_IMPROVED_BRIER_AND_LOG_LOSS"
        ),
        "deploymentCandidate": {
            "modelVersion": "scoring-distribution-challenger-v1",
            "status": "READY_FOR_PROSPECTIVE_SHADOW"
            if deployment_model else "NOT_AVAILABLE",
            "parameters": deployment_model,
        },
        "incrementalFeaturesStatus": "SUPPORTED" if supported else "REJECTED_FOR_NOW",
        "decision": (
            f"Use {best_name}; it improved both Brier score and log loss."
            if supported
            else "Keep Current Form and Consistency descriptive; neither earned "
                 "inclusion over PPR-only on both probability metrics."
        ),
        "notes": [
            "All player features use rounds strictly before the target event date.",
            "Every candidate is evaluated on the same common-eligibility matchups.",
            "Models are refitted independently on earlier dates for every fold.",
            "Lower Brier score and log loss are better; higher accuracy is better.",
            "Selection maximizes accuracy only among candidates that also improve both probability-quality metrics.",
            "Nonlinear terms use signed squares so reversing the two sides reverses the signal.",
            "Format interactions are trained inside each rolling fold and never use outcomes from later dates.",
        ],
    }


def _blend_predictions(
    bag_predictions: list[dict[str, Any]],
    scoring_predictions: list[dict[str, Any]],
    *,
    scoring_weight: float,
) -> list[dict[str, Any]]:
    if len(bag_predictions) != len(scoring_predictions):
        raise ValueError("Ensemble candidates must use the same matchup sample")
    rows = []
    for bag, scoring in zip(bag_predictions, scoring_predictions):
        bag_key = (bag.get("eventId"), bag.get("outcome"), bag.get("format"))
        scoring_key = (
            scoring.get("eventId"), scoring.get("outcome"), scoring.get("format")
        )
        if bag_key != scoring_key:
            raise ValueError("Ensemble candidate matchup order does not align")
        rows.append({
            **scoring,
            "probability": round(
                (1.0 - scoring_weight) * float(bag["probability"])
                + scoring_weight * float(scoring["probability"]),
                6,
            ),
        })
    return rows


def _add_nonlinear_and_format_features(
    examples: list[dict[str, Any]],
) -> None:
    for example in examples:
        features = example["features"]
        for name in (
            "pprDelta",
            "ceilingRateDelta",
            "floorAvoidanceDelta",
            "dprDelta",
        ):
            value = features.get(name)
            features[f"{name}SignedSquare"] = (
                float(value) * abs(float(value))
                if value is not None else None
            )

        match_type, _, bracket_type = str(
            example.get("format") or "UNKNOWN:UNKNOWN"
        ).partition(":")
        is_singles = 1.0 if match_type == "S" else 0.0
        is_doubles = 1.0 if match_type == "D" else 0.0
        is_bracket_p = 1.0 if bracket_type == "P" else 0.0
        is_bracket_w = 1.0 if bracket_type == "W" else 0.0

        def interaction(feature: str, indicator: float) -> float | None:
            value = features.get(feature)
            return float(value) * indicator if value is not None else None

        features["pprDeltaSingles"] = interaction("pprDelta", is_singles)
        features["pprDeltaDoubles"] = interaction("pprDelta", is_doubles)
        features["pprDeltaBracketP"] = interaction("pprDelta", is_bracket_p)
        features["pprDeltaBracketW"] = interaction("pprDelta", is_bracket_w)
        features["ceilingRateDeltaSingles"] = interaction(
            "ceilingRateDelta", is_singles
        )
        features["floorAvoidanceDeltaSingles"] = interaction(
            "floorAvoidanceDelta", is_singles
        )
        features["dprDeltaSingles"] = interaction("dprDelta", is_singles)


def _add_cutoff_safe_profile_features(
    conn: sqlite3.Connection,
    examples: list[dict[str, Any]],
) -> None:
    history_rows = [dict(row) for row in conn.execute(
        """
        SELECT player_id, event_date, gross_points, opponent_points, net_points,
               bags_in, bags_on, bags_off, four_bagger, round_result
        FROM player_rounds
        WHERE event_date IS NOT NULL
        ORDER BY event_date, event_id, match_id, game_id, round_no
        """
    ).fetchall()]
    histories: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in history_rows:
        histories[int(row["player_id"])].append(row)
    history_dates = {
        player_id: [str(row["event_date"]) for row in rows]
        for player_id, rows in histories.items()
    }
    cache: dict[tuple[int, str], dict[str, float] | None] = {}
    for example in examples:
        cutoff = str(example["eventDate"])
        side_values = []
        for key in ("sideAPlayerIds", "sideBPlayerIds"):
            values = [
                _player_signals(
                    histories.get(int(player_id), []),
                    history_dates.get(int(player_id), []),
                    cutoff,
                    cache,
                    int(player_id),
                )
                for player_id in example[key]
            ]
            side_values.append(values if values and all(value is not None for value in values) else None)
        if side_values[0] is None or side_values[1] is None:
            example["features"]["currentFormDelta"] = None
            example["features"]["consistencyDelta"] = None
            example["features"]["partnerSkillGapDelta"] = None
            example["features"]["carryBurdenDelta"] = None
            example["features"]["weakLinkExposureDelta"] = None
            continue
        side_a = side_values[0]
        side_b = side_values[1]
        example["features"]["currentFormDelta"] = (
            _side_mean(side_a, "form") - _side_mean(side_b, "form")
        )
        example["features"]["consistencyDelta"] = (
            _side_mean(side_a, "consistency") - _side_mean(side_b, "consistency")
        )
        side_a_ppr = [value["ppr"] for value in side_a]
        side_b_ppr = [value["ppr"] for value in side_b]
        dynamics_a = _side_dynamics(side_a_ppr, side_b_ppr)
        dynamics_b = _side_dynamics(side_b_ppr, side_a_ppr)
        example["features"]["partnerSkillGapDelta"] = (
            dynamics_a["partnerSkillGap"] - dynamics_b["partnerSkillGap"]
        )
        example["features"]["carryBurdenDelta"] = (
            dynamics_a["carryBurden"] - dynamics_b["carryBurden"]
        )
        example["features"]["weakLinkExposureDelta"] = (
            dynamics_a["weakLinkExposure"] - dynamics_b["weakLinkExposure"]
        )
        for feature, signal in (
            ("ceilingRateDelta", "ceilingRate"),
            ("floorAvoidanceDelta", "floorAvoidance"),
            ("dprDelta", "dpr"),
            ("fourBaggerRateDelta", "fourBaggerRate"),
            ("bagsInRateDelta", "bagsInRate"),
        ):
            example["features"][feature] = (
                _side_mean(side_a, signal) - _side_mean(side_b, signal)
            )


def _player_signals(
    history: list[dict[str, Any]],
    history_dates: list[str],
    cutoff: str,
    cache: dict[tuple[int, str], dict[str, float] | None],
    player_id: int,
) -> dict[str, float] | None:
    cache_key = (player_id, cutoff)
    if cache_key in cache:
        return cache[cache_key]
    cutoff_index = bisect_left(history_dates, cutoff)
    start = (date.fromisoformat(cutoff) - timedelta(days=365)).isoformat()
    start_index = bisect_left(history_dates, start, 0, cutoff_index)
    prior = history[:cutoff_index]
    recent = history[max(start_index, cutoff_index - 100):cutoff_index]
    if len(prior) < 30 or len(recent) < 15:
        cache[cache_key] = None
        return None
    baseline = prior[:-len(recent)] if len(prior) > len(recent) else prior
    recent_stats = _stats(recent)
    baseline_stats = _stats(baseline)
    reliability = len(recent) / (len(recent) + 30)
    form = (
        0.5 * (recent_stats[0] - baseline_stats[0])
        + 0.3 * (recent_stats[1] - baseline_stats[1])
        + 0.8 * (recent_stats[2] - baseline_stats[2])
    ) * reliability
    gross = [float(row["gross_points"] or 0) for row in prior]
    ppr = sum(gross) / len(gross)
    variation = _stddev(gross)
    consistency = -variation * (len(prior) / (len(prior) + 100))
    bag_rows = [
        row for row in prior
        if row.get("bags_in") is not None
        and row.get("bags_on") is not None
        and row.get("bags_off") is not None
    ]
    total_bags = sum(
        int(row["bags_in"]) + int(row["bags_on"]) + int(row["bags_off"])
        for row in bag_rows
    )
    cache[cache_key] = {
        "form": form,
        "consistency": consistency,
        "ppr": ppr,
        "dpr": sum(float(row["net_points"] or 0) for row in prior) / len(prior),
        "ceilingRate": sum(float(row["gross_points"] or 0) >= 10 for row in prior) / len(prior),
        "floorAvoidance": 1.0 - (
            sum(float(row["gross_points"] or 0) <= 5 for row in prior) / len(prior)
        ),
        "fourBaggerRate": (
            sum(int(row["four_bagger"] or 0) for row in bag_rows) / len(bag_rows)
            if bag_rows else 0.0
        ),
        "bagsInRate": (
            sum(int(row["bags_in"]) for row in bag_rows) / total_bags
            if total_bags else 0.0
        ),
    }
    return cache[cache_key]


def _side_mean(players: list[dict[str, float]], key: str) -> float:
    return sum(player[key] for player in players) / len(players)


def _side_dynamics(
    side_pprs: list[float],
    opponent_pprs: list[float],
) -> dict[str, float]:
    if not side_pprs or not opponent_pprs:
        return {
            "partnerSkillGap": 0.0,
            "carryBurden": 0.0,
            "weakLinkExposure": 0.0,
        }
    stronger = max(side_pprs)
    weaker = min(side_pprs)
    opponent = sum(opponent_pprs) / len(opponent_pprs)
    required = max(2 * opponent - weaker, 0.0)
    return {
        "partnerSkillGap": stronger - weaker if len(side_pprs) > 1 else 0.0,
        "carryBurden": max(required - stronger, 0.0) if len(side_pprs) > 1 else 0.0,
        "weakLinkExposure": max(opponent - weaker, 0.0) if len(side_pprs) > 1 else 0.0,
    }


def _stats(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
    count = len(rows)
    return (
        sum(float(row["gross_points"] or 0) for row in rows) / count,
        sum(float(row["net_points"] or 0) for row in rows) / count,
        sum(row["round_result"] == "W" for row in rows) / count,
    )


def _stddev(values: list[float]) -> float:
    center = sum(values) / len(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def _difference(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return round(value - baseline, 6)
