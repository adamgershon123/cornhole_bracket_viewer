import unittest

from prediction_weighting import prediction_weighting_policy


class PredictionWeightingTests(unittest.TestCase):
    def test_only_validated_ppr_feature_is_active_for_games(self):
        policy = prediction_weighting_policy()
        self.assertEqual(
            policy["gamePrediction"]["activeFeature"],
            "calculatedPprDelta",
        )
        self.assertTrue(all(
            weight == 0
            for weight in policy["gamePrediction"]["ratingWeights"].values()
        ))

    def test_bracket_uses_ppr_but_descriptive_rating_weights_remain_zero(self):
        policy = prediction_weighting_policy()
        self.assertEqual(
            policy["bracketPrediction"]["status"],
            "EXPERIMENTAL_ACTIVE_ABSTRACTION",
        )
        self.assertEqual(
            policy["bracketPrediction"]["activeFeature"],
            "calculatedPprDelta",
        )
        self.assertTrue(all(
            weight == 0
            for weight in policy["bracketPrediction"]["ratingWeights"].values()
        ))


if __name__ == "__main__":
    unittest.main()
