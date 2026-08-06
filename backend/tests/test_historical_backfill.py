import sqlite3
import unittest
from unittest.mock import patch

from historical_backfill import (
    initialize_schema,
    run_one,
    seed_known_players,
    set_lane_paused,
    set_paused,
    status_snapshot,
    venue_export_rows,
)
from season_platform import init_db


class HistoricalBackfillTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        initialize_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_pause_state_is_persistent_database_state(self):
        paused = set_paused(self.conn, True)
        self.assertTrue(paused["paused"])
        self.assertEqual(run_one(self.conn)["status"], "PAUSED")

        resumed = set_paused(self.conn, False)
        self.assertFalse(resumed["paused"])

    @patch("historical_backfill._process_item")
    def test_collection_lanes_pause_and_flow_independently(self, process_item):
        process_item.return_value = {
            "eventsDiscovered": 0,
            "playersDiscovered": 0,
            "gamesDownloaded": 0,
            "roundsAdded": 0,
            "authBlocked": 0,
            "networkRequests": 0,
        }
        now = "2026-01-01T00:00:00+00:00"
        self.conn.executemany(
            """
            INSERT INTO historical_backfill_queue(
                item_type, item_key, priority, status, created_at, updated_at,
                collection_lane
            ) VALUES ('PLAYER', ?, 100, 'PENDING', ?, ?, ?)
            """,
            [
                ("prediction-player", now, now, "PREDICTION"),
                ("classified-player", now, now, "ACL_CLASSIFIED"),
            ],
        )
        self.conn.commit()

        snapshot = set_lane_paused(self.conn, "ACL_CLASSIFIED", True)
        self.assertTrue(snapshot["lanes"]["ACL_CLASSIFIED"]["paused"])
        self.assertFalse(snapshot["lanes"]["PREDICTION"]["paused"])
        self.assertEqual(
            run_one(self.conn, lane="ACL_CLASSIFIED")["status"],
            "PAUSED",
        )
        self.assertEqual(run_one(self.conn, lane="PREDICTION")["status"], "COMPLETE")
        selected = process_item.call_args.args[1]
        self.assertEqual(selected["item_key"], "prediction-player")

    def test_seed_uses_known_players_without_duplicate_queue_items(self):
        self.conn.execute(
            """
            INSERT INTO players(player_id, display_name)
            VALUES (12, 'Player Twelve')
            """
        )
        self.conn.execute(
            """
            INSERT INTO player_rounds(
                event_id, match_id, game_id, round_no, player_id,
                gross_points, event_date, location_id
            ) VALUES (1, '1', 1, 1, 12, 8, '2026-01-01', 'venue-a')
            """
        )
        self.conn.commit()

        self.assertEqual(seed_known_players(self.conn), 1)
        self.assertEqual(seed_known_players(self.conn), 0)
        self.assertEqual(status_snapshot(self.conn)["queue"]["pending"], 1)

    @patch("historical_backfill._process_item")
    def test_scheduler_prevents_player_discovery_from_starving_events(
        self, process_item
    ):
        process_item.return_value = {
            "eventsDiscovered": 0,
            "playersDiscovered": 0,
            "gamesDownloaded": 0,
            "roundsAdded": 0,
            "authBlocked": 0,
        }
        now = "2026-01-01T00:00:00+00:00"
        self.conn.executemany(
            """
            INSERT INTO historical_backfill_queue(
                item_type, item_key, priority, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'PENDING', ?, ?)
            """,
            [
                ("PLAYER", "player-high-priority", 200, now, now),
                ("EVENT", "event-ready", 80, now, now),
            ],
        )
        self.conn.execute(
            """
            UPDATE historical_backfill_state
            SET tasks_completed=4, tasks_failed=0 WHERE state_id=1
            """
        )
        self.conn.commit()

        result = run_one(self.conn)

        self.assertEqual(result["status"], "COMPLETE")
        selected = process_item.call_args.args[1]
        self.assertEqual(selected["item_type"], "EVENT")

    @patch("historical_backfill._process_item")
    def test_priority_fast_lane_outranks_normal_work_schedule(
        self, process_item
    ):
        process_item.return_value = {
            "eventsDiscovered": 0,
            "playersDiscovered": 0,
            "gamesDownloaded": 0,
            "roundsAdded": 0,
            "authBlocked": 0,
            "networkRequests": 1,
        }
        now = "2026-01-01T00:00:00+00:00"
        self.conn.executemany(
            """
            INSERT INTO historical_backfill_queue(
                item_type, item_key, priority, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'PENDING', ?, ?)
            """,
            [
                ("GAME", "normal-game", 100, now, now),
                ("EVENT", "priority-event", 1000, now, now),
            ],
        )
        self.conn.commit()

        result = run_one(self.conn)

        selected = process_item.call_args.args[1]
        self.assertEqual(selected["item_key"], "priority-event")
        self.assertEqual(result["queuePriority"], 1000)

    def test_venue_export_groups_events_at_the_same_coordinates(self):
        rows = [
            (
                event_id, 11, f"Event {event_id}", date, "6:00 PM", "C",
                "D", "P", 1, "L", "O", "bracket", "Y", "Club 52",
                "Melbourne", "FL", "US", 28.1246495, -80.6776854, 0,
                "SWAP_CANDIDATE", "TEST", "RESOLVED", date, date,
            )
            for event_id, date in (
                (100, "2026-01-01"),
                (101, "2026-02-01"),
            )
        ]
        self.conn.executemany(
            """
            INSERT INTO discovered_events(
                event_id, bucket_id, event_name, event_date, advertised_time,
                status, match_type, bracket_type, blind_draw, event_type,
                event_sub_type, event_list_type, cobs_event, location_name,
                location_city, location_state, location_country, location_lat,
                location_lng, distance, format_candidate, format_basis,
                timezone_status, first_seen_at, last_seen_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            rows,
        )
        self.conn.commit()

        exported = venue_export_rows(self.conn)

        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["Venue"], "Club 52")
        self.assertEqual(exported[0]["Event_Count"], 2)
        self.assertEqual(exported[0]["First_Event_Date"], "2026-01-01")
        self.assertEqual(exported[0]["Latest_Event_Date"], "2026-02-01")

    @patch("historical_backfill.fetch_player_events")
    def test_player_task_expands_to_event_queue(self, fetch_events):
        fetch_events.return_value = (
            [{"eventId": 100, "eventName": "Historical Event"}],
            [{"source": "cache"}],
        )
        self.conn.execute(
            """
            INSERT INTO players(player_id, display_name)
            VALUES (12, 'Player Twelve')
            """
        )
        self.conn.execute(
            """
            INSERT INTO player_rounds(
                event_id, match_id, game_id, round_no, player_id,
                gross_points, event_date, location_id
            ) VALUES (1, '1', 1, 1, 12, 8, '2026-01-01', 'venue-a')
            """
        )
        self.conn.commit()
        seed_known_players(self.conn)

        result = run_one(self.conn)

        self.assertEqual(result["status"], "COMPLETE")
        event = self.conn.execute(
            """
            SELECT status FROM historical_backfill_queue
            WHERE item_type='EVENT' AND item_key='100'
            """
        ).fetchone()
        self.assertIsNotNone(event)
        self.assertEqual(event["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
