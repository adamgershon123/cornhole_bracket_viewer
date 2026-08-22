import sqlite3
import unittest

from shared_viewer_profile import (
    enroll_default_player_brackets_from_collected_rosters,
    get_shared_viewer_profile,
    update_shared_viewer_profile,
)
from lifecycle_runner import monitor_event


class SharedViewerProfileTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE events(event_id INTEGER PRIMARY KEY, status TEXT, bracket_completed INTEGER DEFAULT 0)"
        )
        self.conn.execute("CREATE TABLE team_members(team_id TEXT, player_id INTEGER, event_id INTEGER)")
        self.conn.execute("CREATE TABLE player_rounds(event_id INTEGER, player_id INTEGER)")
        self.conn.execute("CREATE TABLE swap_standings(event_id INTEGER, player_id INTEGER)")

    def tearDown(self):
        self.conn.close()

    def test_profile_is_shared_and_deduplicates_favorites(self):
        initial = get_shared_viewer_profile(self.conn)
        self.assertEqual(initial["defaultPlayerId"], 142125)
        updated = update_shared_viewer_profile(
            self.conn,
            default_player_id=99,
            favorite_players=[
                {"playerId": 99, "name": "Default"},
                {"playerId": "100", "name": "Favorite"},
                {"playerId": 100, "name": "Duplicate"},
            ],
        )
        self.assertEqual(updated["defaultPlayerId"], 99)
        self.assertEqual([p["playerId"] for p in updated["favoritePlayers"]], [99, 100])

    def test_collected_roster_enrolls_bracket_but_not_parent_swap(self):
        monitor_event(self.conn, event_id=10, schedule_format="SWAP", source_timezone=None)
        monitor_event(self.conn, event_id=11, schedule_format="BRACKET", source_timezone=None)
        self.conn.executemany(
            "INSERT INTO team_members(team_id,player_id,event_id) VALUES (?,?,?)",
            [("10:1", 142125, 10), ("11:1", 142125, 11)],
        )
        self.conn.commit()

        result = enroll_default_player_brackets_from_collected_rosters(self.conn)
        self.assertEqual(result["newlyEnabled"], [11])
        row = self.conn.execute(
            "SELECT * FROM monitored_events WHERE event_id='11'"
        ).fetchone()
        self.assertEqual(row["auto_freeze_prediction"], 1)
        parent = self.conn.execute(
            "SELECT * FROM monitored_events WHERE event_id='10'"
        ).fetchone()
        self.assertEqual(parent["auto_freeze_prediction"], 0)

        repeated = enroll_default_player_brackets_from_collected_rosters(self.conn)
        self.assertEqual(repeated["newlyEnabled"], [])


if __name__ == "__main__":
    unittest.main()
