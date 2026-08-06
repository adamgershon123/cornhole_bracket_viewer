import unittest

from live_probability_evaluation import _calibration, _metrics


class LiveProbabilityEvaluationTests(unittest.TestCase):
    def test_metrics_reward_correct_confident_probabilities(self):
        good = _metrics([(0.9, 1), (0.1, 0)])
        weak = _metrics([(0.5, 1), (0.5, 0)])
        self.assertLess(good["brierScore"], weak["brierScore"])
        self.assertLess(good["logLoss"], weak["logLoss"])

    def test_calibration_reports_bucket_outcome_rate(self):
        rows = _calibration({60: [1, 0, 1, 1]})
        self.assertEqual(rows[0]["bucket"], "60-70%")
        self.assertEqual(rows[0]["averageOutcome"], 0.75)


if __name__ == "__main__":
    unittest.main()
