from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from provenance import coverage_summary
from season_platform import cached_get, init_db


class CachedGetProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self.temp_dir.name, "response.json")

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_cache_hit_creates_payload_observation_and_attempt(self) -> None:
        with open(self.cache_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "meta": {
                        "completionStatus": "complete",
                        "fetchedAt": "2026-07-25T10:00:00+00:00",
                        "statusCode": 200,
                    },
                    "payload": {"status": "OK", "data": [{"playerCPI": 6.35}]},
                },
                handle,
            )

        payload, meta = cached_get(
            self.conn,
            cache_key="swap-standings:254035",
            url="https://example.test/swap-standings/254035",
            source_endpoint="swap-standings",
            local_path=self.cache_path,
        )

        self.assertEqual(payload["status"], "OK")
        self.assertEqual(meta["source"], "cache")
        self.assertEqual(
            coverage_summary(self.conn, source_endpoint="swap-standings")["cache_hit"],
            1,
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM source_payloads").fetchone()[0],
            1,
        )

    @patch("season_platform.requests.get")
    def test_403_is_recorded_as_auth_blocked(self, get: Mock) -> None:
        response = requests.Response()
        response.status_code = 403
        response.url = "https://example.test/match-stats/1"
        response._content = b'{"message":"forbidden"}'
        get.return_value = response

        with self.assertRaises(requests.HTTPError):
            cached_get(
                self.conn,
                cache_key="match-stats:1:2:1",
                url=response.url,
                source_endpoint="match-stats",
                local_path=self.cache_path,
                force=True,
            )

        coverage = coverage_summary(self.conn, source_endpoint="match-stats")
        self.assertEqual(coverage["attempted"], 1)
        self.assertEqual(coverage["auth_blocked"], 1)
        self.assertEqual(coverage["available"], 0)


if __name__ == "__main__":
    unittest.main()
