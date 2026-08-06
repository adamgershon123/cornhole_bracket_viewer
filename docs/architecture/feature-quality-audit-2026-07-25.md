# Stage A Feature-Quality Audit

Audit date: 2026-07-25  
Cutoff: `2026-07-25T23:59:59-04:00`  
Window: prior 365 days  
Players audited: all 505 players with normalized round history

## Readiness decision

The data is suitable for building and evaluating a conservative baseline model. It is not
yet suitable for claiming broad high-evidence prediction coverage.

- No impossible feature values were detected.
- 59 players meet provisional Tier B history thresholds.
- 446 players are Tier C because their samples are sparse.
- No players qualify for Tier A because cutoff-eligible ACL snapshots have not yet been
  populated in the new observation table and expected-game coverage is frequently unknown.

Evidence tiers describe input quality, not prediction confidence or player skill.

## History distribution

| Measure | Minimum | Median | Mean | Maximum |
|---|---:|---:|---:|---:|
| Rounds per player | 2 | 12 | 57.04 | 4,472 |
| Games per player | 1 | 2 | 8.07 | 627 |
| Events per player | 1 | 1 | 4.74 | 186 |
| Calculated PPR | 0.6667 | 7.5 | 7.3712 | 11.3333 |
| Calculated DPR | -7.2 | -0.2051 | -0.2852 | 7.6667 |

The long-tailed sample distribution is the main modeling limitation. Most players have only
one event and two games, while a small number have extensive history. Baseline training and
evaluation must therefore use minimum-sample rules and shrink sparse estimates toward a
population/format prior.

## Provisional evidence tiers

| Tier | Players | Interpretation |
|---|---:|---|
| A | 0 | Strong history, trustworthy coverage, and eligible ACL CPI/PPR snapshots |
| B | 59 | At least 100 rounds and 10 games; ACL snapshots/complete coverage not required |
| C | 446 | Some history, but below the Tier B volume threshold |
| No prediction | 0 | No historical game/round facts among the audited population |

These counts cover players already present in `player_rounds`; a newly encountered player
with no history would be `NO_PREDICTION` or a separately defined cold-start case.

## Coverage findings

| Finding | Players |
|---|---:|
| Expected-game coverage known | 249 |
| Coverage unknown | 256 |
| Indexed expected games fewer than retrieved games | 239 |

Among the 249 players whose expected index passed integrity checks:

- median coverage ratio was `1.0`;
- mean coverage ratio was `0.9738`; and
- minimum coverage ratio was `0.25`.

Coverage remains unknown for more than half the population. The feature builder correctly
withholds ratios when legacy expected-game indexing does not contain all retrieved games.

The audit found zero latest-attempt 401/403 games in the new attempt table. This does **not**
prove that no historical games were blocked: attempt-level provenance was implemented after
much of the existing cache was created, so historical failures were not backfilled.

## ACL snapshot findings

The new statistic-observation table contained no cutoff-eligible CPI or PPR observations for
the audited players. This is an initialization/backfill state, not evidence that public ACL
snapshots are unavailable. Existing raw/cache data predates automatic extraction.

Consequences:

- Stage A must remain independent of CPI.
- Do not mark snapshot fields unavailable permanently.
- Re-fetch or perform a controlled extraction from existing immutable cache files with their
  original retrieval metadata where trustworthy.
- Never assign today's retrieval time to a historical observation and then use it before
  today.

## Format and partnership coverage

Normalized round counts by raw match/bracket code:

| Raw format | Rounds |
|---|---:|
| `D:D` | 23,686 |
| `S:D` | 3,618 |
| `D:S` | 1,302 |
| `T:T` | 134 |
| `S:S` | 64 |

The codes must remain raw features until their meanings and cross-endpoint consistency are
fully mapped. They should not be replaced with guessed labels.

Partnership history was identifiable for:

- 1,891 shared-team games;
- 906 unique player combinations; and
- 470 of the 505 audited players.

## Anomaly checks

No players failed the implemented bounds:

- PPR between 0 and 12;
- opponent PPR between 0 and 12;
- DPR between -12 and 12;
- rates between 0 and 1;
- bag placement rates summing to one; and
- known coverage ratios between 0 and 1.

Passing these checks establishes arithmetic plausibility, not complete source coverage.

## Timezone defect found and fixed

The initial audit converted the Eastern cutoff to UTC before deriving the event-date cutoff,
which advanced `2026-07-25 23:59:59 -04:00` to the UTC date `2026-07-26`. The builder now:

- preserves the calendar date from the supplied cutoff timezone for date-grain event facts;
  and
- retains the normalized UTC timestamp for timestamped ACL observation eligibility.

A regression test confirms that a July 25 event remains excluded from a late-evening July 25
cutoff.

## Baseline-build constraints

Proceed with baseline construction under these conditions:

1. Train/evaluate only on matches whose participants and prior history are reconstructable.
2. Preserve Tier B and Tier C results separately.
3. Apply shrinkage and missingness indicators for sparse Tier C players.
4. Do not use CPI or profile PPR as required inputs.
5. Do not present unknown coverage as complete.
6. Use chronological splits and exclude the entire prediction date until precise match
   timestamps are validated.
7. Compare against equal-probability and simple rating/PPR-difference baselines before
   introducing a learned model.

The initial equal-probability and calculated-PPR benchmarks are implemented in
[`baseline-prediction-implementation.md`](./baseline-prediction-implementation.md).
