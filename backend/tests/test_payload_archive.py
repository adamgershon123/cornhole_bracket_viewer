from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from payload_archive import (
    archive_pending_payloads,
    load_source_payload,
    payload_archive_health,
)
from provenance import initialize_provenance_schema, record_source_payload


class PayloadArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary.name) / "season_platform.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        initialize_provenance_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temporary.cleanup()

    def test_archives_verifies_and_restores_payload(self) -> None:
        payload = {
            "status": "OK",
            "data": [{"playerID": 142125, "playerPPR": 7.39}],
        }
        payload_id = record_source_payload(
            self.conn,
            source_endpoint="swap-standings",
            entity_key="event:254035",
            request_url="https://example.test/swap-standings/254035",
            payload=payload,
            http_status=200,
        )

        result = archive_pending_payloads(self.conn, limit=10)

        self.assertEqual(result["archived"], 1)
        row = self.conn.execute(
            """
            SELECT payload_json, archive_path, archive_verified_at
            FROM source_payloads WHERE source_payload_id=?
            """,
            (payload_id,),
        ).fetchone()
        self.assertEqual(row["payload_json"], "")
        self.assertTrue(row["archive_path"])
        self.assertTrue(row["archive_verified_at"])
        self.assertEqual(load_source_payload(self.conn, payload_id), payload)
        health = payload_archive_health(self.conn)
        self.assertEqual(health["archivedPayloads"], 1)
        self.assertEqual(health["pendingPayloads"], 0)
        self.assertGreater(health["sourceBytesArchived"], 0)
        self.assertGreater(health["archiveBytes"], 0)

    def test_hash_mismatch_never_clears_inline_payload(self) -> None:
        payload_id = record_source_payload(
            self.conn,
            source_endpoint="bracket-data",
            entity_key="bracket:1",
            request_url=None,
            payload={"status": "OK"},
        )
        self.conn.execute(
            "UPDATE source_payloads SET payload_hash='bad' WHERE source_payload_id=?",
            (payload_id,),
        )
        self.conn.commit()

        with self.assertRaises(ValueError):
            archive_pending_payloads(self.conn, limit=10)

        inline = self.conn.execute(
            "SELECT payload_json FROM source_payloads WHERE source_payload_id=?",
            (payload_id,),
        ).fetchone()[0]
        self.assertTrue(inline)


if __name__ == "__main__":
    unittest.main()
