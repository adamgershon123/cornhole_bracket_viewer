# ACL Swap Standings Endpoint Review

Endpoint:

```text
GET /api/v1/swap-standings/{event_id}
```

Validated example:

```text
GET /api/v1/swap-standings/254035
```

Review status: **Successful populated unauthenticated response confirmed**

## Response envelope

| Variable | Observed value | Meaning |
|---|---|---|
| `status` | `"OK"` | ACL application status |
| `message` | `"Successfull Swap Player Standings"` | Result message |
| `data[]` | 64 rows | One individual swap-standing row per player |
| `cachedData` | `false` | ACL cache indicator |

## Row grain and standings behavior

This endpoint ranks individual players in a swap event. It does not return persistent
doubles teams.

| Validation | Result |
|---|---|
| Rows / unique player IDs | `64 / 64` |
| Rank range | `1–64` |
| Ranks unique and sequential | Yes |
| Matches per player (`wins + losses`) | Exactly 4 for all players |
| Observed records | `4-0`, `3-1`, `2-2`, `1-3`, `0-4` |
| Partner IDs per player | Exactly 4 for all players |
| Partner IDs missing from standings | None |
| Nonreciprocal partner links | None |
| Ordering | Descending wins, then descending point differential |

This supports treating each standing row as an individual event result and each
`partnerHistory` entry as a player-to-player partnership observation. The order of partner
IDs may correspond to match order, but that has not yet been proven.

## Registration and status fields

| Variable | Likely meaning | Observed behavior |
|---|---|---|
| `leagueID` | Event identifier | `254035` on all rows |
| `playerID`, `fldPlayerID` | Player ID aliases | Equal on all rows |
| `playerStatus` | Player/account status code | `"A"` in supplied rows |
| `playerCheckedIn` | Check-in flag | 37 `"Y"`, 27 `"N"` |
| `paidStatus` | Payment flag/status | Requires code review |
| `playerOptOut` | Opt-out flag | Requires code review |
| `dateTimeStamp` | Registration/event-row timestamp | 2026-07-24 values; timezone absent |
| `holdMySpotPaymentMethod`, `holdMySpotPaymentAmount` | Registration payment metadata | Sensitive/unneeded for analytics |
| `playerGroup` | Swap pool/group | `"B"` in supplied rows |

All 27 players marked not checked in still have four match results. Therefore
`playerCheckedIn` must not be used as evidence that a player did or did not participate.
It may be stale, reset, or have another ACL-specific meaning.

## Player profile snapshot fields

| Variable | Likely meaning |
|---|---|
| `playerSkillLevel` | ACL skill-level code |
| `playerPPRPlayerInfo` | Higher-precision PPR-like snapshot; definition unknown |
| `playerPPR` | ACL-reported PPR snapshot, not event PPR |
| `playerCPI` | ACL-reported CPI snapshot |
| `cPITimeStamp` | CPI update/effective timestamp |
| `conferenceID`, `conferenceName` | Conference information |
| `playerMembershipType`, `playerMembershipName` | Membership code/label |

The event occurred on 2026-07-24. Most CPI timestamps are 2026-07-22, so these snapshots
were available before the event and can be eligible for a prediction cutoff after their
timestamp.

Player `142125` returned:

| Field | Value |
|---|---:|
| `playerPPRPlayerInfo` | `7.4153` |
| `playerPPR` | `7.39` |
| `playerCPI` | `6.35` |
| `cPITimeStamp` | `"2026-07-22 13:29:30"` |

These match the supplied authenticated profile snapshot, confirming this public endpoint
can provide current CPI/PPR without profile authentication for players participating in the
event.

## Missing-stat representation

Three rows returned:

```text
playerPPRPlayerInfo: 0
playerPPR: 0
playerCPI: 0
cPITimeStamp: null
```

These appear to be new/no-profile-stat players. Normalize this combination as
`ACL_STAT_UNAVAILABLE` pending ACL confirmation, while preserving the raw zeroes.

Do not:

- treat zero CPI as a real official rating;
- rank these players as proven zero-strength;
- silently impute another player's or current average value;
- calculate or infer CPI.

## Swap result fields

| Variable | Likely meaning | Validated behavior |
|---|---|---|
| `partnerHistory[]` | Four partner player IDs | Four reciprocal links for every player |
| `wins`, `losses` | Player match record | Sum to four for every player |
| `playerDifferentialPoints` | Points scored minus opponent points | Ranking secondary key |
| `playerTotalPoints` | Player/side points credited across matches | Exact scoring grain needs review |
| `isNegativeDiff` | Whether differential is negative | Matched `playerDifferentialPoints < 0` for all rows |
| `rank` | Individual swap rank | Unique 1–64, sorted by wins then differential |

Potential opponent points can be arithmetically expressed as:

```text
playerTotalPoints - playerDifferentialPoints
```

But confirm the meaning against match records before storing it as an ACL-defined opponent
total.

## Partnership implications

The complete reciprocal four-partner graph is valuable for:

- reconstructing who partnered with whom in each swap event;
- accumulating partnership sample counts;
- studying partner lift/drag after joining to match-level performance;
- validating normalized match participants.

However, the array alone does not prove:

- which partner belongs to which match;
- chronological partner order;
- match outcome with each partner;
- throw order or side;
- whether repeated partners are possible.

Join partner pairs to schedule/bracket/match results before assigning match context.

## Privacy findings

Every one of the 64 rows returned both:

- `playerEmail`;
- `playerPhoneNo`.

The endpoint also returns name, photo, city, state, membership, and payment-related
registration fields. Contact/payment data is unnecessary for prediction analytics and
should be excluded from normalized data and visibly redacted in fixtures.

Because the endpoint is unauthenticated, its exposure of complete player contact data
should be documented as a privacy/security review item. Cheesebaggers should not amplify or
redistribute those values.

## Strategy implications

- This is the strongest current unauthenticated source for pre-event CPI/PPR snapshots of
  players registered in a swap event.
- It cannot provide CPI for players who are not in the event.
- It does not provide historical CPI merely because the event is old; timestamp rules still
  control eligibility.
- Use it for swap ranks, records, point differential, total points, and partner IDs.
- Use `event-player-stats`, not `playerPPR`, for event performance PPR.
- Attach event ID, CPI timestamp, retrieval time, endpoint, and payload hash to every
  profile-stat observation.
- Treat zero statistics with null CPI timestamp as unavailable.
- Do not use check-in status as participation evidence.

## Visible redaction summary

| JSON path | Marker | Reason/count |
|---|---|---|
| `data[].playerFirstName`, `data[].playerLastName` | `[REDACTED_PLAYER_NAME]` | 64 player identities |
| `data[].playerEmail` | `[REDACTED_EMAIL]` | 64 email values |
| `data[].playerPhoneNo` | `[REDACTED_PHONE]` | 64 phone values |
| `data[].playerPhoto` | `[REDACTED_PROFILE_IMAGE]` | Player-specific image URLs where populated |
| `data[].playerCity` | `[REDACTED_PERSONAL_DATA: city]` | Personal location |
| Hold-my-spot payment fields | `[REDACTED_PERSONAL_DATA: payment metadata]` | Registration/payment metadata |

Player IDs and partner IDs remain visible for relational validation.

## Required follow-up tests

1. Active/in-progress swap event.
2. Re-fetch this completed event to test mutability.
3. Join every partner pair to schedule/match results and determine array ordering.
4. Confirm ranking tie-breakers when wins and differential are equal.
5. Confirm the meaning of `playerTotalPoints`.
6. Confirm formal meaning of zero CPI/PPR with null timestamp.
7. Compare the same player's CPI/PPR across swap standings, schedule roster, and profile at
   one capture time.
8. Determine whether contact fields can be excluded at source or must be discarded during
   normalization.
