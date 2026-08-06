import sqlite3
import unittest

from historical_backfill import initialize_schema, prioritize_events
from season_platform import init_db, upsert_event
from venue_analytics import venue_catalog, venue_court_ppr, venue_event_schedule


class VenueAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        initialize_schema(self.conn)
        for event_id, location_id, name, event_date in (
            (100, "3231", "Hurricane's Veterans Memorial Pkwy", "2025-09-01"),
            (101, "7681", "Hurricanes", "2026-03-02"),
        ):
            upsert_event(
                self.conn,
                {
                    "eventId": event_id,
                    "eventName": f"Event {event_id}",
                    "date": event_date,
                    "locationId": location_id,
                    "locationName": name,
                    "locationCity": "Port St. Lucie",
                    "locationState": "FL",
                    "locationCountry": "US",
                    "locationLat": 27.2756,
                    "locationLng": -80.3194,
                },
            )

    def tearDown(self):
        self.conn.close()

    def test_coordinate_aliases_are_one_venue(self):
        venues = venue_catalog(self.conn)
        self.assertEqual(len(venues), 1)
        self.assertEqual(set(venues[0]["locationIds"]), {"3231", "7681"})
        self.assertEqual(venues[0]["eventCount"], 2)

    def test_schedule_exposes_download_and_priority_state(self):
        venue = venue_catalog(self.conn)[0]
        result = venue_event_schedule(
            self.conn,
            venue_key=venue["venueKey"],
            start_date="2025-09-01",
            end_date="2026-08-31",
        )
        self.assertEqual(result["summary"]["notDownloaded"], 2)

        queued = prioritize_events(
            self.conn,
            [100, 101],
            source="test-venue-priority",
        )
        self.assertEqual(queued["prioritized"], 2)
        refreshed = venue_event_schedule(
            self.conn,
            venue_key=venue["venueKey"],
            start_date="2025-09-01",
            end_date="2026-08-31",
        )
        self.assertEqual(refreshed["summary"]["priorityQueued"], 2)

    def test_court_ppr_groups_events_courts_games_and_filters_players(self):
        self.conn.execute(
            """
            INSERT INTO games(
                event_id, match_id, game_id, home_score, away_score,
                completed, stats_downloaded
            ) VALUES (100, '1', 1, 21, 15, 1, 1)
            """
        )
        rows = [
            (1, 10, "Player Ten", 8),
            (2, 10, "Player Ten", 10),
            (1, 20, "Player Twenty", 6),
            (2, 20, "Player Twenty", 8),
        ]
        self.conn.executemany(
            """
            INSERT INTO player_rounds(
                event_id, match_id, game_id, round_no, player_id,
                player_name, court_id, gross_points, event_date, location_id
            ) VALUES (100, '1', 1, ?, ?, ?, '3', ?, '2025-09-01', '3231')
            """,
            rows,
        )
        self.conn.commit()
        venue = venue_catalog(self.conn)[0]

        all_players = venue_court_ppr(
            self.conn,
            venue_key=venue["venueKey"],
            start_date="2025-09-01",
            end_date="2026-08-31",
        )
        self.assertEqual(all_players["events"][0]["ppr"], 8.0)
        self.assertEqual(all_players["events"][0]["courts"][0]["courtId"], "3")
        self.assertEqual(all_players["events"][0]["courts"][0]["games"][0]["ppr"], 8.0)

        filtered = venue_court_ppr(
            self.conn,
            venue_key=venue["venueKey"],
            start_date="2025-09-01",
            end_date="2026-08-31",
            player_ids=[10],
        )
        self.assertEqual(filtered["summary"]["ppr"], 9.0)
        self.assertEqual(filtered["events"][0]["courts"][0]["games"][0]["players"][0]["playerId"], 10)


if __name__ == "__main__":
    unittest.main()
