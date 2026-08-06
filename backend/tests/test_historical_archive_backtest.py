from __future__ import annotations

import unittest

from historical_archive_backtest import (
    _metrics,
    _paired_comparison,
    _signature_counts,
    _shrunk_effect,
    _shrunk_rate_effect,
)


class HistoricalArchiveBacktestTests(unittest.TestCase):
    def test_ledger_signature_counts_support_refresh_deltas(self) -> None:
        self.assertEqual(
            _signature_counts("games:26351:rounds:685756"),
            {"games": 26351, "rounds": 685756},
        )
        self.assertEqual(
            _signature_counts("invalid"),
            {"games": 0, "rounds": 0},
        )

    def test_context_effect_is_shrunk_toward_player_baseline(self) -> None:
        self.assertEqual(_shrunk_effect(0, 0, 7.0), 0.0)
        raw_effect = (80 / 10) - 7.0
        self.assertAlmostEqual(_shrunk_effect(80, 10, 7.0), raw_effect * 0.25)
        self.assertAlmostEqual(_shrunk_rate_effect(5, 10, 0.4), 0.025)

    def test_metrics_score_probabilities_and_winners(self) -> None:
        result = _metrics([
            {"probability": 0.8, "outcome": 1},
            {"probability": 0.4, "outcome": 0},
        ], 4)
        self.assertEqual(result["evaluatedMatchups"], 2)
        self.assertEqual(result["coverageRate"], 0.5)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertLess(result["brierScore"], 0.25)

    def test_paired_comparison_counts_only_changed_calls(self) -> None:
        baseline = [
            {"probability": 0.6, "outcome": 1},
            {"probability": 0.6, "outcome": 0},
        ]
        challenger = [
            {"probability": 0.4, "outcome": 1},
            {"probability": 0.4, "outcome": 0},
        ]
        result = _paired_comparison(baseline, challenger)
        self.assertEqual(result["challengerOnlyCorrect"], 1)
        self.assertEqual(result["pprOnlyCorrect"], 1)
        self.assertEqual(result["netAdditionalCorrect"], 0)


if __name__ == "__main__":
    unittest.main()
