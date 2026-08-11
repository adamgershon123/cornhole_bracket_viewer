# Data Integrity v2

Data Integrity v2 makes the preserved ACL response the source record and allows
only reconciled final games into the analytics ledger.

## Game states

- `PARTIAL`: live payload retained as raw data only; it is not eligible for profiles or models.
- `VERIFIED`: final payload passed structural checks and exactly matches normalized rows.
- `QUARANTINED`: final payload or normalized output failed at least one check and is withheld.

Checks include player/round uniqueness, two opposing teams per round, sequential
rounds, stable player-team assignment, legal scores, four-bag totals, declared
player totals when supplied, and exact raw-to-normalized value reconciliation.

## Operational endpoints

- `GET /api/data-integrity/status`
- `GET /api/events/{event_id}/data-integrity`

`legacyUnverifiedGames` is the number of existing ledger games that do not yet
have a v2 verified source. `migrationReady` remains false while any such game or
quarantined game exists.

## Historical migration

The cloud worker audits in dry-run mode by default. It will not rewrite the
historical ledger until `DATA_INTEGRITY_V2_APPLY=1` is explicitly set.

Manual dry run:

```powershell
python integrity_backfill.py --database <db-path> --data-dir <raw-data-path>
```

Controlled apply after reviewing the dry-run totals and taking a database backup:

```powershell
python integrity_backfill.py --database <db-path> --data-dir <raw-data-path> --apply
```

The migration is idempotent. A game is skipped when its payload hash and
integrity version already match. Derived v2 artifacts record their calculation
and integrity versions; stale v1 report cards are withheld until regenerated
from certified sources.
