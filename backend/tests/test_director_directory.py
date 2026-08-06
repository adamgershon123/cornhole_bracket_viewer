import sqlite3
import unittest

from director_directory import director_directory, index_director_event_payload


class DirectorDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_indexes_director_venue_event_and_attendance(self):
        payload = {
            "eventInfo": {
                "eventID": 42, "eventName": "Friday Blind Draw", "startdate": "2026-08-01",
                "starttime": "7:00 PM", "eventAdminID": 9, "adminFirstName": "Dana",
                "adminLastName": "Director", "adminEmail": "dana@example.com",
                "leagueLocationID": 12, "leagueLocationName": "The Hall",
                "leagueAddress": "1 Main St", "locationCity": "Town", "locationState": "FL",
                "locationZip": "33000", "countryCode": "US", "teamCount": 2, "matchType": "D",
            },
            "bracketDetails": [
                {"player_info": [{"playerid": 1, "firstname": "A"}, {"playerid": 2, "firstname": "B"}]},
                {"player_info": [{"playerid": 3, "firstname": "C"}, {"playerid": 4, "firstname": "D"}]},
            ],
        }
        result = index_director_event_payload(self.conn, payload, source_payload_id=7)
        self.assertTrue(result["indexed"])
        self.assertEqual(result["playerCount"], 4)

        directors = director_directory(self.conn, view="DIRECTORS")
        self.assertEqual(directors["rows"][0]["display_name"], "Dana Director")
        self.assertEqual(directors["rows"][0]["average_players"], 4.0)
        venues = director_directory(self.conn, view="VENUES")
        self.assertEqual(venues["rows"][0]["venue_name"], "The Hall")
        self.assertEqual(venues["rows"][0]["event_count"], 1)
        events = director_directory(self.conn, view="EVENTS", state="FL")
        self.assertEqual(events["rows"][0]["director_email"], "dana@example.com")


if __name__ == "__main__":
    unittest.main()
