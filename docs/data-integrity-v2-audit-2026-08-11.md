# Data Integrity v2 production-copy audit — 2026-08-11

The audit ran against an online SQLite backup at
`/opt/cheesebaggers/v2-audit/season_platform.v2-audit.db`. The live database and
services were not modified.

## Inventory

- Production snapshot size: 2,395,545,600 bytes
- Normalized player-round rows: 1,016,925 before copy-only reconciliation
- Normalized games: 39,630
- Normalized events: 5,313
- Loose match-stat files: 1,343
- Hash-verified archived match-stat payloads: 37,783 unique game sources
- Combined unique game sources: 38,655 (97.5% of normalized-game count)

## Projected v2 classification

- Completed sources: 38,604
- Verified completed games: 38,541
- Quarantined completed games: 63
- Partial/live sources retained raw-only: 51
- Completed-source pass rate: 99.84%

The initial archive scan falsely rejected 1,916 payloads because the audit hash
escaped Unicode while the provenance archive preserves Unicode. The verifier was
corrected and the rerun reported zero unreadable archives.

Six singles games used ACL's shared placeholder team identifier. V2 now permits
that raw convention for singles and normalizes each player to a distinct
player-specific team. The same condition remains invalid for doubles.

## Remaining work before production apply

- Review the 63 structurally quarantined completed games.
- Decide how to treat approximately 975 normalized games without an immediately
  available raw source; they remain legacy-unverified and ineligible for v2
  certification.
- Take a fresh database backup immediately before applying migration.
- Run the idempotent migration in controlled batches and confirm the global and
  per-event integrity endpoints after each batch.
