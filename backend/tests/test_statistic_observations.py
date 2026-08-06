from __future__ import annotations

import sqlite3
import unittest

from provenance import initialize_provenance_schema, record_source_payload
from statistic_observations import (
    eligible_observations,
    extract_statistic_observations,
    initialize_statistic_schema,
)


class StatisticObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        initialize_provenance_schema(self.conn)
        initialize_statistic_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_payload(
        self,
        endpoint: str,
        entity_key: str,
        payload: dict,
        retrieved_at: str = "2026-07-25T12:00:00+00:00",
    ) -> int:
        return record_source_payload(
            self.conn,
            source_endpoint=endpoint,
            entity_key=entity_key,
            request_url=f"https://example.test/{endpoint}",
            payload=payload,
            retrieved_at=retrieved_at,
            http_status=200,
        )

    def test_public_snapshot_extracts_cpi_and_profile_ppr_without_pii(self) -> None:
        player = {
            "playerID": 142125,
            "playerEmail": "not-stored@example.test",
            "playerPhoneNo": "15555555555",
            "playerCPI": 6.35,
            "playerPPR": 7.39,
            "cPITimeStamp": "2026-07-22 13:29:30",
        }
        payload = {"data": {"overAllSchedule": [{"homeTeam": [player, player]}]}}
        payload_id = self.add_payload(
            "swiss-pairing-schedule-breakdown",
            "swiss-pairing-schedule-breakdown:248002",
            payload,
        )

        count = extract_statistic_observations(
            self.conn,
            source_payload_id=payload_id,
            source_endpoint="swiss-pairing-schedule-breakdown",
            entity_key="swiss-pairing-schedule-breakdown:248002",
            payload=payload,
            retrieved_at="2026-07-25T12:00:00+00:00",
        )

        self.assertEqual(count, 2)
        rows = self.conn.execute(
            "SELECT * FROM statistic_observations ORDER BY statistic_type"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["scope_type"] for row in rows}, {"event"})
        self.assertEqual({row["scope_id"] for row in rows}, {"248002"})
        serialized = " ".join(str(dict(row)) for row in rows)
        self.assertNotIn("not-stored@example.test", serialized)
        self.assertNotIn("15555555555", serialized)

    def test_future_cpi_is_not_eligible_for_historical_cutoff(self) -> None:
        payload = {
            "data": [{
                "playerID": 142125,
                "playerCPI": 6.35,
                "cPITimeStamp": "2026-07-22 13:29:30",
            }]
        }
        payload_id = self.add_payload("swap-standings", "swap-standings:254035", payload)
        extract_statistic_observations(
            self.conn,
            source_payload_id=payload_id,
            source_endpoint="swap-standings",
            entity_key="swap-standings:254035",
            payload=payload,
            retrieved_at="2026-07-25T12:00:00+00:00",
        )

        before = eligible_observations(
            self.conn,
            player_id=142125,
            statistic_type="ACL_REPORTED_CPI",
            cutoff_at="2026-07-01T00:00:00+00:00",
        )
        after = eligible_observations(
            self.conn,
            player_id=142125,
            statistic_type="ACL_REPORTED_CPI",
            cutoff_at="2026-07-26T00:00:00+00:00",
        )
        self.assertEqual(before, [])
        self.assertEqual(len(after), 1)

    def test_retrieval_time_controls_ppr_without_effective_timestamp(self) -> None:
        payload = {"data": [{"playerID": 142125, "bucketID": 11, "ptsPerRnd": 7.39}]}
        payload_id = self.add_payload("player-compare-stats", "player:142125:bucket:11", payload)
        extract_statistic_observations(
            self.conn,
            source_payload_id=payload_id,
            source_endpoint="player-compare-stats",
            entity_key="player:142125:bucket:11",
            payload=payload,
            retrieved_at="2026-07-25T12:00:00+00:00",
        )

        self.assertEqual(
            eligible_observations(
                self.conn,
                player_id=142125,
                statistic_type="ACL_REPORTED_SEASON_PPR",
                cutoff_at="2026-07-25T11:59:59+00:00",
            ),
            [],
        )
        eligible = eligible_observations(
            self.conn,
            player_id=142125,
            statistic_type="ACL_REPORTED_SEASON_PPR",
            cutoff_at="2026-07-25T12:00:00+00:00",
        )
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]["bucket_id"], 11)

    def test_zero_and_invalid_timestamp_are_ineligible(self) -> None:
        payload = {
            "data": [
                {"playerID": 1, "playerCPI": 0, "cPITimeStamp": None},
                {"playerID": 2, "playerCPI": 5.5, "cPITimeStamp": "not-a-date"},
            ]
        }
        payload_id = self.add_payload("swap-standings", "swap-standings:1", payload)
        extract_statistic_observations(
            self.conn,
            source_payload_id=payload_id,
            source_endpoint="swap-standings",
            entity_key="swap-standings:1",
            payload=payload,
            retrieved_at="2026-07-25T12:00:00+00:00",
        )
        statuses = {
            row["player_id"]: row["availability_status"]
            for row in self.conn.execute("SELECT * FROM statistic_observations")
        }
        self.assertEqual(statuses[1], "ZERO_UNVALIDATED")
        self.assertEqual(statuses[2], "INVALID_EFFECTIVE_TIME")
        for player_id in (1, 2):
            self.assertEqual(
                eligible_observations(
                    self.conn,
                    player_id=player_id,
                    statistic_type="ACL_REPORTED_CPI",
                    cutoff_at="2027-01-01T00:00:00+00:00",
                ),
                [],
            )

    def test_event_and_game_ppr_types_are_distinct(self) -> None:
        event_payload = {"data": [{"playerID": 9, "ptsPerRnd": 8.1}]}
        game_payload = {"event_match_details": [{"playerid": 9, "ptsperrnd": 7.75}]}
        event_id = self.add_payload("event-player-stats", "event-player-stats:100", event_payload)
        game_id = self.add_payload("match-stats", "match-stats:100:5:1", game_payload)
        extract_statistic_observations(
            self.conn,
            source_payload_id=event_id,
            source_endpoint="event-player-stats",
            entity_key="event-player-stats:100",
            payload=event_payload,
            retrieved_at="2026-07-25T12:00:00+00:00",
        )
        extract_statistic_observations(
            self.conn,
            source_payload_id=game_id,
            source_endpoint="match-stats",
            entity_key="match-stats:100:5:1",
            payload=game_payload,
            retrieved_at="2026-07-25T12:00:00+00:00",
        )
        types = {
            row[0]
            for row in self.conn.execute(
                "SELECT statistic_type FROM statistic_observations"
            )
        }
        self.assertEqual(
            types,
            {"ACL_REPORTED_EVENT_PPR", "ACL_REPORTED_GAME_PPR"},
        )


if __name__ == "__main__":
    unittest.main()
