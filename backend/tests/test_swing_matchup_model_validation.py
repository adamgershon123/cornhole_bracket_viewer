import unittest

from swing_matchup_model_validation import _improves


class SwingMatchupModelValidationTests(unittest.TestCase):
    def test_requires_both_probability_metrics_to_improve(self):
        baseline = {"brierScore": 0.21, "logLoss": 0.61}
        self.assertTrue(_improves(
            {"brierScore": 0.20, "logLoss": 0.60},
            baseline,
        ))
        self.assertFalse(_improves(
            {"brierScore": 0.20, "logLoss": 0.62},
            baseline,
        ))


if __name__ == "__main__":
    unittest.main()
