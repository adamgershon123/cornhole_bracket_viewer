# `GET /api/v1/swap-schedule-breakdown/{event_id}`

Review date: 2026-07-25  
Authentication in current code: none  
Validated response: event `254035`, completed swap event dated 2026-07-24

## What this capture returned

| JSON path | Observed result | Interpretation |
|---|---:|---|
| `status` | `"OK"` | Request succeeded. |
| `data.eventInfo` | object, 122 fields | Event configuration, venue, organizer, status, and format metadata. |
| `data.inProgressMatchList` | `[]` | No match was live when the completed event was queried. |
| `data.inProgressMatchListCount` | `0` | Agrees with the empty live-match array. |
| `data.playersList` | 64 rows | Registered-player/profile snapshot for the event. |
| `data.playersListCount` | `64` | Agrees with the array length and 64 unique player IDs. |

The response did **not** contain `overAllSchedule` or `availableMatchList`. Those keys are
expected by current application code but were absent from this completed-event response.
Consequently, this capture does not provide completed-match chronology, historical
partnerships, scores, or round-by-round results.

## Player row

| Variable | Likely meaning | Use guidance |
|---|---|---|
| `leagueID` | Event ID. | Event join key. |
| `playerID`, `fldPlayerID` | ACL player identifiers. | Use `playerID` as the primary player key; preserve both raw values. |
| `playerStatus` | Registration status. | Event participation metadata. |
| `playerCheckedIn` | Check-in flag/status. | Live-event operational state. |
| `paidStatus` | Payment status. | Sensitive operational field; not needed by the prediction engine. |
| `playerOptOut` | Player opt-out flag. | Eligibility/operational metadata; meaning needs confirmation. |
| `dateTimeStamp` | Registration or row-update timestamp. | Preserve as source metadata; exact semantics unconfirmed. |
| `holdMySpotPaymentMethod`, `holdMySpotPaymentAmount` | Registration payment details. | Sensitive and unnecessary for modeling; redact/omit. |
| `playerGroup` | Swap grouping assignment. | May affect pairing logic. |
| `playerFirstName`, `playerLastName` | Player name. | Display identity; redact from published samples. |
| `playerEmail`, `playerPhoneNo` | Player contact data. | Personal data; redact and do not ingest for predictions. |
| `playerPhoto` | Player-photo URL. | Display-only personal data. |
| `playerCity`, `playerState` | Player location. | Personal/location data; omit unless a defined feature requires it. |
| `playerSkillLevel` | ACL skill classification. | ACL-supplied categorical statistic. |
| `playerPPRPlayerInfo` | Additional PPR-related display/source field. | Preserve raw; semantics need validation. |
| `playerPPR` | ACL-supplied season/profile PPR snapshot. | Label as ACL value and retain separately from internally calculated PPR. |
| `playerCPI` | ACL-supplied CPI snapshot. | Official only as the value explicitly supplied by ACL; never infer CPI. |
| `cPITimeStamp` | Timestamp attached to the CPI snapshot. | Required provenance for CPI; it is not an event-time guarantee. |
| `conferenceID`, `conferenceName` | ACL conference assignment. | Player classification metadata. |
| `playerMembershipType`, `playerMembershipName` | ACL membership classification. | Profile metadata; modeling value unproven. |

## Reconciliation with `swap-standings/254035`

- Both endpoints returned the same 64 unique players.
- All 27 fields shared by their player rows matched exactly for every player.
- This includes `playerPPR`, `playerCPI`, and `cPITimeStamp`.
- `swap-standings` adds `partnerHistory`, wins, losses, differential, total points, and rank.
- Therefore, for a completed event, `swap-standings` is the richer source. The schedule
  response's player list is a duplicate roster/profile snapshot, not independent statistical
  corroboration.
- Player `142125` appeared with ACL PPR `7.39`, ACL CPI `6.35`, and CPI timestamp
  `2026-07-22 13:29:30`, two days before the event date.
- Three players had CPI `0`, PPR `0`, and no CPI timestamp. One additional player had CPI
  `2.01` but PPR `0`. Zero must be treated as unavailable or unvalidated unless ACL confirms
  that zero is a meaningful measured value.

## Privacy/redaction

The supplied response exposed an email address and phone number in all 64 player rows.
The event object also contains organizer and venue details. Documentation examples must use
`[REDACTED_EMAIL]`, `[REDACTED_PHONE]`, and `[REDACTED_PLAYER_NAME]` where appropriate.
Payment fields and unnecessary location data should be omitted rather than copied.

## Strategy impact

Use this endpoint for live swap-event state and roster discovery. Do not use this completed
response to reconstruct historical matches, and do not treat its roster CPI/PPR values as
values measured at the time of each match. Store the value, ACL source, ACL timestamp when
present, and collection timestamp. A populated response captured during an active event is
still needed to validate the match-list schema and determine whether schedule keys are
conditional on event state.
# Live validation update — event 254155, 2026-07-25

The live response contained two rows in `data.inProgressMatchList` and 14 rows
in `data.playersList`. Both matches had `matchStatusID: 1`,
`matchStatus: "In-Progress"`, `availableToStart: 0`, and
`matchStartTime: null`.

No available or scheduled pregame pairing list was returned. Player identities
for both sides were complete, but the pairings became observable only as
in-progress matches. They must not be backfilled as pregame predictions.

Sixteen personal fields were redacted before this live response entered the
provenance store.
