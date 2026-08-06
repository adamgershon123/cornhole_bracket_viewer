import unittest

from opponent_adjusted_performance import _mean_residual, _metrics


class OpponentAdjustedPerformanceTests(unittest.TestCase):
    def test_residual_is_actual_minus_pregame_expectation(self):
        rows = [
            {"performanceVsExpected": 0.5},
            {"performanceVsExpected": -0.1},
        ]
        self.assertAlmostEqual(_mean_residual(rows), 0.2)

    def test_error_metrics_reward_closer_expected_ppr(self):
        closer = _metrics([(8.0, 8.1), (7.0, 6.9)])
        farther = _metrics([(9.0, 8.1), (6.0, 6.9)])
        self.assertLess(closer["mae"], farther["mae"])
        self.assertLess(closer["rmse"], farther["rmse"])


if __name__ == "__main__":
    unittest.main()
