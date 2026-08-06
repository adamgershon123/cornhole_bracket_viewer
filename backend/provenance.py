from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


OUTCOMES = {"success", "cache_hit", "not_modified", "auth_blocked", "http_error", "network_error"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_payload_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def initialize_provenance_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_payloads (
            source_payload_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_system TEXT NOT NULL DEFAULT 'ACL',
            source_endpoint TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            request_url TEXT,
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            local_path TEXT,
            source_effective_at TEXT,
            retrieved_at TEXT NOT NULL,
            http_status INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(source_system, source_endpoint, entity_key, payload_hash)
        );

        CREATE TABLE IF NOT EXISTS ingestion_attempts (
            ingestion_attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            source_system TEXT NOT NULL DEFAULT 'ACL',
            source_endpoint TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            request_url TEXT,
            attempted_at TEXT NOT NULL,
            outcome TEXT NOT NULL,
            http_status INTEGER,
            source_payload_id INTEGER,
            error_kind TEXT,
            error_message TEXT,
            FOREIGN KEY(source_payload_id) REFERENCES source_payloads(source_payload_id),
            CHECK(outcome IN (
                'success', 'cache_hit', 'not_modified', 'auth_blocked',
                'http_error', 'network_error'
            ))
        );

        CREATE INDEX IF NOT EXISTS idx_source_payload_lookup
            ON source_payloads(source_endpoint, entity_key, retrieved_at);

        CREATE INDEX IF NOT EXISTS idx_ingestion_attempt_coverage
            ON ingestion_attempts(source_endpoint, entity_key, attempted_at, outcome);
        """
    )
    from payload_archive import initialize_payload_archive_schema

    initialize_payload_archive_schema(conn)
    conn.commit()


def record_source_payload(
    conn: sqlite3.Connection,
    *,
    source_endpoint: str,
    entity_key: str,
    request_url: str | None,
    payload: Any,
    retrieved_at: str | None = None,
    source_effective_at: str | None = None,
    http_status: int | None = None,
    local_path: str | None = None,
) -> int:
    initialize_provenance_schema(conn)
    observed_at = retrieved_at or utc_now()
    digest = canonical_payload_hash(payload)
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    conn.execute(
        """
        INSERT INTO source_payloads (
            source_endpoint, entity_key, request_url, payload_hash, payload_json,
            local_path, source_effective_at, retrieved_at, http_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_system, source_endpoint, entity_key, payload_hash) DO NOTHING
        """,
        (
            source_endpoint,
            entity_key,
            request_url,
            digest,
            serialized,
            local_path,
            source_effective_at,
            observed_at,
            http_status,
            utc_now(),
        ),
    )
    row = conn.execute(
        """
        SELECT source_payload_id
        FROM source_payloads
        WHERE source_system='ACL'
          AND source_endpoint=?
          AND entity_key=?
          AND payload_hash=?
        """,
        (source_endpoint, entity_key, digest),
    ).fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("Source payload insert could not be resolved")
    return int(row[0])


def record_ingestion_attempt(
    conn: sqlite3.Connection,
    *,
    source_endpoint: str,
    entity_key: str,
    outcome: str,
    request_url: str | None = None,
    attempted_at: str | None = None,
    http_status: int | None = None,
    source_payload_id: int | None = None,
    run_id: str | None = None,
    error_kind: str | None = None,
    error_message: str | None = None,
) -> int:
    if outcome not in OUTCOMES:
        raise ValueError(f"Unsupported ingestion outcome: {outcome}")
    initialize_provenance_schema(conn)
    cursor = conn.execute(
        """
        INSERT INTO ingestion_attempts (
            run_id, source_endpoint, entity_key, request_url, attempted_at,
            outcome, http_status, source_payload_id, error_kind, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source_endpoint,
            entity_key,
            request_url,
            attempted_at or utc_now(),
            outcome,
            http_status,
            source_payload_id,
            error_kind,
            error_message,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def coverage_summary(
    conn: sqlite3.Connection,
    *,
    source_endpoint: str | None = None,
    run_id: str | None = None,
) -> dict[str, int]:
    initialize_provenance_schema(conn)
    clauses: list[str] = []
    params: list[Any] = []
    if source_endpoint is not None:
        clauses.append("source_endpoint=?")
        params.append(source_endpoint)
    if run_id is not None:
        clauses.append("run_id=?")
        params.append(run_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT outcome, COUNT(*) AS count
        FROM ingestion_attempts
        {where}
        GROUP BY outcome
        """,
        params,
    ).fetchall()
    result = {outcome: 0 for outcome in sorted(OUTCOMES)}
    for row in rows:
        result[str(row[0])] = int(row[1])
    result["attempted"] = sum(result.values())
    result["available"] = result["success"] + result["cache_hit"] + result["not_modified"]
    result["unavailable"] = result["auth_blocked"] + result["http_error"] + result["network_error"]
    return result
