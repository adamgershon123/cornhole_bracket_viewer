from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import Mock, patch

from acl_prediction_assistance import hydrate_acl_prediction_assistance
from season_platform import init_db


class AclPredictionAssistanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    @patch("acl_prediction_assistance.requests.post")
    def test_fetches_all_missing_players_in_one_batch_and_caches_them(
        self,
        post: Mock,
    ) -> None:
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "OK",
            "data": [
                {"playerID": 10, "bucketID": 11, "ptsPerRnd": 7.2},
                {"playerID": 20, "bucketID": 11, "ptsPerRnd": 8.1},
            ],
        }
        post.return_value = response

        first = hydrate_acl_prediction_assistance(
            self.conn,
            player_ids=[10, 20],
        )
        second = hydrate_acl_prediction_assistance(
            self.conn,
            player_ids=[10, 20],
        )

        self.assertEqual(first["requestCount"], 1)
        self.assertEqual(first["assistedPlayers"], 2)
        self.assertEqual(first["status"], "READY")
        self.assertEqual(second["requestCount"], 0)
        self.assertEqual(second["freshPlayers"], 2)
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
