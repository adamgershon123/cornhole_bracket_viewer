import unittest

from profile_rating_validation import _correlation


class ProfileRatingValidationTests(unittest.TestCase):
    def test_correlation_detects_stable_ordering(self):
        self.assertAlmostEqual(_correlation([(1, 2), (2, 4), (3, 6)]), 1.0)


if __name__ == "__main__":
    unittest.main()
