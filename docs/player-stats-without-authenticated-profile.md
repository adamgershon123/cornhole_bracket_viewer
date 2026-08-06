# Player Statistics Strategy Without the Authenticated Profile Endpoint

Status: **Proposed for ACL API review and Phase 1 ingestion design**

Empirical test result:
[`acl-api-tests/public-cpi-history-test-2026-07-25.md`](./acl-api-tests/public-cpi-history-test-2026-07-25.md).

## Goal

Collect ACL-reported CPI and historical PPR without depending on:

```text
GET /api/auth/v1/players/{player_id}
```

The platform must preserve ACL-reported values separately from Cheesebaggers calculations,
retain provenance, and disclose incomplete coverage.

## Recommended source hierarchy

| Statistic need | Primary unauthenticated source | Secondary source | Cheesebaggers fallback |
|---|---|---|---|
| Current ACL CPI | Event roster/standing rows containing `playerCPI` and `cPITimeStamp` | Other public event payloads containing the same fields | None—CPI is never calculated or inferred |
| Historical ACL CPI | Cheesebaggers' own periodic public-endpoint snapshots collected going forward | Existing saved observations with valid CPI timestamps, treated cautiously | None; report pre-collection history as unavailable when not proven |
| ACL season/bucket PPR | `POST /api/v1/player-compare-stats` using `playerIDs` and `bucketID` | Public player/event rows containing `playerPPR` | None; preserve the value as ACL-reported |
| ACL event PPR | `GET /api/v1/event-player-stats/{event_id}` using `ptsPerRnd` | `event-standings` or swap standings if scope is confirmed | None; preserve as ACL-reported |
| ACL match PPR | Public `match-stats` `event_match_details[].ptsperrnd` when accessible | None | Calculate independently from available round facts and label `CHEESEBAGGERS_CALCULATED` |
| Cheesebaggers historical PPR | Retained `event_match_inning_history[]` round facts | Player points/round totals from accessible match/event payloads | Calculate only from known included records and expose coverage |

## Available unauthenticated endpoints

### `POST /api/v1/player-compare-stats`

Best candidate for ACL season/bucket aggregates.

A populated unauthenticated response has now been validated. See
[`acl-api-endpoints/player-compare-stats.md`](./acl-api-endpoints/player-compare-stats.md).

Request:

```json
{
  "playerIDs": [142125],
  "bucketID": 11
}
```

Relevant returned fields currently consumed by code:

- `bucketID`
- `yearDesc`
- `ptsPerRnd`
- `DPR`
- `OppPtsPerRnd`
- bag totals and percentages
- four-bagger totals and percentage
- round totals/win/loss/tie rates
- total player and opponent points

Use this as an ACL-reported bucket snapshot, not as a fact table. Store request bucket,
retrieval time, raw response, and source classification.

For player `142125`, bucket `11`, the endpoint returned PPR `7.39`, matching the
authenticated profile value. It did not return CPI. The response message called the result
“Career” while `yearDesc` identified `2025 - 2026`, so scope terminology remains unresolved.

Open questions:

- Which bucket IDs exist and how can they be enumerated?
- Does one bucket equal one ACL season in every case?
- Does the response include all event levels and formats?
- Does it combine singles and doubles?
- Are withdrawn, incomplete, forfeited, or corrected matches included?
- Is `ptsPerRnd` rounded from hidden higher-precision data?

### `GET /api/v1/event-player-stats/{event_id}`

Best candidate for ACL-reported event aggregates.

A populated 60-player response has been validated, and every row's PPR, opponent PPR, DPR,
bag totals/percentages, and four-bagger rate reconciled arithmetically. See
[`acl-api-endpoints/event-player-stats.md`](./acl-api-endpoints/event-player-stats.md).

Relevant fields:

- `playerID`
- `rounds`
- `totalPts`
- `ptsPerRnd`
- `opponentPts`
- `opponentPtsPerRnd`
- `diffPerRnd`
- bag placement percentages
- four-bagger count/rate

This endpoint provides an event-level PPR observation and its reported round count. It is
valuable for reconciling independently calculated PPR and identifying missing match data.

### Public event roster/standing endpoints

Observed fields include:

- `playerID` / `fldPlayerID`
- `playerPPR`
- `playerPPRPlayerInfo`
- `playerCPI`
- `cPITimeStamp`

Observed in:

- `swap-standings/{event_id}`
- player rows within `swap-schedule-breakdown/{event_id}`
- potentially `swap-up-next-players-list/{event_id}`
- potentially analogous Swiss/Rounders endpoints

These are the best current unauthenticated source of CPI. They are event-scoped copies of a
player value, however, and may reflect the player's current ACL profile value rather than
the value as of the event date.

A completed 64-player swap response for event `254035` confirmed that this endpoint can
provide a pre-event CPI/PPR snapshot for registered players. See
[`acl-api-endpoints/swap-standings.md`](./acl-api-endpoints/swap-standings.md). Eligibility
still depends on `cPITimeStamp`, not event date alone.

## CPI collection strategy

### Current CPI

1. When any public event payload contains a player row, capture:
   - `playerID`;
   - `playerCPI`;
   - `cPITimeStamp`;
   - endpoint;
   - event ID;
   - retrieval time;
   - raw payload ID/hash.
2. Store the observation append-only.
3. Deduplicate exact observations by source, player, CPI value, CPI timestamp, and payload
   hash.
4. Select the latest known official CPI only by an explicit rule:
   - greatest valid `cPITimeStamp`;
   - then greatest retrieval time as a deterministic tie breaker.
5. If `cPITimeStamp` is absent or invalid, retain the observation but do not silently order
   it ahead of timestamped observations.

### Historical CPI

Historical CPI cannot be reliably reconstructed by downloading old events. The primary
strategy is to collect public CPI observations prospectively on a schedule and preserve
each change append-only.

Recommended collection cadence:

- daily for active/production players;
- immediately before every production prediction;
- at event ingestion and event completion;
- at observed ACL season/bucket transitions;
- on demand when a player profile or prediction page is opened, subject to caching and rate
  controls.

Historical payloads may still contain useful older observations, but they are evidence of a
CPI value at the supplied CPI timestamp—not proof of the value at the event date.

Classify each CPI observation:

- `SOURCE_EFFECTIVE_TIME_KNOWN` — ACL supplied a valid `cPITimeStamp`;
- `RETRIEVAL_TIME_ONLY` — value is known only as of capture;
- `EVENT_TIME_NOT_PROVEN` — the value appears in an old event payload but may have been
  joined from the current player profile;
- `CONFLICTING_OBSERVATION` — same effective timestamp has different CPI values.

Testing on 2026-07-25 proved that old event rosters do not reliably preserve event-time
CPI. Most tested old events returned the current profile CPI/timestamp, while one returned
an older snapshot whose CPI timestamp was still after the event date. Therefore:

- the UI must call this an “observed ACL CPI history,” not event-time CPI history;
- `cPITimeStamp`, not event date, controls temporal eligibility;
- a CPI observation with a timestamp after the prediction cutoff is excluded;
- a CPI observation without a valid effective timestamp is known only at retrieval time.

The older result from event `216959` may be a prior-season/bucket snapshot or a stale
event-cache anomaly. Both explanations are plausible; neither is proven. It must not define
a season boundary until tests across known bucket IDs, boundary dates, and multiple players
show the same behavior.

### Revised practical limitation

The platform may not have trustworthy ACL CPI history before it begins scheduled
observation collection. That gap should be represented explicitly:

- `HISTORICAL_CPI_OBSERVED` when an eligible timestamped observation exists;
- `CURRENT_CPI_ONLY` when only a current observation exists;
- `CPI_UNAVAILABLE_AT_CUTOFF` when no observation was knowable by the prediction cutoff.

For historical backtests with no eligible CPI, the model must use a documented missing-CPI
path and missingness indicator. It must not substitute today's CPI or infer a historical
CPI from performance.

## Historical PPR collection strategy

Maintain three separate PPR series.

### 1. ACL bucket PPR

From `player-compare-stats`:

```text
player + bucket + retrieval time -> ACL ptsPerRnd
```

This is useful for official season/career comparison but not for reconstructing a
match-by-match time series unless historical buckets can be queried.

### 2. ACL event PPR

From `event-player-stats`:

```text
player + event + reported rounds -> ACL ptsPerRnd
```

Order events by verified event start/completion time. This creates historical event
observations without pretending to know ACL's internal inclusion logic.

### 3. Cheesebaggers calculated PPR

From accessible match-round facts:

```text
sum(player round points) / count(player rounds)
```

Calculate for:

- match;
- event;
- rolling last 10/25/50 matches;
- season/bucket;
- career;
- singles and doubles separately;
- combined only when explicitly requested.

Every calculated PPR must include:

- calculation version;
- `as_of` cutoff;
- included match/game/round manifest;
- expected versus available match/game/round counts;
- excluded/rejected record counts;
- data-completeness percentage;
- missing-data reasons, including match-stat 401/403 responses.

Never fill missing rounds from ACL aggregate PPR. Aggregates may be compared with calculated
values but are not source facts suitable for reconstructing absent rounds.

## Reconciliation model

For the same player/event or player/bucket:

| Field | Description |
|---|---|
| `acl_reported_ppr` | PPR returned by ACL |
| `cheesebaggers_calculated_ppr` | PPR calculated from retained facts |
| `absolute_delta` | Calculated minus ACL-reported |
| `relative_delta` | Delta relative to ACL value where valid |
| `acl_reported_rounds` | ACL round count where supplied |
| `cheesebaggers_rounds` | Retained/calculated round count |
| `coverage_delta` | Difference in round counts |
| `known_exclusions` | Missing/auth-blocked/rejected games and rounds |
| `reconciliation_status` | `MATCH`, `EXPLAINED_DIFFERENCE`, `POSSIBLE_DIFFERENCE`, or `UNEXPLAINED` |
| `explanation_evidence` | References to source records supporting any claimed cause |

Do not claim that a difference is caused by rounding, missing matches, corrections, format,
or ACL rules unless the available evidence establishes that claim.

## Discovery workflow

For a requested player:

1. Call `player-events-grouped` for each known bucket and both `ACTIVE` and `COMPLETED`.
2. Build an event list and retain the raw event-index responses.
3. For each event, request:
   - event metadata;
   - event player stats;
   - relevant standing/roster endpoint;
   - bracket/schedule data;
   - match stats for the player's games when publicly accessible.
4. Extract ACL CPI observations from public player rows.
5. Extract ACL event PPR from event player stats.
6. Request `player-compare-stats` for each known bucket.
7. Calculate independent PPR only from retained round facts.
8. Produce a coverage and reconciliation report.

Batch player IDs for `player-compare-stats` to reduce calls. Cache completed event payloads
and use ETags where provided.

## Data-quality and access limitations

- `match-stats` sometimes returns 401/403 without authentication, causing incomplete
  round-level history.
- Public event endpoints may return empty arrays for older or unsupported event types.
- `player-events-grouped` may not enumerate every historical event or bucket.
- CPI copied into an event response may be current-at-retrieval rather than event-time.
- PPR fields may use different scopes even when names are similar.
- Numeric identifiers and statistics may change type across endpoints.
- Strings may contain whitespace and sentinel strings such as `"NULL"`.

Coverage is a first-class output, not a background log.

## Minimal implementation sequence

1. Start scheduled public CPI observation collection so history accumulates immediately.
2. Audit and document `player-compare-stats` across bucket IDs.
3. Audit `event-player-stats` for singles, doubles, old, recent, live, and completed events.
4. Test the prior-season/bucket hypothesis across boundary dates and multiple players.
5. Continue longitudinal re-fetch tests; the initial test proved old rosters contain mixed
   cached/current snapshots rather than reliable event-time values.
6. Inventory existing saved payloads for unique `(playerID, playerCPI, cPITimeStamp)`.
7. Build append-only ACL statistic observations with provenance.
8. Build independent PPR calculation and coverage reporting.
9. Add reconciliation views.
10. Decide whether authenticated profile access provides any necessary value not safely
   available from public sources.

## Decision rule

The prediction engine may use:

- ACL CPI only from an ACL-reported observation;
- ACL aggregate PPR as an explicitly sourced model feature;
- Cheesebaggers calculated PPR as a separate feature with completeness metadata.

It must not:

- infer CPI;
- overwrite one PPR series with another;
- treat an event payload as historical CPI proof without validating its time semantics;
- hide match-stat authentication gaps;
- use data retrieved after a prediction cutoff in historical replay.
