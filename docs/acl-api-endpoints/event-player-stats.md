# ACL Event Player Statistics Endpoint Review

Endpoint:

```text
GET /api/v1/event-player-stats/{event_id}
```

Validated example:

```text
GET /api/v1/event-player-stats/247734
```

Review status: **Successful populated unauthenticated response confirmed**

## Response envelope

| Variable | Observed value | Meaning |
|---|---|---|
| `status` | `"OK"` | ACL application status |
| `message` | `"Successfully Get Event Player Stats"` | Result message |
| `data[]` | 60 rows | One aggregate statistic row per player ID |

## Event-level row schema

| Variable | Observed type | Likely meaning |
|---|---|---|
| `ranking` | integer | Rank ordered by event PPR; tied ranks share a number |
| `playerID` | integer | ACL player identifier |
| `playerFirstName`, `playerLastName` | string | Player identity; redact in review fixtures |
| `skillLevel` | string | Human-readable ACL skill label |
| `rounds` | integer | Player rounds included in this event aggregate |
| `totalPts` | integer | Player points across included rounds |
| `ptsPerRnd` | number | ACL-reported event PPR |
| `opponentPts` | integer | Opponent points across included rounds |
| `opponentPtsPerRnd` | number | ACL-reported opponent PPR |
| `diffPerRnd` | number | Player PPR minus opponent PPR, derived from totals |
| `TotalFourBaggers` | integer | Four-bagger count; note capital `T` |
| `fourBaggerPct` | number | Four-baggers divided by rounds, as a percentage |
| `bagsInPct` | number | Hole bags divided by total bags |
| `bagsOnPct` | number | Board bags divided by total bags |
| `bagsOffPct` | number | Off-board bags divided by total bags |
| `avgBagsInPerRnd` | number | Hole bags divided by rounds |
| `totalBags` | integer | Bags thrown; four per included round in every tested row |
| `bagsIn` | integer | Total hole bags |

The response does not include CPI, event ID inside each row, an `as_of` timestamp, or a
calculation version. Cheesebaggers must attach event ID, endpoint, retrieval time, payload
hash, and event metadata as provenance.

## Sanitized sample row

| Variable | Observed value |
|---|---:|
| `ranking` | `1` |
| `playerID` | `200684` |
| Player name | `[REDACTED_PLAYER_NAME]` |
| `skillLevel` | `"Advanced"` |
| `rounds` | `20` |
| `totalPts` | `203` |
| `ptsPerRnd` | `10.15` |
| `opponentPts` | `145` |
| `opponentPtsPerRnd` | `7.25` |
| `diffPerRnd` | `2.9` |
| `TotalFourBaggers` | `7` |
| `fourBaggerPct` | `35` |
| `bagsInPct` | `78.75` |
| `bagsOnPct` | `17.5` |
| `bagsOffPct` | `3.75` |
| `avgBagsInPerRnd` | `3.15` |
| `totalBags` | `80` |
| `bagsIn` | `63` |

## Full-response validation

All 60 rows were checked.

| Check | Result |
|---|---|
| Rows / unique player IDs | `60 / 60` |
| Total player-round observations | `1284` |
| Total bags | `5136` |
| `totalBags = rounds × 4` | Passed for all 60 rows |
| `ptsPerRnd = totalPts / rounds` after rounding | Passed for all 60 rows |
| `opponentPtsPerRnd = opponentPts / rounds` after rounding | Passed for all 60 rows |
| `diffPerRnd = (totalPts - opponentPts) / rounds` after rounding | Passed for all 60 rows |
| `bagsInPct = bagsIn / totalBags × 100` after rounding | Passed for all 60 rows |
| `avgBagsInPerRnd = bagsIn / rounds` after rounding | Passed for all 60 rows |
| Bag-placement percentages sum to 100% within rounding tolerance | Passed for all 60 rows |
| `fourBaggerPct = TotalFourBaggers / rounds × 100` after rounding | Passed for all 60 rows |
| Sorted descending by `ptsPerRnd` | Passed |

This endpoint's reported statistics are internally consistent for the supplied event.

## Ranking behavior

Ties use competition ranking:

| Shared rank | Next missing rank |
|---:|---:|
| `17` | `18` |
| `21` | `22` |
| `38` | `39` |

Rows are sorted by descending PPR. Equal PPR values share the same rank and the following
rank is skipped. Tie ordering within a rank is not proven to have a stable secondary key.

## Synthetic Ghost participants

Two synthetic-looking records received full statistics:

| Player ID | Source label | Rank | Rounds | PPR |
|---:|---|---:|---:|---:|
| `29683` | `"Ghost One"` | `23` | `27` | `7.81` |
| `29684` | `"Ghost Two"` | `47` | `25` | `5.96` |

These may represent anonymous/substitute placeholders rather than actual ACL player
profiles. They must be classified explicitly and not silently merged with ordinary players.
Their round facts should not be discarded automatically, because they contributed to real
event scoring; instead, retain the participant classification and exclude/include them
according to the metric's documented purpose.

## Derived formulas supported by evidence

For this response, the following formulas reproduce ACL's displayed values:

```text
PPR = totalPts / rounds
Opponent PPR = opponentPts / rounds
DPR = (totalPts - opponentPts) / rounds
Four-bagger percentage = TotalFourBaggers / rounds × 100
Hole-bag percentage = bagsIn / totalBags × 100
Average hole bags per round = bagsIn / rounds
Total bags = rounds × 4
```

This validates arithmetic, not inclusion rules. We still do not know which matches, games,
forfeits, live rounds, corrections, or synthetic-player rounds ACL includes.

## Strategy implications

- Use this endpoint as the primary unauthenticated ACL-reported event PPR source.
- Store the entire aggregate row as an ACL observation with event and retrieval provenance.
- Use `rounds` and `totalPts` to reconcile independent round-level calculations.
- Do not treat the response as immutable; re-fetching may reflect corrections.
- Do not derive historical pre-event features from an event's final aggregate.
- For backtesting, this event aggregate becomes eligible only after the event/matches
  contributing to it were known.
- Preserve ACL aggregate PPR separately from Cheesebaggers-calculated PPR.
- Do not use event rankings as a player strength feature without accounting for event
  completion and sample size.

## Visible redaction summary

| JSON path | Marker | Reason |
|---|---|---|
| `data[].playerFirstName`, `data[].playerLastName` | `[REDACTED_PLAYER_NAME]` | Player identity unnecessary for statistical contract review |

Player IDs are retained because they are needed to reconcile event, bracket, match, and
round records.

## Required follow-up tests

1. Singles event.
2. Completed doubles bracket rather than swap/pool event.
3. Active/incomplete event and transition to completed.
4. Event containing forfeits or byes.
5. Event with multiple games per match.
6. Re-fetch the same event later to detect corrections/mutability.
7. Sum accessible match-stat rows and compare player-by-player with this endpoint.
8. Determine inclusion rules for synthetic Ghost participants.
9. Determine whether missing/inaccessible match stats still contribute to this aggregate.
