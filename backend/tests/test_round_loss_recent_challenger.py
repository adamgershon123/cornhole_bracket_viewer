from __future__ import annotations

import unittest

from round_loss_recent_challenger import (
    MODEL_VERSION,
    score_round_loss_recent_challenger,
)


class RoundLossRecentChallengerTests(unittest.TestCase):
    def test_scores_complete_matchup(self) -> None:
        result = score_round_loss_recent_challenger({
            "deltasAminusB": {
                "predictivePpr": 0.5,
                "roundLossRate": -0.05,
                "recent90PprEffect": 0.1,
            }
        })
        self.assertEqual(result["modelVersion"], MODEL_VERSION)
        self.assertEqual(result["status"], "PREDICTED")
        self.assertGreater(result["sideAProbability"], 0.5)
        self.assertAlmostEqual(
            result["sideAProbability"] + result["sideBProbability"], 1.0
        )

    def test_abstains_when_round_loss_is_missing(self) -> None:
        result = score_round_loss_recent_challenger({
            "deltasAminusB": {
                "predictivePpr": 0.5,
                "roundLossRate": None,
                "recent90PprEffect": 0.1,
            }
        })
        self.assertEqual(result["status"], "ABSTAINED")


if __name__ == "__main__":
    unittest.main()
