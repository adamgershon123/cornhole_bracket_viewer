from __future__ import annotations

from statistics import mean
from typing import Any

from chronological_evaluation import _metric_summary
from holdout_evaluation import (
    _prediction_rows,
    _vector,
    bootstrap_improvement_interval,
    build_evaluation_dataset,
    fit_logistic,
    logistic_probability,
)


ROLLING_ORIGIN_VERSION = "rolling-origin-v1"


def rolling_origin_folds(
    examples: list[dict[str, Any]],
    *,
    minimum_development_dates: int = 10,
    test_dates_per_fold: int = 5,
) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]]:
    if minimum_development_dates < 1:
        raise ValueError("minimum_development_dates must be positive")
    if test_dates_per_fold < 1:
        raise ValueError("test_dates_per_fold must be positive")
    dates = sorted({str(example["eventDate"]) for example in examples})
    folds = []
    fold_number = 1
    for test_start_index in range(
        minimum_development_dates,
        len(dates),
        test_dates_per_fold,
    ):
        test_dates = dates[
            test_start_index:test_start_index + test_dates_per_fold
        ]
        if not test_dates:
            continue
        development_dates = set(dates[:test_start_index])
        test_date_set = set(test_dates)
        development = [
            example
            for example in examples
            if str(example["eventDate"]) in development_dates
        ]
        test = [
            example
            for example in examples
            if str(example["eventDate"]) in test_date_set
        ]
        folds.append((
            development,
            test,
            {
                "fold": fold_number,
                "developmentStartDate": dates[0],
                "developmentEndDate": dates[test_start_index - 1],
                "testStartDate": test_dates[0],
                "testEndDate": test_dates[-1],
                "developmentDateCount": len(development_dates),
                "testDateCount": len(test_dates),
            },
        ))
        fold_number += 1
    return folds


def _summarize(
    predictions: list[dict[str, Any]],
    total_matchups: int,
) -> dict[str, Any]:
    metrics = _metric_summary(predictions)
    return {
        **metrics,
        "coverageRate": (
            round(len(predictions) / total_matchups, 6)
            if total_matchups
            else 0
        ),
        "logLossImprovementVsEqual": (
            round(0.6931471805599453 - metrics["logLoss"], 6)
            if metrics["logLoss"] is not None
            else None
        ),
        "brierImprovementVsEqual": (
            round(0.25 - metrics["brierScore"], 6)
            if metrics["brierScore"] is not None
            else None
        ),
    }


def evaluate_rolling_origin_examples(
    examples: list[dict[str, Any]],
    *,
    minimum_development_dates: int = 10,
    test_dates_per_fold: int = 5,
) -> dict[str, Any]:
    folds = rolling_origin_folds(
        examples,
        minimum_development_dates=minimum_development_dates,
        test_dates_per_fold=test_dates_per_fold,
    )
    fold_results = []
    combined_predictions: list[dict[str, Any]] = []
    total_test_matchups = 0
    skipped_folds = 0

    for development, test, metadata in folds:
        eligible_development = [
            example for example in development if _vector(example, ("pprDelta",)) is not None
        ]
        eligible_test = [
            example for example in test if _vector(example, ("pprDelta",)) is not None
        ]
        total_test_matchups += len(test)
        if not eligible_development:
            skipped_folds += 1
            fold_results.append({
                **metadata,
                "status": "SKIPPED_NO_ELIGIBLE_DEVELOPMENT",
                "developmentMatchups": len(development),
                "testMatchups": len(test),
                "eligibleDevelopmentMatchups": 0,
                "eligibleTestMatchups": len(eligible_test),
            })
            continue
        model = fit_logistic(
            eligible_development,
            feature_names=("pprDelta",),
            l2=0.1,
        )
        predictions = _prediction_rows(
            eligible_test,
            lambda example: logistic_probability(model, example),
        )
        combined_predictions.extend(predictions)
        fold_results.append({
            **metadata,
            "status": "EVALUATED",
            "developmentMatchups": len(development),
            "testMatchups": len(test),
            "eligibleDevelopmentMatchups": len(eligible_development),
            "eligibleTestMatchups": len(eligible_test),
            "metrics": _summarize(predictions, len(test)),
            "parameters": model,
        })

    evaluated = [
        fold for fold in fold_results if fold["status"] == "EVALUATED"
    ]
    accuracies = [
        fold["metrics"]["accuracy"]
        for fold in evaluated
        if fold["metrics"]["accuracy"] is not None
    ]
    positive_log_loss_folds = sum(
        fold["metrics"]["logLossImprovementVsEqual"] > 0
        for fold in evaluated
        if fold["metrics"]["logLossImprovementVsEqual"] is not None
    )
    aggregate = _summarize(combined_predictions, total_test_matchups)
    aggregate["logLossImprovement95"] = bootstrap_improvement_interval(
        combined_predictions,
        metric="log_loss",
    )
    aggregate["brierImprovement95"] = bootstrap_improvement_interval(
        combined_predictions,
        metric="brier",
    )
    return {
        "evaluationVersion": ROLLING_ORIGIN_VERSION,
        "featureVersion": "stage-a-v1",
        "modelVersion": "fitted-ppr-logistic-v1",
        "minimumDevelopmentDates": minimum_development_dates,
        "testDatesPerFold": test_dates_per_fold,
        "sourceMatchups": len(examples),
        "foldCount": len(fold_results),
        "evaluatedFoldCount": len(evaluated),
        "skippedFoldCount": skipped_folds,
        "aggregate": aggregate,
        "stability": {
            "foldsBeatingEqualLogLoss": positive_log_loss_folds,
            "evaluatedFolds": len(evaluated),
            "minimumFoldAccuracy": round(min(accuracies), 6) if accuracies else None,
            "meanFoldAccuracy": round(mean(accuracies), 6) if accuracies else None,
            "maximumFoldAccuracy": round(max(accuracies), 6) if accuracies else None,
        },
        "folds": fold_results,
        "notes": [
            "Each fold trains only on event dates strictly before its test window.",
            "All games from an event date remain wholly within one fold partition.",
            "The fitted PPR parameters are re-estimated independently for every fold.",
            "Coverage includes abstentions caused by unavailable or unsafe features.",
        ],
    }


def evaluate_rolling_origin(
    conn,
    *,
    minimum_development_dates: int = 10,
    test_dates_per_fold: int = 5,
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
    return evaluate_rolling_origin_examples(
        examples,
        minimum_development_dates=minimum_development_dates,
        test_dates_per_fold=test_dates_per_fold,
    )
