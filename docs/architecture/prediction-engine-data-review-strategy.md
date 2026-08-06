# ACL Data Review: Prediction-Engine Strategy

Status: consolidated decision record as of 2026-07-25  
Assumption: the reviewed endpoints represent all ACL data available to the platform

## Executive conclusion

ACL supplies enough public data to build a useful, auditable match prediction engine, but
not enough to reconstruct a complete, leakage-free history of every ACL rating or match.

The engine must be designed around three facts:

1. Match and inning facts support independent performance calculations, but some match-stat
   records return 401/403 and are unavailable.
2. CPI/PPR fields embedded in old event responses are often later profile snapshots, not
   values that existed at the event.
3. Event formats expose different historical detail. Swiss/Rounders has a strong completed
   schedule; Swap and bracket data have different structures and gaps.

The correct design is a cutoff-aware, coverage-aware engine that preserves ACL statistics
alongside separately calculated statistics. It must not fill gaps with invented facts or
silently use future snapshots.

## Source capability summary

| Need | Best source | Limitation |
|---|---|---|
| Event identity, date, format, bucket | `events/{event_id}` | Alias fields and inconsistent sentinels require normalization. |
| Bracket matches and participants | `bracket-data/{event_id}` | Duplicate/synthetic participants and timestamp defects require filtering. |
| Game and inning performance | `match-stats/...` | Some games return 401/403; coverage is incomplete. |
| ACL event player aggregates | `event-player-stats/{event_id}` | Event outcome, not a pre-match feature. |
| ACL season/bucket PPR | `player-compare-stats` | Exact inclusion rules and bucket scope are undisclosed. |
| Current/observed ACL CPI | Public event player rows | Snapshot may postdate the event; zero/null requires missingness handling. |
| Historical event-time CPI | No reliable source | Unavailable before prospective collection. |
| Swap final standings/partners | `swap-standings` | Does not guarantee complete scored-match chronology. |
| Swiss chronology | `swiss-pairing-schedule-breakdown` | Overall and completed lists duplicate matches. |
| Swiss official standings | `swiss-pairing-standings` | ACL tiebreak formula is unknown. |
| Live/up-next state | Format-specific schedule/up-next endpoints | Populated schemas still require active-event captures. |
| Authenticated profile | `/api/auth/v1/players/...` | Unusable dependency; requires session and exposes excessive sensitive data. |

## Findings that change modeling

### Historical CPI is not reconstructable

An old event response is not proof of the CPI available before that event. CPI timestamps
frequently postdate the event.

- Never calculate or infer official CPI.
- Exclude CPI whose ACL timestamp is after the prediction cutoff.
- Treat a missing timestamp as retrieval-time-only.
- Treat zero CPI as unavailable/unvalidated unless ACL confirms otherwise.
- Begin append-only prospective CPI collection.
- Do not use CPI in retrospective backtests before trustworthy observations exist.

### ACL PPR and calculated PPR are distinct observations

ACL season, event, and game PPR can coexist with PPR calculated from accessible match
history. Values may differ because ACL rules are undisclosed and local match coverage is
incomplete.

- Store and display both separately.
- Include source, scope, cutoff, round count, and retrieval/calculation time.
- Quantify differences without claiming an unproven cause.
- Never overwrite or impersonate the ACL value.

### Match facts are strong but selectively missing

The reviewed match aggregates reconciled exactly to inning facts, making match-stats the
strongest calculated-feature source. Some records are skipped after 401/403 responses.

- Carry retrieved/expected/blocked/failed game counts with every rolling statistic.
- Never convert missing games into zero-performance games.
- Train only on examples meeting an explicit minimum-coverage policy.
- Expose coverage as both a model feature and a confidence warning.

### Formats require separate adapters

- Swiss/Rounders uses fixed teams and provides complete round/match chronology.
- Swap rotates partners and provides player standings/partner history, but the completed
  schedule capture did not provide scored historical chronology.
- Bracket data provides match structure but includes synthetic Bye/Ghost participants,
  duplicates, and timestamp anomalies.

Use one canonical match/side/participant model with format-specific adapters. Represent
fixed teams separately from temporary Swap partnerships, never concatenate duplicate Swiss
schedule arrays, and report model performance separately by format.

### Final statistics are outcomes, not pre-match features

Final rank, wins, differential, event PPR, and completed-event standings leak information
produced by the event.

- Use them for labels, validation, and post-event audit.
- Build features only from matches strictly before the cutoff.
- For round events, use data through the prior completed round, not other results from the
  round being predicted.

## Required strategy changes

### 1. Define the prediction moment

Every prediction must retain `prediction_created_at`, `data_cutoff_at`, event/match/round,
known participants, source payloads, feature version, and model version. No observation
effective or retrieved after the cutoff is eligible.

### 2. Roll out models in two stages

Stage A should be an interpretable logistic or rating baseline that does not require CPI:

- rolling calculated PPR and differential;
- bag placement and four-bagger rates;
- opponent-adjusted performance;
- sample size, coverage, and recency;
- format and singles/doubles indicators;
- eligible team/partnership history; and
- missingness indicators.

Stage B may add latest eligible ACL CPI/PPR, snapshot age, ACL-versus-calculated PPR delta,
and staleness indicators only after prospective history exists. Adopt it only if
chronological evaluation improves calibration and predictive performance.

### 3. Attach evidence-quality tiers

| Tier | Evidence | Behavior |
|---|---|---|
| `A` | Strong match coverage and timely ACL snapshots | Full model and normal confidence display. |
| `B` | Adequate match history but ACL snapshots missing/stale | Match-history model with disclosure. |
| `C` | Sparse history or material endpoint failures | Shrunk/cold-start prediction with prominent warning. |
| `NO_PREDICTION` | Participants unknown or temporal/integrity checks fail | Abstain rather than invent a probability. |

The tier describes evidence quality, not probability.

### 4. Make missingness first-class

Each feature window needs games expected/retrieved/blocked/failed, rounds included, date
range, formats, observation age, source classification, and minimum-coverage result. Null
means unknown and must never silently become zero.

### 5. Separate official and calculated records

Use distinct types such as `ACL_REPORTED_CPI`, `ACL_REPORTED_SEASON_PPR`,
`ACL_REPORTED_EVENT_PPR`, `ACL_REPORTED_GAME_PPR`, `CHEESEBAGGERS_CALCULATED_PPR`,
`ACL_REPORTED_RANK`, and `CHEESEBAGGERS_CALCULATED_RANK`. Store endpoint, scope, effective
time, retrieval time, calculation version, and raw-payload provenance.

### 6. Collect prospectively

Capture public snapshots before production predictions, at event ingestion, before new
rounds where practical, at completion, daily for tracked players, and at bucket/season
transitions. Deduplicate identical observations but retain changes append-only.

### 7. Evaluate chronologically and by format

Backtests must split by time, calculate every feature at the historical cutoff, exclude
later snapshots, group same-round matches against within-round leakage, and report log loss,
Brier score, calibration, accuracy, coverage, format, and evidence tier. Compare against
equal-probability, PPR-difference, and Elo-style baselines.

## Minimum viable engine

The first defensible engine predicts which known side wins using accessible pre-match facts.
It outputs probabilities summing to one, the cutoff, evidence tier, feature contributions,
coverage summary, and immutable model/feature versions. It abstains when participants or
temporal integrity cannot be established.

## Prohibited claims

- Do not claim reconstructed event-time CPI where none was observed.
- Do not calculate or infer “official CPI.”
- Do not assert a certain cause for ACL/internal PPR differences without evidence.
- Do not imply complete history when match-stat requests were blocked.
- Do not use final standings, event aggregates, or later snapshots as pre-match features.
- Do not compare formats without disclosing materially different coverage.

## Immediate priorities

1. Implement immutable raw-payload ingestion with source, effective, and retrieval times.
   **Foundation implemented:** see
   [`provenance-foundation-implementation.md`](./provenance-foundation-implementation.md).
2. Normalize events, matches, sides, teams/partnerships, participants, and rounds with
   format-specific adapters.
3. Add ingestion coverage and reconciliation reports.
4. Implement cutoff-aware rolling player and partnership features.
   **Implemented:** see
   [`stage-a-feature-builder-implementation.md`](./stage-a-feature-builder-implementation.md).
5. Build the Stage A interpretable baseline without CPI dependency.
   **Feature audit passed with constraints:** see
   [`feature-quality-audit-2026-07-25.md`](./feature-quality-audit-2026-07-25.md).
   **Initial benchmarks implemented:** see
   [`baseline-prediction-implementation.md`](./baseline-prediction-implementation.md).
6. Start scheduled prospective ACL CPI/PPR collection.
7. Run chronological, format-stratified backtests.
   **Initial evaluation complete:** see
   [`chronological-evaluation-2026-07-25.md`](./chronological-evaluation-2026-07-25.md).
8. Add Stage B snapshot features only after sufficient eligible history accumulates.

The first untouched chronological holdout selected a one-parameter fitted-PPR candidate for
rolling-origin validation. See
[`holdout-evaluation-2026-07-25.md`](./holdout-evaluation-2026-07-25.md).

The ACL statistic observation prerequisite for cutoff-aware features is implemented in
[`statistic-observation-implementation.md`](./statistic-observation-implementation.md).
