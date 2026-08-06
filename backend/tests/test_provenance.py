from __future__ import annotations

import sqlite3
import unittest

from provenance import (
    canonical_payload_hash,
    coverage_summary,
    initialize_provenance_schema,
    record_ingestion_attempt,
    record_source_payload,
)


class ProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        initialize_provenance_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_hash_is_independent_of_object_key_order(self) -> None:
        self.assertEqual(
            canonical_payload_hash({"b": 2, "a": 1}),
            canonical_payload_hash({"a": 1, "b": 2}),
        )

    def test_identical_payload_is_deduplicated_without_losing_attempts(self) -> None:
        payload = {"status": "OK", "data": {"playerCPI": 6.35}}
        first_id = record_source_payload(
            self.conn,
            source_endpoint="swap-standings",
            entity_key="event:254035",
            request_url="https://example.test/swap-standings/254035",
            payload=payload,
            retrieved_at="2026-07-25T10:00:00+00:00",
            source_effective_at="2026-07-22T13:29:30",
            http_status=200,
        )
        second_id = record_source_payload(
            self.conn,
            source_endpoint="swap-standings",
            entity_key="event:254035",
            request_url="https://example.test/swap-standings/254035",
            payload={"data": {"playerCPI": 6.35}, "status": "OK"},
            retrieved_at="2026-07-25T11:00:00+00:00",
            http_status=200,
        )
        self.assertEqual(first_id, second_id)
        count = self.conn.execute("SELECT COUNT(*) FROM source_payloads").fetchone()[0]
        self.assertEqual(count, 1)

        record_ingestion_attempt(
            self.conn,
            source_endpoint="swap-standings",
            entity_key="event:254035",
            outcome="success",
            source_payload_id=first_id,
        )
        record_ingestion_attempt(
            self.conn,
            source_endpoint="swap-standings",
            entity_key="event:254035",
            outcome="cache_hit",
            source_payload_id=second_id,
        )
        self.assertEqual(coverage_summary(self.conn)["attempted"], 2)

    def test_coverage_keeps_auth_blocked_separate_from_other_failures(self) -> None:
        for outcome in ("success", "auth_blocked", "http_error", "network_error"):
            record_ingestion_attempt(
                self.conn,
                source_endpoint="match-stats",
                entity_key=f"game:{outcome}",
                outcome=outcome,
                http_status=403 if outcome == "auth_blocked" else None,
            )
        coverage = coverage_summary(self.conn, source_endpoint="match-stats")
        self.assertEqual(coverage["attempted"], 4)
        self.assertEqual(coverage["available"], 1)
        self.assertEqual(coverage["unavailable"], 3)
        self.assertEqual(coverage["auth_blocked"], 1)

    def test_unknown_outcome_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            record_ingestion_attempt(
                self.conn,
                source_endpoint="match-stats",
                entity_key="game:1",
                outcome="missing",
            )


if __name__ == "__main__":
    unittest.main()
