from __future__ import annotations

import unittest

from rolling_origin_evaluation import (
    evaluate_rolling_origin_examples,
    rolling_origin_folds,
)


def example(date: str, delta: float, outcome: int) -> dict:
    return {
        "eventDate": date,
        "sideAWon": outcome,
        "sideAPlayerIds": [1],
        "sideBPlayerIds": [2],
        "evidenceTier": "B",
        "format": "S:D",
        "modelReady": True,
        "features": {"pprDelta": delta},
    }


class RollingOriginEvaluationTests(unittest.TestCase):
    def test_folds_are_strictly_chronological_and_keep_dates_whole(self) -> None:
        rows = [
            example(f"2026-01-{day:02d}", 1, 1)
            for day in range(1, 9)
            for _ in range(2)
        ]
        folds = rolling_origin_folds(
            rows,
            minimum_development_dates=4,
            test_dates_per_fold=2,
        )
        self.assertEqual(len(folds), 2)
        for development, test, _ in folds:
            development_dates = {row["eventDate"] for row in development}
            test_dates = {row["eventDate"] for row in test}
            self.assertTrue(development_dates.isdisjoint(test_dates))
            self.assertLess(max(development_dates), min(test_dates))

    def test_evaluation_refits_and_combines_out_of_sample_predictions(self) -> None:
        rows = []
        for day in range(1, 13):
            rows.append(example(f"2026-01-{day:02d}", 2, 1))
            rows.append(example(f"2026-01-{day:02d}", -2, 0))
        result = evaluate_rolling_origin_examples(
            rows,
            minimum_development_dates=4,
            test_dates_per_fold=2,
        )
        self.assertEqual(result["evaluatedFoldCount"], 4)
        self.assertEqual(result["aggregate"]["predictions"], 16)
        self.assertEqual(result["aggregate"]["coverageRate"], 1.0)
        self.assertGreater(result["aggregate"]["accuracy"], 0.9)
        self.assertEqual(result["stability"]["foldsBeatingEqualLogLoss"], 4)
        self.assertGreater(
            result["aggregate"]["logLossImprovement95"]["lower95"],
            0,
        )

    def test_non_model_ready_rows_are_abstentions(self) -> None:
        rows = []
        for day in range(1, 7):
            rows.extend([
                example(f"2026-01-{day:02d}", 2, 1),
                example(f"2026-01-{day:02d}", -2, 0),
            ])
        rows[-1]["modelReady"] = False
        result = evaluate_rolling_origin_examples(
            rows,
            minimum_development_dates=4,
            test_dates_per_fold=2,
        )
        self.assertEqual(result["aggregate"]["predictions"], 3)
        self.assertEqual(result["aggregate"]["coverageRate"], 0.75)


if __name__ == "__main__":
    unittest.main()
