import unittest

from profile_feature_model_validation import (
    _add_nonlinear_and_format_features,
    _blend_predictions,
)


class ProfileFeatureCandidateEngineeringTests(unittest.TestCase):
    def test_signed_square_reverses_with_matchup_direction(self):
        examples = [
            {
                "format": "D:P",
                "features": {
                    "pprDelta": 0.5,
                    "ceilingRateDelta": -0.2,
                    "floorAvoidanceDelta": 0.1,
                    "dprDelta": -0.4,
                },
            },
            {
                "format": "D:P",
                "features": {
                    "pprDelta": -0.5,
                    "ceilingRateDelta": 0.2,
                    "floorAvoidanceDelta": -0.1,
                    "dprDelta": 0.4,
                },
            },
        ]

        _add_nonlinear_and_format_features(examples)

        for name in (
            "pprDeltaSignedSquare",
            "ceilingRateDeltaSignedSquare",
            "floorAvoidanceDeltaSignedSquare",
            "dprDeltaSignedSquare",
        ):
            self.assertAlmostEqual(
                examples[0]["features"][name],
                -examples[1]["features"][name],
            )

    def test_format_interactions_only_activate_for_matching_format(self):
        examples = [
            {
                "format": "S:W",
                "features": {
                    "pprDelta": 0.6,
                    "ceilingRateDelta": 0.2,
                    "floorAvoidanceDelta": 0.1,
                    "dprDelta": 0.3,
                },
            }
        ]

        _add_nonlinear_and_format_features(examples)
        features = examples[0]["features"]

        self.assertEqual(features["pprDeltaSingles"], 0.6)
        self.assertEqual(features["pprDeltaDoubles"], 0.0)
        self.assertEqual(features["pprDeltaBracketP"], 0.0)
        self.assertEqual(features["pprDeltaBracketW"], 0.6)
        self.assertEqual(features["ceilingRateDeltaSingles"], 0.2)

    def test_blend_preserves_sample_and_weights_probabilities(self):
        common = {"eventId": 1, "outcome": 1, "format": "D:P"}
        blended = _blend_predictions(
            [{**common, "probability": 0.6}],
            [{**common, "probability": 0.8}],
            scoring_weight=0.75,
        )

        self.assertEqual(len(blended), 1)
        self.assertAlmostEqual(blended[0]["probability"], 0.75)


if __name__ == "__main__":
    unittest.main()
