import unittest

from strength_of_competition import _median, _tier


class StrengthOfCompetitionTests(unittest.TestCase):
    def test_opponent_tiers_are_relative_to_contemporary_population(self):
        self.assertEqual(_tier(8.1, 7.0), "ELITE")
        self.assertEqual(_tier(7.6, 7.0), "STRONG")
        self.assertEqual(_tier(7.2, 7.0), "ABOVE_AVERAGE")
        self.assertEqual(_tier(7.0, 7.0), "AVERAGE")
        self.assertEqual(_tier(6.4, 7.0), "DEVELOPING")

    def test_median_handles_even_and_odd_samples(self):
        self.assertEqual(_median([3, 1, 2]), 2)
        self.assertEqual(_median([4, 1, 3, 2]), 2.5)


if __name__ == "__main__":
    unittest.main()
