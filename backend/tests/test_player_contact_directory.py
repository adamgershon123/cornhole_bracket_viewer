import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from player_contact_directory import (
    index_contact_payload,
    player_contact_directory,
    refresh_player_contact_index,
)


class PlayerContactDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "schedules").mkdir()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE players(
                player_id INTEGER PRIMARY KEY, display_name TEXT, first_name TEXT, last_name TEXT,
                city TEXT, state TEXT, profile_image TEXT, skill_level TEXT, is_pro INTEGER,
                membership_name TEXT, membership_type TEXT
            );
            CREATE TABLE player_analytics_snapshots(player_id INTEGER PRIMARY KEY, snapshot_json TEXT);
            INSERT INTO players VALUES(10,'Player Ten','Player','Ten','Town','FL',NULL,'PRO',1,'Platinum','P');
            INSERT INTO players VALUES(20,'Player Twenty','Player','Twenty',NULL,NULL,NULL,NULL,0,NULL,NULL);
            INSERT INTO player_analytics_snapshots VALUES(10,'{"calculatedPpr":8.25,"rounds":120}');
            """
        )

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def write(self, name, payload):
        (self.root / "schedules" / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_indexes_only_player_identified_contacts(self):
        self.write("event_1.json", {
            "data": {
                "eventInfo": {"playerEmail": "director@example.com"},
                "players": [
                    {"playerID": 10, "playerEmail": "ten@example.com", "playerPhoneNo": "555-0100", "leagueID": 1},
                    {"playerID": 20, "playerEmail": "", "playerPhoneNo": "", "leagueID": 1},
                ],
            },
        })
        result = refresh_player_contact_index(self.conn, self.root)
        self.assertEqual(result["indexedPlayers"], 1)
        row = self.conn.execute("SELECT * FROM player_contacts WHERE player_id=10").fetchone()
        self.assertEqual(row["email"], "ten@example.com")
        self.assertEqual(row["phone"], "555-0100")

        directory = player_contact_directory(self.conn, contact="BOTH")
        self.assertEqual(directory["total"], 1)
        self.assertEqual(directory["players"][0]["playerName"], "Player Ten")
        self.assertEqual(directory["players"][0]["calculatedPpr"], 8.25)

    def test_later_partial_record_does_not_erase_existing_contact(self):
        self.write("event_1.json", {"players": [{
            "playerID": 10, "playerEmail": "ten@example.com", "playerPhoneNo": "555-0100",
        }]})
        refresh_player_contact_index(self.conn, self.root)
        self.write("event_2.json", {"players": [{
            "playerID": 10, "playerEmail": "", "playerPhoneNo": "555-0101",
        }]})
        refresh_player_contact_index(self.conn, self.root)
        row = self.conn.execute("SELECT email,phone FROM player_contacts WHERE player_id=10").fetchone()
        self.assertEqual(row["email"], "ten@example.com")
        self.assertEqual(row["phone"], "555-0101")

    def test_indexes_fresh_schedule_payload_without_file_rescan(self):
        result = index_contact_payload(
            self.conn,
            {"players": [{
                "playerID": 20,
                "playerEmail": "twenty@example.com",
                "playerPhoneNo": "555-0200",
            }]},
            source_endpoint="swap-schedule-breakdown",
            source_event_id=99,
        )
        self.assertEqual(result["playersChanged"], 1)
        row = self.conn.execute(
            "SELECT email,source_event_id FROM player_contacts WHERE player_id=20"
        ).fetchone()
        self.assertEqual(row["email"], "twenty@example.com")
        self.assertEqual(row["source_event_id"], "99")

    def test_redaction_marker_is_never_treated_as_private_contact_data(self):
        index_contact_payload(
            self.conn,
            {"players": [{
                "playerID": 10,
                "playerEmail": "[REDACTED_PERSONAL_DATA]",
                "playerPhoneNo": "[REDACTED_PERSONAL_DATA]",
            }]},
            source_endpoint="schedule",
        )
        self.assertIsNone(self.conn.execute(
            "SELECT email FROM player_contacts WHERE player_id=10"
        ).fetchone())

        self.conn.execute(
            "INSERT INTO player_contacts VALUES(10,'[REDACTED_PERSONAL_DATA]','[REDACTED_PERSONAL_DATA]','old',NULL,'old',NULL,'now','now')"
        )
        directory = player_contact_directory(self.conn)
        player = next(row for row in directory["players"] if row["playerId"] == 10)
        self.assertIsNone(player["email"])
        self.assertIsNone(player["phone"])


if __name__ == "__main__":
    unittest.main()
