import unittest

from live_win_probability import calculate_probability_series


class LiveWinProbabilityTests(unittest.TestCase):
    def test_series_starts_at_locked_pregame_probability(self):
        result = calculate_probability_series(
            [], top_team_id="A", bottom_team_id="B",
            pregame_top_probability=0.64, simulations=100,
        )
        self.assertEqual(result["points"][0]["topWinProbability"], 0.64)

    def test_completed_state_resolves_to_one(self):
        result = calculate_probability_series(
            [{"round": 1, "gameState": {"scoreAfter": {"A": 21, "B": 12}}}],
            top_team_id="A", bottom_team_id="B", simulations=100,
        )
        self.assertEqual(result["points"][-1]["topWinProbability"], 1.0)
        self.assertEqual(result["points"][-1]["status"], "FINAL")

    def test_same_inputs_are_deterministic(self):
        args = dict(
            rounds=[{"round": 1, "gameState": {"scoreAfter": {"A": 10, "B": 8}}}],
            top_team_id="A", bottom_team_id="B",
            top_gross_samples=[6, 7, 8], bottom_gross_samples=[5, 6, 7],
            simulations=250, seed_key="match",
        )
        self.assertEqual(
            calculate_probability_series(**args)["points"],
            calculate_probability_series(**args)["points"],
        )

    def test_eight_point_lead_improves_trailing_favorites_opponent(self):
        prior = 0.286
        result = calculate_probability_series(
            [{
                "round": 5,
                "gameState": {
                    "scoreAfter": {"A": 8, "B": 0},
                    "nextFirstThrowTeamId": "A",
                },
            }],
            top_team_id="A",
            bottom_team_id="B",
            pregame_top_probability=prior,
            top_gross_samples=[6, 7, 8, 9],
            bottom_gross_samples=[7, 8, 9, 10],
            simulations=5000,
            seed_key="eight-point-lead",
        )
        self.assertGreater(
            result["points"][-1]["topWinProbability"],
            prior,
        )


if __name__ == "__main__":
    unittest.main()
