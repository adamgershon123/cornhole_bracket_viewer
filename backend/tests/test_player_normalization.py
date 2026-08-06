import unittest

from app import safe_player, safe_swap_player


class PlayerNormalizationTests(unittest.TestCase):
    def test_safe_player_returns_normalized_record(self):
        player = safe_player({
            "playerID": 142125,
            "playerFirstName": "Adam",
            "playerLastName": "Gershon",
            "playerCPI": 7.4,
        })
        self.assertEqual(player["playerId"], 142125)
        self.assertEqual(player["name"], "Adam Gershon")
        self.assertEqual(player["cpi"], 7.4)

    def test_swap_player_can_extend_normalized_record(self):
        player = safe_swap_player({
            "playerID": 142125,
            "playerFirstName": "Adam",
            "playerLastName": "Gershon",
            "wins": 3,
            "losses": 1,
        })
        self.assertEqual(player["wins"], 3)
        self.assertEqual(player["losses"], 1)


if __name__ == "__main__":
    unittest.main()
