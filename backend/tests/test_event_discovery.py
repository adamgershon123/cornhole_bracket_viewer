from __future__ import annotations

import json
import sqlite3
import unittest

from event_discovery import _format_candidate, redact_discovery_payload, search_acl_events
from season_platform import init_db


class Response:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        return None


class Session:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.payload)


class EventDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_redaction_is_recursive_and_highlighted(self) -> None:
        sanitized, count = redact_discovery_payload({
            "playerEmail": "person@example.test",
            "data": [{"phone": "555-0100"}, {"eventID": 1}],
        })
        self.assertEqual(count, 2)
        self.assertEqual(
            sanitized["playerEmail"],
            "[REDACTED_PERSONAL_DATA]",
        )
        self.assertEqual(
            sanitized["data"][0]["phone"],
            "[REDACTED_PERSONAL_DATA]",
        )

    def test_structured_bracket_type_overrides_swap_in_generated_name(self) -> None:
        candidate, basis = _format_candidate({
            "leagueName": "Weekly Swap - Swap Final Bracket 1",
            "bracketType": "D",
            "blindDraw": True,
        })
        self.assertEqual(candidate, "BRACKET_CANDIDATE")
        self.assertEqual(basis, "BRACKET_TYPE")

    def test_search_posts_payload_indexes_events_and_excludes_registration_rows(self) -> None:
        session = Session({
            "status": "OK",
            "event_count": 2,
            "data": [
                {
                    "eventID": 254070,
                    "leagueName": "Doubles Rounders",
                    "leagueStartDate": "2026-07-26",
                    "leagueTime": "9:00 AM",
                    "leagueStatus": "A",
                    "matchType": "D",
                    "bracketType": "W",
                    "eventListType": "bracket",
                    "mapLat": 47.3,
                    "mapLng": 11.6,
                    "playerEmail": "private@example.test",
                },
                {
                    "regEventID": 100,
                    "eventListType": "reg",
                    "playerEmail": "also-private@example.test",
                },
            ],
        })
        result = search_acl_events(
            self.conn,
            bucket_id=11,
            origin_lat=26.78,
            origin_lng=-80.32,
            session=session,
        )
        self.assertEqual(result["reportedEventCount"], 2)
        self.assertEqual(result["indexedEventCount"], 1)
        self.assertEqual(result["redactedFieldCount"], 2)
        url, request = session.calls[0]
        self.assertIn("bucket_id=11", url)
        self.assertEqual(request["json"]["selectedTime"], "WEEK")
        event = self.conn.execute(
            "SELECT * FROM discovered_events WHERE event_id=254070"
        ).fetchone()
        self.assertEqual(event["format_candidate"], "SWISS_CANDIDATE")
        self.assertEqual(event["timezone_status"], "UNRESOLVED")
        stored = self.conn.execute(
            "SELECT payload_json FROM source_payloads WHERE source_endpoint='events-radius'"
        ).fetchone()[0]
        self.assertNotIn("private@example.test", stored)
        self.assertIn("[REDACTED_PERSONAL_DATA]", stored)
        request_json = self.conn.execute(
            "SELECT request_json FROM event_discovery_searches"
        ).fetchone()[0]
        self.assertEqual(json.loads(request_json)["eventRange"], 10000)


if __name__ == "__main__":
    unittest.main()
