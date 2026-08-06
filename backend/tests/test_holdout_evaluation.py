from __future__ import annotations

import unittest

from holdout_evaluation import (
    LOGISTIC_FEATURES,
    bootstrap_improvement_interval,
    chronological_split,
    fit_logistic,
    logistic_probability,
    run_elo,
    tune_elo_k,
)


def example(
    date: str,
    ppr_delta: float,
    outcome: int,
    player_a: int = 1,
    player_b: int = 2,
) -> dict:
    return {
        "eventDate": date,
        "sideAWon": outcome,
        "sideAPlayerIds": [player_a],
        "sideBPlayerIds": [player_b],
        "evidenceTier": "B",
        "format": "S:D",
        "modelReady": True,
        "features": {
            "pprDelta": ppr_delta,
            "dprDelta": ppr_delta,
            "bagsInDelta": ppr_delta / 10,
            "fourBaggerDelta": 0,
            "roundWinDelta": ppr_delta / 10,
            "logRoundRatio": 0,
            "partnershipDifference": 0,
        },
    }


class HoldoutEvaluationTests(unittest.TestCase):
    def test_split_keeps_event_dates_wholly_on_one_side(self) -> None:
        rows = [
            example("2026-01-01", 1, 1),
            example("2026-01-01", -1, 0),
            example("2026-02-01", 1, 1),
            example("2026-03-01", -1, 0),
        ]
        development, holdout, start = chronological_split(
            rows,
            development_fraction=2 / 3,
        )
        self.assertEqual(start, "2026-03-01")
        self.assertEqual({row["eventDate"] for row in development}, {"2026-01-01", "2026-02-01"})
        self.assertEqual({row["eventDate"] for row in holdout}, {"2026-03-01"})

    def test_logistic_fit_learns_positive_ppr_direction(self) -> None:
        rows = []
        for index in range(40):
            delta = 2.0 if index % 2 == 0 else -2.0
            rows.append(example(f"2026-01-{index % 28 + 1:02d}", delta, 1 if delta > 0 else 0))
        model = fit_logistic(
            rows,
            feature_names=LOGISTIC_FEATURES,
            iterations=1500,
        )
        positive = logistic_probability(model, example("2026-02-01", 2, 1))
        negative = logistic_probability(model, example("2026-02-01", -2, 0))
        self.assertIsNotNone(positive)
        self.assertIsNotNone(negative)
        self.assertGreater(positive, 0.5)
        self.assertLess(negative, 0.5)

    def test_one_parameter_ppr_model_uses_only_ppr_delta(self) -> None:
        rows = [
            example("2026-01-01", 2, 1),
            example("2026-01-02", -2, 0),
            example("2026-01-03", 1, 1),
            example("2026-01-04", -1, 0),
        ]
        model = fit_logistic(
            rows,
            feature_names=("pprDelta",),
            iterations=500,
        )
        self.assertEqual(model["featureNames"], ["pprDelta"])
        self.assertEqual(len(model["weights"]), 1)
        self.assertEqual(len(model["means"]), 1)

    def test_logistic_vector_rejects_non_model_ready_matchup(self) -> None:
        ready = example("2026-01-01", 2, 1)
        blocked = {**ready, "modelReady": False}
        model = fit_logistic(
            [ready, example("2026-01-02", -2, 0)],
            feature_names=LOGISTIC_FEATURES,
            iterations=200,
        )
        self.assertIsNone(logistic_probability(model, blocked))

    def test_elo_updates_chronologically(self) -> None:
        development = [
            example("2026-01-01", 0, 1),
            example("2026-01-02", 0, 1),
        ]
        holdout = [example("2026-02-01", 0, 1)]
        _, predictions = run_elo(development, holdout, k_factor=20)
        self.assertEqual(len(predictions), 1)
        self.assertGreater(predictions[0]["probability"], 0.5)

    def test_elo_tuning_selects_a_candidate(self) -> None:
        development = [
            example(f"2026-01-{index + 1:02d}", 0, 1)
            for index in range(10)
        ]
        selected, results = tune_elo_k(development, candidates=(10.0, 20.0))
        self.assertIn(selected, (10.0, 20.0))
        self.assertEqual(set(results), {"10", "20"})

    def test_bootstrap_reports_positive_improvement_for_correct_predictions(self) -> None:
        predictions = [
            {"probability": 0.8, "outcome": 1},
            {"probability": 0.2, "outcome": 0},
        ] * 10
        interval = bootstrap_improvement_interval(
            predictions,
            metric="brier",
            samples=200,
        )
        self.assertGreater(interval["lower95"], 0)
        self.assertGreater(interval["mean"], 0)
        self.assertEqual(interval["clusters"], 20)


if __name__ == "__main__":
    unittest.main()
