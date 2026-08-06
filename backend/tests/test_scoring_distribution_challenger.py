import unittest

from scoring_distribution_challenger import (
    score_scoring_distribution_challenger,
)


class ScoringDistributionChallengerTests(unittest.TestCase):
    def test_scores_complete_distribution_features(self):
        result = score_scoring_distribution_challenger({
            "deltasAminusB": {
                "calculatedPpr": 0.5,
                "ceilingRate": 0.05,
                "floorAvoidance": 0.04,
                "calculatedDpr": 0.3,
            },
        })

        self.assertEqual(result["status"], "PREDICTED")
        self.assertGreater(result["sideAProbability"], 0.5)
        self.assertAlmostEqual(
            result["sideAProbability"] + result["sideBProbability"],
            1.0,
        )

    def test_abstains_without_distribution_history(self):
        result = score_scoring_distribution_challenger({
            "deltasAminusB": {
                "calculatedPpr": 0.5,
                "ceilingRate": None,
                "floorAvoidance": 0.04,
                "calculatedDpr": 0.3,
            },
        })

        self.assertEqual(result["status"], "ABSTAINED")


if __name__ == "__main__":
    unittest.main()
