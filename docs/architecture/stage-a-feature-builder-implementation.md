# Stage A Cutoff-Aware Feature Builder

Implementation date: 2026-07-25  
Feature version: `stage-a-v1`

## Purpose

The Stage A builder produces modeling features from prior accessible match facts without
requiring CPI. It also supports optional cutoff-eligible ACL snapshots for analysis, but
those snapshots are not required for model readiness.

## Cutoff policy

Normalized historical match facts currently have an event date but not a consistently
trustworthy match timestamp. The builder therefore uses:

```text
event_date < date(data_cutoff_at)
```

All matches on the cutoff date are excluded. This conservative rule prevents same-day and
same-round leakage at the cost of omitting legitimately earlier matches from that day.
Precise timestamp support may replace this policy only after timestamps are normalized and
validated across formats.

## Player features

For a configurable prior-day window, the builder produces:

- events, games, and rounds;
- gross, opponent, and net points;
- calculated PPR, opponent PPR, and DPR;
- bag-in, bag-on, and bag-off rates;
- four-bagger rate;
- round win/loss/tie rates;
- most recent eligible event and recency;
- round counts by match/bracket format;
- expected/retrieved/blocked/error coverage; and
- explicit missing-history and unknown-coverage flags.

All rate denominators are retained through round, bag, and game counts. With no history,
rates remain null rather than becoming zero.

## Partnership features

For a multi-player side, partnership history is detected at game/team grain. This correctly
finds doubles partners even when they throw in alternating rounds and never share the same
round record.

The initial partnership features are:

- shared eligible games;
- shared eligible events; and
- known/unknown partnership.

## Side and matchup features

Player metrics are aggregated to a side using round-weighted means. The matchup builder
returns:

- complete player feature records for both sides;
- partnership information;
- side coverage;
- side A minus side B deltas; and
- a basic `modelReady` integrity flag.

Current deltas include calculated PPR, opponent PPR, DPR, bag rates, four-bagger rate, and
round win rate.

## Coverage integrity

Expected games are derived from indexed team membership and games. Retrieved games come
from normalized player-round records. A coverage ratio is published only when:

1. at least one expected game is indexed; and
2. every retrieved game is contained in the expected-game index.

If legacy indexing is incomplete, the builder reports:

- `coverageKnown: false`;
- `expectedGames: null`;
- `indexedExpectedGames` as diagnostic information;
- the actual retrieved count; and
- no coverage ratio.

This prevents impossible ratios above 100% from being presented as meaningful.

## Existing-data validation

For player `142125` at the 2026-07-25 cutoff, the local database produced:

- 186 eligible events;
- 627 retrieved games;
- 4,472 player-round records;
- calculated PPR `7.2321`;
- calculated DPR `-0.0282`; and
- latest eligible event date 2026-07-16.

The legacy expected-game index contained only 412 games, fewer than the 627 retrieved games.
The builder correctly classified coverage as unknown and withheld the ratio. This is an
index-quality finding, not evidence that retrieved history is complete.

## Tests

The combined suite now contains 16 passing tests. Stage A coverage includes:

- cutoff-day and future-event exclusion;
- PPR/DPR arithmetic;
- expected, retrieved, and 403-blocked coverage;
- invalid expected-index detection;
- alternating-round doubles partnership detection; and
- side-to-side feature deltas.

## Next slice

The next step is an evidence-tier and baseline scoring layer:

- translate coverage/history availability into `A`, `B`, `C`, or `NO_PREDICTION`;
- define a frozen numeric feature vector;
- implement equal-probability and rating/logistic baselines;
- persist immutable predictions with feature and model versions; and
- add chronological evaluation without CPI dependency.

The repository-wide validation prerequisite is complete. See
[`feature-quality-audit-2026-07-25.md`](./feature-quality-audit-2026-07-25.md).
