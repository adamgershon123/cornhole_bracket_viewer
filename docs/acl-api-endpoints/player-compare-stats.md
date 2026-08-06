# ACL Player Compare Statistics Endpoint Review

Endpoint:

```text
POST /api/v1/player-compare-stats
```

Validated request:

```json
{
  "playerIDs": [142125],
  "bucketID": 11
}
```

Review status: **Successful populated unauthenticated response confirmed**

## Response envelope

| Variable | Observed value | Meaning |
|---|---|---|
| `status` | `"OK"` | ACL application status |
| `message` | `"Successfull - Player Compare Career"` | ACL labels this response “Career” |
| `data[]` | One row | One aggregate row per requested player in this sample |

The message says “Career,” while the row is also scoped by `bucketID: 11` and
`yearDesc: "2025 - 2026"`. Until ACL confirms the behavior, describe this as an
**ACL-reported player aggregate for the requested bucket**, not definitively career or
season.

## Identity and scope

| Variable | Sanitized sample | Likely meaning |
|---|---|---|
| `playerID` | `142125` | ACL player identifier |
| `playerFirstName`, `playerLastName` | `[REDACTED_PLAYER_NAME]` | Player name |
| `playerPhoto` | `[REDACTED_PROFILE_IMAGE]` | Player image URL |
| `playerSkillLevel` | `"C"` | ACL skill-level code |
| `bucketID` | `11` | Requested ACL statistics bucket |
| `yearDesc` | `"2025 - 2026"` | Human-readable bucket/season description |

## Performance statistics

| Variable | Observed value | Observed type | Likely meaning |
|---|---:|---|---|
| `ptsPerRnd` | `7.39` | number | ACL-reported points per round |
| `DPR` | `0.05` | number | ACL-reported differential per round |
| `OppPtsPerRnd` | `7.34` | number | ACL-reported opponent points per round |
| `totPtsTotal` | `40110` | integer | Total player points in aggregate |
| `oppPtsTotal` | `39821` | integer | Total opponent points in aggregate |
| `rdsTotal` | `5425` | integer | Total rounds in aggregate |

## Bag statistics

| Variable | Observed value | Observed type | Likely meaning |
|---|---:|---|---|
| `bagsTotal` | `21700` | integer | Total bags |
| `bagsInTotal` | `10596` | integer | Hole bags |
| `bagsInPct` | `"48.83"` | string | Hole-bag percentage encoded as text |
| `bagsOnTotal` | `8322` | integer | Board bags |
| `bagsOnPct` | `"38.35"` | string | Board-bag percentage encoded as text |
| `bagsOffTotal` | `2782` | integer | Off-board bags |
| `bagsOffPct` | `"12.82"` | string | Off-board percentage encoded as text |
| `fourBaggersTotal` | `403` | integer | Four-bagger count |
| `fourBagPct` | `"7.43"` | string | Four-bagger percentage encoded as text |

## Round-result statistics

| Variable | Observed value | Observed type | Likely meaning |
|---|---:|---|---|
| `rdsWonTotal` | `2295` | integer | Rounds classified as won |
| `roundsWonPct` | `"42.30"` | string | Round-win percentage encoded as text |
| `rdsLostTotal` | `2312` | integer | Rounds classified as lost |
| `roundsLostPct` | `"42.62"` | string | Round-loss percentage encoded as text |
| `rdsTiedTotal` | `0` | integer | ACL reports zero tied rounds |
| `roundsTiedPct` | `"0"` | string | ACL reports zero tied-round percentage |

## Arithmetic validation

| Check | Calculation | Result |
|---|---|---|
| Four bags per round | `5425 × 4` | `21700`, exactly matches `bagsTotal` |
| Bag categories reconcile | `10596 + 8322 + 2782` | `21700`, exactly matches `bagsTotal` |
| Bag percentages reconcile | `48.83 + 38.35 + 12.82` | `100.00%` |
| PPR from totals | `40110 / 5425` | `7.3935…`, rounds to reported `7.39` |
| Opponent PPR from totals | `39821 / 5425` | `7.3403…`, rounds to reported `7.34` |
| DPR from totals | `(40110 - 39821) / 5425` | `0.05327…`, rounds to reported `0.05` |
| Four-bagger rate | `403 / 5425 × 100` | `7.428…%`, rounds to reported `7.43` |
| Won/lost/tied classified rounds | `2295 + 2312 + 0` | `4607`, which is 818 fewer than `rdsTotal` |
| Unclassified share | `818 / 5425 × 100` | `15.08%` |
| Reported won/lost/tied percentages | `42.30 + 42.62 + 0` | `84.92%`, leaving `15.08%` |

The 818-round/15.08% gap is internally consistent but unexplained. It may represent washes,
pushes, unclassified rounds, or another ACL rule, but `rdsTiedTotal` remains zero. Do not
assign a cause until ACL behavior or match-level reconciliation proves it.

## Cross-endpoint comparison

The authenticated player-profile response supplied for the same player returned:

| Field | Player profile | Player compare |
|---|---:|---:|
| PPR | `7.39` | `7.39` |
| Skill code | `"C"` | `"C"` |
| CPI | `6.35` | Not returned |
| Higher-precision `playerPPRPlayerInfo` | `7.4153` | Not returned |

This confirms `player-compare-stats` can provide the displayed PPR without authenticated
profile access. It does not provide CPI.

## Strategy implications

- Use this endpoint as the primary unauthenticated ACL-reported bucket aggregate.
- Store request `bucketID`, returned `bucketID`, `yearDesc`, retrieval time, and raw payload.
- Preserve numeric strings as returned and normalize them separately.
- Do not call the result season-only or career-only until bucket behavior is tested.
- Do not use aggregate totals to fabricate missing match/round facts.
- Compare its round total with the sum of event/match data to measure coverage.
- Retain ACL PPR separately from Cheesebaggers-calculated PPR.

## Visible redaction summary

| JSON path | Marker | Reason |
|---|---|---|
| `data[].playerFirstName`, `data[].playerLastName` | `[REDACTED_PLAYER_NAME]` | Identity unnecessary for statistical contract review |
| `data[].playerPhoto` | `[REDACTED_PROFILE_IMAGE]` | Player-specific image URL unnecessary for statistical review |

## Required follow-up tests

1. Request multiple player IDs in one call.
2. Test known prior and current bucket IDs for the same player.
3. Test a player with no rounds and a player with very small history.
4. Test singles-only, doubles-only, and mixed-history players.
5. Determine whether bucket results combine singles and doubles.
6. Explain the won/lost/tied classification gap by reconciling match rounds.
7. Determine whether active-event results appear immediately or only after completion.
8. Repeat requests over time to see whether the aggregate is mutable within a bucket.
