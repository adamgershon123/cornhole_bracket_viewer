from __future__ import annotations

import math
import random
import sqlite3
from collections import defaultdict
from statistics import mean
from typing import Any, Callable

from baseline_predictions import score_matchup
from chronological_evaluation import _metric_summary, historical_matchups
from stage_a_features import build_matchup_features


HOLDOUT_VERSION = "holdout-v1"
LOGISTIC_FEATURES = (
    "pprDelta",
    "dprDelta",
    "bagsInDelta",
    "fourBaggerDelta",
    "roundWinDelta",
    "logRoundRatio",
    "partnershipDifference",
)


def build_evaluation_dataset(
    conn: sqlite3.Connection,
    *,
    window_days: int | None = 365,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    targets = historical_matchups(
        conn,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    examples: list[dict[str, Any]] = []
    for target in targets:
        matchup = build_matchup_features(
            conn,
            side_a_player_ids=target["sideAPlayerIds"],
            side_b_player_ids=target["sideBPlayerIds"],
            cutoff_at=f"{target['eventDate']}T00:00:00+00:00",
            window_days=window_days,
            include_acl_snapshots=False,
        )
        fixed = score_matchup(matchup, model_version="ppr-difference-v1")
        deltas = matchup["deltasAminusB"]
        rounds_a = int(matchup["sideA"]["coverage"]["rounds"] or 0)
        rounds_b = int(matchup["sideB"]["coverage"]["rounds"] or 0)
        vector = {
            "pprDelta": deltas.get("calculatedPpr"),
            "dprDelta": deltas.get("calculatedDpr"),
            "bagsInDelta": deltas.get("bagsInRate"),
            "fourBaggerDelta": deltas.get("fourBaggerRate"),
            "roundWinDelta": deltas.get("roundWinRate"),
            "logRoundRatio": math.log1p(rounds_a) - math.log1p(rounds_b),
            "partnershipDifference": (
                int(matchup["sideA"]["partnership"]["knownPartnership"])
                - int(matchup["sideB"]["partnership"]["knownPartnership"])
            ),
        }
        examples.append({
            **target,
            "evidenceTier": fixed["evidenceTier"],
            "fixedPprProbability": fixed["sideAProbability"],
            "fixedPprStatus": fixed["status"],
            "modelReady": matchup["modelReady"],
            "features": vector,
        })
    return examples


def chronological_split(
    examples: list[dict[str, Any]],
    *,
    development_fraction: float = 0.7,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    if not 0 < development_fraction < 1:
        raise ValueError("development_fraction must be between zero and one")
    dates = sorted({str(example["eventDate"]) for example in examples})
    if len(dates) < 2:
        raise ValueError("At least two event dates are required for a holdout split")
    development_date_count = min(
        max(int(len(dates) * development_fraction), 1),
        len(dates) - 1,
    )
    holdout_start = dates[development_date_count]
    development = [
        example for example in examples if str(example["eventDate"]) < holdout_start
    ]
    holdout = [
        example for example in examples if str(example["eventDate"]) >= holdout_start
    ]
    return development, holdout, holdout_start


def _vector(
    example: dict[str, Any],
    feature_names: tuple[str, ...] = LOGISTIC_FEATURES,
) -> list[float] | None:
    if not example.get("modelReady", True):
        return None
    values = example["features"]
    if values.get("pprDelta") is None:
        return None
    return [
        float(values.get(name) or 0.0)
        for name in feature_names
    ]


def fit_logistic(
    examples: list[dict[str, Any]],
    *,
    feature_names: tuple[str, ...],
    l2: float = 0.1,
    iterations: int = 2500,
    learning_rate: float = 0.05,
) -> dict[str, Any]:
    rows = [
        (_vector(example, feature_names), int(example["sideAWon"]))
        for example in examples
    ]
    rows = [(values, outcome) for values, outcome in rows if values is not None]
    if not rows:
        raise ValueError("No eligible development examples")
    columns = list(zip(*(values for values, _ in rows)))
    means = [mean(column) for column in columns]
    scales = [
        math.sqrt(mean((value - center) ** 2 for value in column)) or 1.0
        for column, center in zip(columns, means)
    ]
    standardized = [
        (
            [(value - center) / scale for value, center, scale in zip(values, means, scales)],
            outcome,
        )
        for values, outcome in rows
    ]
    weights = [0.0] * len(feature_names)
    intercept = 0.0
    count = len(standardized)
    for _ in range(iterations):
        grad_intercept = 0.0
        gradients = [0.0] * len(weights)
        for values, outcome in standardized:
            linear = intercept + sum(weight * value for weight, value in zip(weights, values))
            prediction = 1.0 / (1.0 + math.exp(-max(min(linear, 35), -35)))
            error = prediction - outcome
            grad_intercept += error
            for index, value in enumerate(values):
                gradients[index] += error * value
        intercept -= learning_rate * grad_intercept / count
        for index in range(len(weights)):
            gradient = gradients[index] / count + l2 * weights[index] / count
            weights[index] -= learning_rate * gradient
    return {
        "featureNames": list(feature_names),
        "means": means,
        "scales": scales,
        "weights": weights,
        "intercept": intercept,
        "l2": l2,
        "developmentExamples": count,
    }


def logistic_probability(model: dict[str, Any], example: dict[str, Any]) -> float | None:
    feature_names = tuple(model["featureNames"])
    values = _vector(example, feature_names)
    if values is None:
        return None
    standardized = [
        (value - center) / scale
        for value, center, scale in zip(values, model["means"], model["scales"])
    ]
    linear = float(model["intercept"]) + sum(
        weight * value for weight, value in zip(model["weights"], standardized)
    )
    if linear >= 0:
        z = math.exp(-linear)
        return 1.0 / (1.0 + z)
    z = math.exp(linear)
    return z / (1.0 + z)


def _prediction_rows(
    examples: list[dict[str, Any]],
    probability: Callable[[dict[str, Any]], float | None],
) -> list[dict[str, Any]]:
    rows = []
    for example in examples:
        predicted = probability(example)
        if predicted is None:
            continue
        rows.append({
            "probability": round(float(predicted), 6),
            "outcome": int(example["sideAWon"]),
            "evidenceTier": example["evidenceTier"],
            "format": example["format"],
            "eventId": example.get("eventId"),
        })
    return rows


def _elo_probability(rating_a: float, rating_b: float, scale: float = 400.0) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / scale))


def run_elo(
    development: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
    *,
    k_factor: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ratings: defaultdict[int, float] = defaultdict(lambda: 1500.0)

    def process(
        examples: list[dict[str, Any]],
        collect: bool,
    ) -> list[dict[str, Any]]:
        predictions: list[dict[str, Any]] = []
        for example in examples:
            side_a = example["sideAPlayerIds"]
            side_b = example["sideBPlayerIds"]
            rating_a = mean(ratings[int(player_id)] for player_id in side_a)
            rating_b = mean(ratings[int(player_id)] for player_id in side_b)
            probability = _elo_probability(rating_a, rating_b)
            outcome = int(example["sideAWon"])
            if collect:
                predictions.append({
                    "probability": round(probability, 6),
                    "outcome": outcome,
                    "evidenceTier": example["evidenceTier"],
                    "format": example["format"],
                    "eventId": example.get("eventId"),
                })
            change = k_factor * (outcome - probability)
            for player_id in side_a:
                ratings[int(player_id)] += change
            for player_id in side_b:
                ratings[int(player_id)] -= change
        return predictions

    development_predictions = process(development, True)
    holdout_predictions = process(holdout, True)
    return development_predictions, holdout_predictions


def tune_elo_k(
    development: list[dict[str, Any]],
    candidates: tuple[float, ...] = (10.0, 20.0, 40.0),
) -> tuple[float, dict[str, Any]]:
    results: dict[str, Any] = {}
    best_k = candidates[0]
    best_loss = float("inf")
    for candidate in candidates:
        predictions, _ = run_elo(development, [], k_factor=candidate)
        metrics = _metric_summary(predictions)
        results[str(int(candidate))] = metrics
        if metrics["logLoss"] is not None and metrics["logLoss"] < best_loss:
            best_loss = metrics["logLoss"]
            best_k = candidate
    return best_k, results


def _loss(probability: float, outcome: int, metric: str) -> float:
    if metric == "brier":
        return (probability - outcome) ** 2
    clipped = min(max(probability, 1e-15), 1 - 1e-15)
    return -(outcome * math.log(clipped) + (1 - outcome) * math.log(1 - clipped))


def bootstrap_improvement_interval(
    predictions: list[dict[str, Any]],
    *,
    metric: str,
    samples: int = 1000,
    seed: int = 1729,
) -> dict[str, float | int | None]:
    if not predictions:
        return {"samples": 0, "lower95": None, "mean": None, "upper95": None}
    randomizer = random.Random(seed)
    improvements = []
    equal_loss = _loss(0.5, 0, metric)
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, prediction in enumerate(predictions):
        event_id = prediction.get("eventId")
        key = f"event:{event_id}" if event_id is not None else f"row:{index}"
        clusters[key].append(prediction)
    cluster_values = list(clusters.values())
    cluster_count = len(cluster_values)
    for _ in range(samples):
        selected = [
            item
            for _ in range(cluster_count)
            for item in cluster_values[randomizer.randrange(cluster_count)]
        ]
        improvements.append(mean(
            equal_loss - _loss(float(item["probability"]), int(item["outcome"]), metric)
            for item in selected
        ))
    improvements.sort()
    return {
        "samples": samples,
        "clusters": cluster_count,
        "lower95": round(improvements[int(samples * 0.025)], 6),
        "mean": round(mean(improvements), 6),
        "upper95": round(improvements[min(int(samples * 0.975), samples - 1)], 6),
    }


def evaluate_holdout(
    conn: sqlite3.Connection,
    *,
    development_fraction: float = 0.7,
    window_days: int | None = 365,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    examples = build_evaluation_dataset(
        conn,
        window_days=window_days,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    development, holdout, holdout_start = chronological_split(
        examples,
        development_fraction=development_fraction,
    )
    eligible_development = [
        example for example in development if _vector(example) is not None
    ]
    eligible_holdout = [
        example for example in holdout if _vector(example) is not None
    ]

    ppr_only_model = fit_logistic(
        eligible_development,
        feature_names=("pprDelta",),
        l2=0.1,
    )
    fitted_ppr = _prediction_rows(
        eligible_holdout,
        lambda example: logistic_probability(ppr_only_model, example),
    )
    stage_a_model = fit_logistic(
        eligible_development,
        feature_names=LOGISTIC_FEATURES,
        l2=0.1,
    )
    stage_a_logistic = _prediction_rows(
        eligible_holdout,
        lambda example: logistic_probability(stage_a_model, example),
    )
    fixed_ppr = _prediction_rows(
        eligible_holdout,
        lambda example: example.get("fixedPprProbability"),
    )
    equal = _prediction_rows(holdout, lambda _: 0.5)

    best_k, elo_development = tune_elo_k(development)
    _, elo_holdout = run_elo(development, holdout, k_factor=best_k)

    def summarize(predictions: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            **_metric_summary(predictions),
            "coverageRate": round(len(predictions) / len(holdout), 6) if holdout else 0,
            "logLossImprovementVsEqual": (
                round(0.6931471805599453 - _metric_summary(predictions)["logLoss"], 6)
                if predictions
                else None
            ),
            "brierImprovementVsEqual": (
                round(0.25 - _metric_summary(predictions)["brierScore"], 6)
                if predictions
                else None
            ),
            "logLossImprovement95": bootstrap_improvement_interval(
                predictions,
                metric="log_loss",
            ),
            "brierImprovement95": bootstrap_improvement_interval(
                predictions,
                metric="brier",
            ),
        }

    return {
        "evaluationVersion": HOLDOUT_VERSION,
        "featureVersion": "stage-a-v1",
        "developmentFractionByEventDate": development_fraction,
        "holdoutStartDate": holdout_start,
        "developmentMatchups": len(development),
        "holdoutMatchups": len(holdout),
        "eligibleDevelopmentMatchups": len(eligible_development),
        "eligibleHoldoutMatchups": len(eligible_holdout),
        "models": {
            "equal-v1": summarize(equal),
            "fixed-ppr-difference-v1": summarize(fixed_ppr),
            "fitted-ppr-logistic-v1": {
                **summarize(fitted_ppr),
                "parameters": ppr_only_model,
            },
            "regularized-stage-a-logistic-v1": {
                **summarize(stage_a_logistic),
                "parameters": stage_a_model,
            },
            "elo-v1": {
                **summarize(elo_holdout),
                "selectedK": best_k,
                "developmentTuning": elo_development,
            },
        },
        "notes": [
            "All fitted parameters use development events before the holdout start date.",
            "Elo ratings update chronologically after each observed game.",
            "Bootstrap intervals are paired improvements against a 50/50 forecast.",
            "The logistic model uses a small frozen Stage A feature vector with L2 regularization.",
        ],
    }
