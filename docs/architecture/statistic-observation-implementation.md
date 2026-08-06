# ACL Statistic Observation Layer

Implementation date: 2026-07-25  
Scope: cutoff-aware ACL CPI/PPR observations extracted from immutable source payloads

## Purpose

Prediction features no longer need to read raw ACL payloads containing names, email
addresses, phone numbers, locations, or photos. The ingestion layer extracts only the
statistic, player ID, source, scope, and timing metadata needed for modeling.

## Observation types

- `ACL_REPORTED_CPI`
- `ACL_REPORTED_PROFILE_PPR`
- `ACL_REPORTED_SEASON_PPR`
- `ACL_REPORTED_EVENT_PPR`
- `ACL_REPORTED_GAME_PPR`

These remain separate observations and are never collapsed into one generic PPR field.

## Sources

| Observation | Extracted source |
|---|---|
| CPI and profile PPR | Swap and Swiss/Rounders roster, schedule, standings, and up-next player rows |
| Season/bucket PPR | `player-compare-stats.data[].ptsPerRnd` |
| Event PPR | `event-player-stats.data[].ptsPerRnd` |
| Game PPR | `match-stats.event_match_details[].ptsperrnd` |

Repeated embedded player rows within one payload are deduplicated when player, statistic,
value, and ACL effective timestamp are identical. Conflicting values remain separate
evidence.

## Stored provenance

Every observation includes:

- immutable source payload ID;
- endpoint and JSON path;
- player ID;
- statistic type;
- numeric and raw value;
- event/game/bucket/source scope;
- bucket ID where applicable;
- ACL effective timestamp when supplied;
- retrieval timestamp;
- availability classification; and
- record creation time.

No player name, email, phone, city/state, or photo is copied into the statistic table.

## Availability classifications

| Status | Meaning | Cutoff eligible |
|---|---|---|
| `AVAILABLE` | Valid, finite, nonzero statistic | Yes, subject to timing |
| `ZERO_UNVALIDATED` | ACL supplied zero but zero is not established as measured performance | No |
| `MISSING` | Null/empty/sentinel value | No |
| `INVALID_VALUE` | Non-numeric or non-finite value | No |
| `INVALID_EFFECTIVE_TIME` | ACL supplied an unparseable effective timestamp | No |

## Temporal eligibility

An observation is eligible only when:

1. availability is `AVAILABLE`;
2. `retrieved_at <= data_cutoff_at`; and
3. if ACL supplied an effective timestamp, `source_effective_at <= data_cutoff_at`.

Both checks are required. An ACL timestamp from July 22 captured on July 25 cannot be used
in a July 23 historical backtest because the platform did not possess the observation at
that time.

PPR observations without an ACL effective timestamp become eligible at retrieval time.

## Integration

Successful network responses, cache hits, and HTTP 304 cache reuse now invoke the extractor.
The operation is idempotent for the same immutable source payload.

## Tests

The combined provenance/statistic suite contains 11 passing tests, including:

- PII exclusion from statistic rows;
- deduplication of repeated embedded player snapshots;
- future CPI exclusion;
- retrieval-time eligibility for PPR;
- zero and invalid-timestamp exclusion;
- distinct event/game PPR types; and
- the provenance and coverage tests from the previous slice.

## Next slice

Build cutoff-aware feature queries that combine:

- latest eligible ACL snapshot observations;
- calculated rolling match statistics;
- retrieved/expected/blocked/failed coverage;
- recency and sample size; and
- format and partnership/team context.

The first model remains the Stage A baseline and must not require CPI.

**Implemented:** see
[`stage-a-feature-builder-implementation.md`](./stage-a-feature-builder-implementation.md).
