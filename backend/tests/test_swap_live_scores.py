import unittest

from app import safe_swap_match, safe_swap_match_stats, should_apply_match_stats_score


class SwapLiveScoreTests(unittest.TestCase):
    def test_assigned_match_without_start_or_score_is_next(self):
        match = safe_swap_match({
            "matchID": 23,
            "matchStatus": "In-Progress",
            "matchStatusID": 1,
            "matchStartTime": None,
            "homeScore": 0,
            "awayScore": 0,
            "homeTeam": [],
            "awayTeam": [],
        })
        self.assertEqual(match["status"], "next")

    def test_started_match_is_live(self):
        match = safe_swap_match({
            "matchID": 20,
            "matchStatus": "In-Progress",
            "matchStatusID": 1,
            "resultGameStatus": 5,
            "matchStartTime": "2026-08-14 18:42:08",
            "matchEndTime": "2026-08-14 18:42:08",
            "homeScore": 15,
            "awayScore": 9,
            "homeTeam": [],
            "awayTeam": [],
        })
        self.assertEqual(match["status"], "live")
        self.assertEqual(match["homeScore"], 15)
        self.assertEqual(match["awayScore"], 9)

    def test_empty_match_stats_are_not_published_rounds(self):
        stats = safe_swap_match_stats({
            "scoresheet": False,
            "currentRound": 0,
            "homeScore": 0,
            "awayScore": 0,
            "event_match_details": [],
            "event_match_inning_history": [],
            "event_match_inning_summary": [],
        })
        self.assertFalse(stats["scoresheet"])
        self.assertFalse(stats["hasPublishedRounds"])

    def test_round_feed_cannot_replace_published_schedule_score(self):
        match = {"homeScore": 21, "awayScore": 2}
        stats = {
            "scoresheet": True,
            "hasPublishedRounds": True,
            "homeScore": 0,
            "awayScore": 2,
        }
        self.assertFalse(should_apply_match_stats_score(match, stats))

    def test_round_feed_can_fill_schedule_while_it_is_still_zero(self):
        match = {"homeScore": 0, "awayScore": 0}
        stats = {
            "scoresheet": True,
            "hasPublishedRounds": True,
            "homeScore": 15,
            "awayScore": 9,
        }
        self.assertTrue(should_apply_match_stats_score(match, stats))


if __name__ == "__main__":
    unittest.main()
