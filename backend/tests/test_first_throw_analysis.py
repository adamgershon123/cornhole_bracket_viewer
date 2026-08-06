import unittest

from first_throw_analysis import _empty, _add, _summarize, _certainty_summary, _chronological_validation


class FirstThrowAnalysisTests(unittest.TestCase):
    def test_scoring_conceding_and_washes_are_separate(self):
        row = _empty()
        _add(row, "A", "A", 3, "A")
        _add(row, "A", None, 0, "A")
        _add(row, "A", "B", 2, "B")
        summary = _summarize(row)
        self.assertEqual(summary["knownRounds"], 3)
        self.assertEqual(summary["scoredRounds"], 1)
        self.assertEqual(summary["washRounds"], 1)
        self.assertEqual(summary["concededRounds"], 1)
        self.assertAlmostEqual(summary["averageSignedNetPoints"], 1 / 3)

    def test_certainty_summary_tracks_rounds_until_first_score(self):
        summary = _certainty_summary([1, 1, 2, 4], 5)
        self.assertEqual(summary["averageRoundsUntilKnown"], 2.0)
        self.assertEqual(summary["medianRoundsUntilKnown"], 1.5)
        self.assertEqual(summary["gamesUnresolved"], 1)
        self.assertEqual(summary["cumulativeByRound"][0]["knownRate"], 0.4)

    def test_chronological_validation_requires_holdout_replication(self):
        games = []
        for index in range(10):
            row = _empty()
            for _ in range(20):
                _add(row, "A", "A", 1, "A")
            for _ in range(5):
                _add(row, "A", "B", 1, "A")
            games.append((f"2026-01-{index + 1:02d}", row))
        report = _chronological_validation(games)
        self.assertTrue(report["effectReplicated"])
        self.assertEqual(report["activationStatus"], "READY_FOR_SIMULATION_WEIGHT")


if __name__ == "__main__":
    unittest.main()
