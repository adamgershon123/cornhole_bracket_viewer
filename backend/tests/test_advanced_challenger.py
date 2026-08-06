import unittest

from advanced_challenger import score_advanced_challenger


class AdvancedChallengerTests(unittest.TestCase):
    def test_scores_when_all_validated_features_are_present(self):
        result = score_advanced_challenger({
            "deltasAminusB": {
                "predictivePpr": 0.5,
                "fourBaggerRate": 0.02,
                "bagsInRate": 0.04,
            },
        })
        self.assertEqual(result["status"], "PREDICTED")
        self.assertGreater(result["sideAProbability"], 0.5)
        self.assertAlmostEqual(
            result["sideAProbability"] + result["sideBProbability"],
            1.0,
        )
        self.assertEqual(
            [item["factor"] for item in result["factorPolicy"]["weighted"]],
            ["Expected performance", "Four-bagger rate", "Bags-in rate"],
        )

    def test_abstains_when_bag_evidence_is_missing(self):
        result = score_advanced_challenger({
            "deltasAminusB": {
                "predictivePpr": 0.5,
                "fourBaggerRate": None,
                "bagsInRate": 0.04,
            },
        })
        self.assertEqual(result["status"], "ABSTAINED")


if __name__ == "__main__":
    unittest.main()
