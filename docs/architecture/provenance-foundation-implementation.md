# Provenance and Coverage Foundation

Implementation date: 2026-07-25  
Scope: first implementation slice for the prediction-engine data strategy

## Implemented

The existing SQLite season platform now initializes two append-only audit tables:

### `source_payloads`

Stores an immutable ACL response observation with:

- source system and endpoint;
- entity/cache key;
- request URL;
- canonical SHA-256 payload hash;
- raw payload JSON;
- local cache path;
- optional source-effective timestamp;
- retrieval timestamp;
- HTTP status; and
- record creation timestamp.

Identical payload content for the same endpoint/entity is deduplicated by canonical hash.
Different payload content creates a new observation rather than overwriting history.

### `ingestion_attempts`

Stores every observed retrieval attempt independently of payload deduplication:

- optional ingestion run ID;
- endpoint and entity key;
- request URL and attempt time;
- outcome;
- HTTP status;
- linked source payload when available; and
- error classification/message.

Supported outcomes:

- `success`;
- `cache_hit`;
- `not_modified`;
- `auth_blocked`;
- `http_error`; and
- `network_error`.

The coverage summary reports total attempted, available, unavailable, and each detailed
outcome. Authentication-blocked match statistics remain distinguishable from other failures.

## Integration

`season_platform.cached_get` now records:

- cache reuse;
- HTTP 304 reuse;
- successful network payloads;
- 401/403 as `auth_blocked`;
- other HTTP failures; and
- request/network failures.

This preserves the existing cache and manifest behavior while adding the evidence needed for
cutoff-aware feature calculations and coverage disclosures.

## Privacy boundary

`source_payloads.payload_json` is an internal raw-evidence record and may include personal
data returned by ACL. It must not be exposed through general prediction or public API
responses. Published fixtures and documentation remain redacted. A later access-control and
retention migration should restrict raw payload access and define deletion/retention rules
without weakening derived-record provenance.

## Tests

Automated tests cover:

- stable hashing independent of JSON object-key order;
- payload deduplication;
- preservation of repeated attempts;
- separate authentication-blocked coverage;
- invalid outcome rejection;
- cache-hit integration; and
- HTTP 403 integration.

## Next slice

Add immutable ACL statistic observations extracted from source payloads:

- ACL-reported CPI with ACL timestamp and retrieval time;
- ACL-reported season/event/game PPR with explicit scope;
- zero/null availability classification; and
- cutoff eligibility queries.

Those observations will support the first cutoff-aware feature builder without requiring the
prediction model to read raw personal-data-bearing payloads.

**Implemented:** see
[`statistic-observation-implementation.md`](./statistic-observation-implementation.md).
