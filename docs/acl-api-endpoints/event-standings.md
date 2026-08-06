# ACL Event Standings Endpoint Review

Endpoint:

```text
GET /api/v1/event-standings/{event_id}
```

Validated example:

```text
GET /api/v1/event-standings/216491
```

Review status: **Successful populated unauthenticated response confirmed**

## Response envelope

| Variable | Observed value | Meaning |
|---|---|---|
| `status` | `"OK"` | ACL application status |
| `message` | `"Successfully GET Event Standings"` | Result message |
| `eventName` | Public event name | Event display name |
| `data[]` | 28 rows | One row per player/team membership |
| `cachedData` | `false` | ACL cache indicator |

## Row grain and team structure

This is a player row carrying team-level standing results, not one row per team.

| Measure | Result |
|---|---:|
| Rows | 28 |
| Unique players | 28 |
| Unique teams | 14 |
| Players per represented team | 2 |
| Bracket event team count | 16 |
| Teams absent from standings | 2 synthetic bye-only teams from bracket data |

To normalize doubles standings, group rows by `(event ID, fldTeamID)`. Preserve each player
membership, but store rank, points, wins, and losses once at team-result grain.

## Event and player identity fields

| Variable | Likely meaning |
|---|---|
| `fldLeagueYear` | Event/league year |
| `fldLeagueSessionID` | Session identifier |
| `fldLeagueID` | Event identifier |
| `fldWeekID` | Week/session grouping |
| `fldLeagueName` | Event name |
| `fldPlayerID`, `playerID` | Player ID aliases; equal for all 28 rows |
| `fldPlayerFirstName`, `fldPlayerLastname` | Player identity |
| `playerPhoto` | Player image URL or null |
| `playerCity`, `playerState` | Player location |
| `playerSkillLevel` | Skill code |
| `conferenceID`, `conferenceName` | Conference information |

Player name, photo, and city values are redacted in review fixtures.

## Team standing fields

| Variable | Observed behavior | Likely meaning |
|---|---|---|
| `fldTeamID`, `fldTeamName` | Repeated on both partner rows | Team identifier/name |
| `fldEventRank` | Team rank repeated for partners | Finishing rank with competition-ranking ties |
| `fldEventPos` | Sequential `1` through `28` | Player-row display position, not team finishing position |
| `fldEventWeekPoints` | Same for partners | Points awarded for event/week |
| `fldEventTotalPoints` | Equal to week points on every row | Total event points in this response |
| `wins`, `losses` | Populated; ranges `0–5` and `0–2` | Team match record |

## Ranking behavior

Unique team ranks were:

```text
1, 2, 3, 4, 5, 7, 9, 13
```

The jumps are consistent with competition ranking:

- two teams tied at rank 5, so rank 6 is skipped;
- two teams tied at rank 7, so rank 8 is skipped;
- four teams tied at rank 9, so ranks 10–12 are skipped;
- two teams tied at rank 13.

`fldEventPos` remains a unique player-row sequence and must not be used as team rank.

## Conflicting legacy result fields

Every row returned zero for:

- `fldTotalMatchesWon`;
- `fldTotalMatchesLost`;
- `fldPointDifferential`;
- `fldPointsScored`.

At the same time, `wins` and `losses` were populated and consistent between partners.

Therefore:

- use `wins` and `losses` as the observed populated result fields for this endpoint;
- retain the zero-valued `fld*` fields as source observations;
- do not interpret those zeroes as real match or scoring totals;
- verify other event formats before declaring the `fld*` fields universally deprecated.

## ACL PPR and CPI fields

| Variable | Likely meaning |
|---|---|
| `playerPPRPlayerInfo` | Higher-precision PPR-like snapshot; definition/window unknown |
| `playerPPR` | ACL-reported PPR snapshot; not event PPR |
| `playerCPI` | ACL-reported CPI snapshot |
| `cPITimeStamp` | CPI effective/update timestamp |

These are player-stat snapshots attached to standings rows, not statistics calculated from
this event. Evidence:

- the event occurred on 2025-09-01;
- 26 of 28 rows have CPI timestamps on 2025-10-02;
- those values therefore did not exist at the event cutoff;
- player `142125` returned CPI `6.24`, timestamp `2025-10-02 05:28:11`, and PPR `7.36`,
  matching the older public-event observation found in the CPI-history test.

This confirms the older `6.24` CPI was carried by the event-standings snapshot. It does not
prove whether it represents a prior-season value, an October cache refresh, or another ACL
process.

## Zero versus missing CPI/PPR

Two rows returned:

```text
playerCPI: 0
cPITimeStamp: null
```

One was a synthetic Ghost player. The other was an ordinary player row and also returned
`playerPPR: 0` while `playerPPRPlayerInfo` was nonzero.

Treat `playerCPI: 0` with a null CPI timestamp as **missing/unknown pending ACL confirmation**,
not automatically as an official zero rating. Preserve the raw zero and expose a
normalization-quality flag such as `ZERO_WITHOUT_SOURCE_TIMESTAMP`.

## Synthetic participant handling

The standings include Ghost player ID `29683` with:

- a normal team membership;
- rank, event points, wins, and losses;
- nonzero PPR-like fields;
- CPI zero and no CPI timestamp.

The synthetic bye-only teams found in bracket data are omitted entirely. This supports
separate classifications for scoring Ghost participants versus noncompeting Bye
placeholders.

## Strategy implications

- This endpoint is useful for final team standings, placements, points, partnerships, and
  public player-stat snapshots.
- It is not a source of event PPR; use `event-player-stats` for event PPR.
- It is not a reliable source of CPI as of the event date.
- For current data, CPI is eligible only according to `cPITimeStamp`/retrieval cutoff.
- For historical replay, exclude all 26 post-event CPI observations from predictions at
  this event.
- Group doubles rows by team before counting placements or records.
- Do not use `fldEventPos` as rank.
- Do not use zeroed legacy match/point fields when populated alternatives exist.

## Visible redaction summary

| JSON path | Marker | Reason |
|---|---|---|
| Player first/last names | `[REDACTED_PLAYER_NAME]` | Identity unnecessary for structural/statistical review |
| `playerPhoto` | `[REDACTED_PROFILE_IMAGE]` | Player-specific image URL |
| `playerCity` | `[REDACTED_PERSONAL_DATA: city]` | Personal location unnecessary for standings review |

Player and team IDs remain visible for cross-endpoint reconciliation.

## Required follow-up tests

1. Singles standings to confirm row grain.
2. Swap and Swiss standings response differences.
3. Active/incomplete event standings.
4. Events where `fldTotalMatchesWon/Lost` are nonzero.
5. Prior/current bucket boundary behavior across multiple players.
6. Re-fetch this event later to detect CPI/PPR snapshot mutation.
7. Compare standings wins/losses and placement with normalized bracket results.
8. Determine the official distinction between `fldEventRank` and `fldEventPos`.
9. Determine whether CPI zero with null timestamp formally means unavailable.
