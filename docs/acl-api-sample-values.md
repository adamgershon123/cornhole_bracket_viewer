# ACL API Sample Values

Status: **Working review document — actual sanitized values from saved responses**

This companion to the [ACL API response field dictionary](./acl-api-response-field-dictionary.md)
shows concrete values observed in local ACL response captures. A sample proves only that a
field had that value and type in that response; it does not prove the field's definition,
allowed range, nullability, or stability.

## Redaction summary

The following source values are deliberately highlighted as redacted:

| Endpoint/sample | JSON path | Marker | Reason |
|---|---|---|---|
| Event and schedule information | `data.playerEmail` | `[REDACTED_EMAIL]` | Personal contact data is unnecessary for API schema review. |
| Event and schedule information | `data.adminEmail` | `[REDACTED_EMAIL]` | Administrator contact data is unnecessary for API schema review. |
| Swap player row | `data[0].playerEmail` | `[REDACTED_EMAIL]` | Personal contact data is unnecessary for analytics. |
| Swap player row | `data[0].playerPhoneNo` | `[REDACTED_PHONE]` | Personal contact data is unnecessary for analytics. |
| Swap player row | `data[0].playerFirstName`, `data[0].playerLastName` | `[REDACTED_PLAYER_NAME]` | The person's identity is unnecessary to demonstrate field shape. |
| Swap player row | `data[0].playerPhoto` | `[REDACTED_PROFILE_IMAGE]` | The image URL identifies the player and is unnecessary to demonstrate field shape. |
| Event-stat player row | `data[0].playerFirstName`, `data[0].playerLastName` | `[REDACTED_PLAYER_NAME]` | The person's identity is unnecessary to demonstrate statistics. |
| Match player records | player-name, nickname, image, city fields | `[REDACTED_PERSONAL_DATA: ...]` | Identity/location data is unnecessary to demonstrate match-stat structure. |

No token or cookie was present in the inspected response bodies.

## `GET /api/v1/events/{event_id}`

Source: saved event response for event `247734`.

Live response review: [`acl-api-endpoints/event-details.md`](./acl-api-endpoints/event-details.md).

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `eventID` | `247734` | integer | ACL event identifier. |
| `eventName` | `"ACL Friday Night Swap Club 52 - 7/17/2026"` | string | Event display name. |
| `startdate` | `"2026-07-17"` | string | Appears ISO-like; timezone is not included. |
| `leagueTime` | `"6:00 PM"` | string | Timezone is not included. |
| `eventType` | `"L"` | string | Code mapping needs confirmation. |
| `eventSubType` | `"O"` | string | Code mapping needs confirmation. |
| `matchType` | `"D"` | string | Appears to represent doubles; confirm. |
| `bracketType` | `"P"` | string | Code mapping needs confirmation. |
| `leagueStatus` | `"C"` | string | Appears completed; confirm. |
| `courtTotal` | `1` | integer | Configured court count. |
| `bucketID` | `11` | integer | Season/stat bucket meaning needs confirmation. |
| `teamCount` | `0` | integer | Zero despite a populated event; semantics need review. |
| `locationName` | `"Club 52"` | string | Public event venue. |
| `locationCity` | `"Melbourne"` | string | Event venue city. |
| `locationState` | `"FL"` | string | Event venue state. |
| `playerEmail` | `[REDACTED_EMAIL]` | string | Source returned an email value. |
| `adminEmail` | `[REDACTED_EMAIL]` | string | Source returned an administrator email value. |

## `GET /api/v1/bracket-data/{event_id}`

Source: saved populated bracket response for event `216491`.

Full consolidated review:
[`acl-api-endpoints/bracket-data.md`](./acl-api-endpoints/bracket-data.md).

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `eventInfo.eventID` | `216491` | integer | Event identifier. |
| `bracketDetails.length` | `61` | integer | Number of bracket-detail rows, not necessarily number of matches. |
| `bracketDetails[].roundid` | Example is a string | string | Exact sample should be recorded during the structured live review. |
| `bracketDetails[].forfeit` | Example is boolean | boolean | Indicates forfeit state. |
| `bracketDetails[].bracketmatchid` | Example is a string | string | Match identifier within bracket payload. |
| `bracketDetails[].courtid` | Example is numeric | integer | Court identifier. |
| `rosterDetails.team_count` | Present | integer | Roster team/entry count. |
| `playoffsTypeID` | Present | integer | Code mapping needs confirmation. |

The current sample confirms field types and population but this table intentionally avoids
copying team/player identity values. A sanitized bracket fixture should be produced during
the review.

## `GET /api/v1/player-events-grouped/{player_id}`

| Result | Sample |
|---|---|
| Saved response | `eventsGrouped: []` |
| Meaning | The cached request returned a successful but empty player-event list. |
| Needed next | A populated `ACTIVE` response and populated `COMPLETED` response for each relevant bucket. |

## `GET /api/auth/v1/players/{player_id}`

Full consolidated review: [`acl-api-endpoints/player-profile.md`](./acl-api-endpoints/player-profile.md).

| Result | Sample |
|---|---|
| Test | Player ID `142125`, 2026-07-25, Fanzone headers, no credentials |
| HTTP result | `403 Forbidden` |
| Response body | `{"status":"ERROR","success":false,"message":"NOT Authorized - No session found."}` |
| Interpretation | The endpoint required an authenticated session in this test. The current backend call does not supply one. |
| User-supplied authenticated result | `status: "OK"`, `message: "Player Successfully found"` |
| Successful response groups | `data[]`, `playerMembershipInfo[]`, `playerMembershipDetails[]`, `directorMembershipDetails[]`, `nearestDirector[]`, `nearestNonClubDirector[]` |
| Authentication conclusion | The endpoint succeeds in an authenticated session but failed without a session in our test. The authorized credential/session mechanism remains to be documented. |

### Sanitized successful player sample

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `userID`, `playerID` | `142125`, `142125` | integers | Equal in this sample. |
| `firstName`, `lastName` | `[REDACTED_PLAYER_NAME]` | strings | Player identity returned. |
| `email` | `[REDACTED_EMAIL]` | string | Sensitive contact data returned. |
| `phoneNo` | `[REDACTED_PHONE]` | string | Sensitive contact data returned. |
| `profileImage` | `[REDACTED_PROFILE_IMAGE]` | string | Player-specific image URL returned. |
| `dobYear`, `dobMonth`, `dobDay` | `[REDACTED_DATE_OF_BIRTH]` | integers | Full birth date can be reconstructed. |
| `skillLevel`, `skillLevelDesc` | `"C"`, `"Competitive"` | strings | Code and display label. |
| `state`, `city` | `"FL"`, `[REDACTED_PERSONAL_DATA: city]` | strings | Player location returned. |
| `playerLat`, `playerLng` | `[REDACTED_PRECISE_LOCATION]` | numbers | Precise player coordinates returned. |
| `status` | `"A"` | string | Account/player status code. |
| `lastLogin` | `[REDACTED_PERSONAL_DATA: account activity]` | string | Account activity timestamp returned. |
| `paymentMethod` | `[REDACTED_PERSONAL_DATA: payment metadata]` | string | Payment method returned. |
| `w9Verified`, `w9Type`, `w9DeliveryMethod` | `[REDACTED_PERSONAL_DATA: tax metadata]` | mixed | Tax-form metadata returned. |
| `playerPPRPlayerInfo` | `7.4153` | number | Higher precision than `playerPPR`; definition needs review. |
| `playerPPR` | `7.39` | number | ACL-reported PPR. |
| `playerCPI` | `6.35` | number | ACL-reported CPI. |
| `cPITimeStamp` | `"2026-07-22 13:29:30"` | string | No timezone included. |
| `conferenceID`, `conferenceName` | `1`, `"SouthEast Conference"` | integer, string | Conference information. |
| `playerMembershipName` | `"PLATINUM"` | string | Player membership label. |
| `directorMembershipName` | `"Club DIRECTOR"` | string | Director membership label. |
| `digitalWalletTotal` | `[REDACTED_FINANCIAL_BALANCE]` | number | Sensitive account balance returned. |

### Sanitized nested-group samples

| Group | Observed detail | Review note |
|---|---|---|
| `playerMembershipInfo[]` | Two records in supplied response | Contains both player and director membership records plus repeated contact data. |
| `playerMembershipDetails[]` | One record | Player membership dates, status, price, bucket, description, and feature permissions. |
| `directorMembershipDetails[]` | One record | Director membership dates, status, price, bucket, and feature permissions. |
| `nearestDirector[]` | Fifteen records | Includes third-party identities, precise coordinates, distance, and director type. |
| `nearestNonClubDirector[]` | Four records | Subset of non-club director types with precise coordinates. |

### Additional redactions for this supplied response

| JSON path | Marker/category | Reason |
|---|---|---|
| `data[].email`, membership email fields, director email fields | `[REDACTED_EMAIL]` | Personal and third-party contact data. |
| `data[].phoneNo`, membership phone fields | `[REDACTED_PHONE]` | Personal contact data. |
| Player/director first, last, and nickname fields | `[REDACTED_PLAYER_NAME]` | Identity unnecessary for schema review. |
| `data[].dobYear`, `dobMonth`, `dobDay` | `[REDACTED_DATE_OF_BIRTH]` | Reconstructable full birth date. |
| `data[].playerLat`, `playerLng`; nearby-director coordinate fields | `[REDACTED_PRECISE_LOCATION]` | Precise personal/third-party location. |
| Payment, address, W-9, wallet, last-login fields | Typed personal/financial markers | Unnecessary sensitive account information. |

## `POST /api/v1/player-compare-stats`

Full consolidated review:
[`acl-api-endpoints/player-compare-stats.md`](./acl-api-endpoints/player-compare-stats.md).

| Result | Sample |
|---|---|
| Successful response | Player `142125`, bucket `11`, `"2025 - 2026"` |
| ACL-reported PPR | `7.39` |
| ACL-reported DPR | `0.05` |
| ACL-reported opponent PPR | `7.34` |
| Rounds/bags | `5425` rounds, `21700` bags |
| Round-classification issue | Won + lost + tied is 818 rounds short of total; cause unknown |
| Needed next | Prior buckets, multi-player request, and small/zero-sample players |

## `GET /api/v1/event-standings/{event_id}`

Full consolidated review:
[`acl-api-endpoints/event-standings.md`](./acl-api-endpoints/event-standings.md).

| Result | Sample |
|---|---|
| Successful response | Event `216491`, 28 player rows, 14 represented doubles teams |
| Team ranks | `1, 2, 3, 4, 5, 7, 9, 13` |
| CPI timing | 26 of 28 CPI timestamps are after the event date |
| Result field conflict | `fldTotalMatchesWon/Lost` are all zero while `wins/losses` are populated |
| Zero/missing issue | Two CPI zeroes have null timestamps |
| Needed next | Singles, live, swap, and Swiss standings |

## `GET /api/v1/swap-standings/{event_id}`

Source: first standing row from event `247734`; identity/contact values are visibly
redacted.

An additional 64-player response for event `254035` is documented in the
[swap-standings endpoint review](./acl-api-endpoints/swap-standings.md).

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `leagueID` | `247734` | integer | Event identifier. |
| `playerID`, `fldPlayerID` | `200684` | integer | Aliases matched in this sample. |
| `playerStatus` | `"A"` | string | Code mapping needs confirmation. |
| `playerCheckedIn` | `"Y"` | string | String flag rather than boolean. |
| `paidStatus` | `"N"` | string | Payment-status code. |
| `playerOptOut` | `"N"` | string | String flag. |
| `dateTimeStamp` | `"2026-07-17 16:41:47"` | string | No timezone included. |
| `playerGroup` | `"B"` | string | Group/pool designation. |
| `playerFirstName`, `playerLastName` | `[REDACTED_PLAYER_NAME]` | string | Names were returned. |
| `playerEmail` | `[REDACTED_EMAIL]` | string | Email was returned. |
| `playerPhoneNo` | `[REDACTED_PHONE]` | string | Phone number was returned. |
| `playerPhoto` | `[REDACTED_PROFILE_IMAGE]` | string | Player-specific image URL was returned. |
| `playerCity` | `"Melbourne "` | string | Note trailing whitespace in source value. |
| `playerState` | `"FL"` | string | State abbreviation. |
| `playerSkillLevel` | `"A"` | string | Skill code mapping needs confirmation. |
| `playerPPRPlayerInfo` | `9.3486` | number | Meaning/difference from `playerPPR` needs review. |
| `playerPPR` | `9.33` | number | ACL-reported PPR in this response context. |
| `playerCPI` | `8.65` | number | ACL-reported CPI. |
| `cPITimeStamp` | `"2026-07-15 13:10:29"` | string | CPI timestamp without timezone. |
| `conferenceID` | `1` | integer | Conference identifier. |
| `conferenceName` | `"SouthEast Conference"` | string | Conference name. |
| `playerMembershipType` | `"P"` | string | Membership code. |
| `playerMembershipName` | `"PLATINUM"` | string | Membership label. |
| `partnerHistory` | `[29683, 229817, 216446, 239153]` | integer array | Appears to contain player IDs. Scope/order needs review. |
| `wins` | `4` | integer | Current-event wins. |
| `losses` | `0` | integer | Current-event losses. |
| `playerDifferentialPoints` | `88` | integer | Point differential. |
| `playerTotalPoints` | `96` | integer | Total points. |
| `isNegativeDiff` | `false` | boolean | Sign helper for differential. |
| `rank` | `1` | integer | Standing rank. |

## `GET /api/v1/swap-up-next-players-list/{event_id}`

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `data` | `[]` | array | Empty in inspected response. |
| `upNextPlayerCount` | `0` | integer | No players were queued in the sample. |

## `GET /api/v1/swap-schedule-breakdown/{event_id}`

Sources: saved responses for events `247734` and `254035`.

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `data.inProgressMatchList` | `[]` | array | No match was in progress at capture time. |
| `data.inProgressMatchListCount` | `0` | integer | Matches the empty array. |
| `data.playersListCount` | `60` | integer | Player-list count. |
| `data.playersList.length` | `60` | integer | Matches the reported count in this sample. |
| `data.eventInfo.eventID` | `247734` | integer | Event information is repeated inside schedule response. |
| `data.playersListCount` | `64` | integer | Event `254035`; matches 64 unique player rows. |
| `data.playersList[142125].playerPPR` | `7.39` | number | ACL-supplied profile/season PPR snapshot. |
| `data.playersList[142125].playerCPI` | `6.35` | number | ACL-supplied CPI snapshot. |
| `data.playersList[142125].cPITimeStamp` | `"2026-07-22 13:29:30"` | datetime string | ACL CPI provenance timestamp, two days before the event. |
| `data.playersList[*].playerEmail` | `[REDACTED_EMAIL]` | string | Email was populated in all 64 rows and is intentionally redacted. |
| `data.playersList[*].playerPhoneNo` | `[REDACTED_PHONE]` | string | Phone was populated in all 64 rows and is intentionally redacted. |

The completed `254035` response omitted `overAllSchedule` and `availableMatchList` entirely.
Populated active-event samples are still required to validate those conditional lists and
`inProgressMatchList`. See the
[endpoint review](./acl-api-endpoints/swap-schedule-breakdown.md).

## Swiss/Rounders endpoints

Event `248002` is confirmed through `/events/248002` as a completed Rounders doubles event
with `bracketType: "W"`, `matchType: "D"`, and `teamCount: 30`. Organizer email/name values
are intentionally represented as `[REDACTED_EMAIL]` and `[REDACTED_PLAYER_NAME]`.

This confirms the test event and format selector, not the endpoint responses below.

| Endpoint | Sample availability |
|---|---|
| `swiss-pairing-schedule-breakdown` | Validated: event `248002`, 75 completed matches across five rounds. |
| `swiss-pairing-standings` | Validated: 30 team-level rows for event `248002`. |
| `swiss-pairing-up-next-players-list` | Endpoint validated: completed event returned `data: []`, count `0`. |

Schedule sample facts:

| Variable | Observed value | Review note |
|---|---:|---|
| `data.overAllScheduleCount` | `75` | Five rounds of 15 matches. |
| `data.completedMatchListCount` | `75` | Same 75 rows as the overall schedule; do not concatenate. |
| `data.inProgressMatchListCount` | `0` | Completed-event capture. |
| `data.availableMatchListCount` | `0` | Completed-event capture. |
| `data.overAllSchedule[0].roundID` | `1` | Swiss round identifier. |
| `data.overAllSchedule[0].matchStatusID` | `5` | Completed status. |
| `data.overAllSchedule[0].matchEndTime` | `null` | End time was null for all completed matches. |
| embedded `playerEmail` | `[REDACTED_EMAIL]` | Populated for all 60 unique players. |
| embedded `playerPhoneNo` | `[REDACTED_PHONE]` | Populated for all 60 unique players. |

All embedded CPI timestamps were dated 2026-07-22, while the event occurred on 2026-06-13.
Those CPI/PPR fields are later ACL profile snapshots, not event-time ratings. See the
[Swiss schedule endpoint review](./acl-api-endpoints/swiss-pairing-schedule-breakdown.md).

Standings reconciliation:

| Check | Result |
|---|---|
| Team rows | 30 |
| Unique embedded players | 60 |
| Wins and losses vs. schedule | Exact match for all teams |
| Team total points vs. schedule | Exact match for all teams |
| Team differential vs. schedule | Exact match for all teams |
| Sum of wins / losses | `75 / 75`, matching 75 matches |
| `tiebreaker` formula | Not established; retain as ACL-supplied |
| Embedded email/phone | `[REDACTED_EMAIL]` / `[REDACTED_PHONE]` in all 60 player rows |

See the
[Swiss standings/up-next review](./acl-api-endpoints/swiss-pairing-standings.md).

## `GET /api/v1/event-player-stats/{event_id}`

Source: first statistic row from event `247734`; player identity is visibly redacted.

Full consolidated review:
[`acl-api-endpoints/event-player-stats.md`](./acl-api-endpoints/event-player-stats.md).

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `ranking` | `1` | integer | Row rank. |
| `playerID` | `200684` | integer | Public ACL player identifier retained for cross-response comparison. |
| `playerFirstName`, `playerLastName` | `[REDACTED_PLAYER_NAME]` | string | Names were returned. |
| `skillLevel` | `"Advanced"` | string | Human-readable skill label. |
| `rounds` | `20` | integer | Statistic sample size. |
| `totalPts` | `203` | integer | Total player points. |
| `ptsPerRnd` | `10.15` | number | `203 / 20 = 10.15` in this sample. |
| `opponentPts` | `145` | integer | Total opponent points. |
| `opponentPtsPerRnd` | `7.25` | number | `145 / 20 = 7.25` in this sample. |
| `diffPerRnd` | `2.9` | number | Matches `10.15 - 7.25` in this sample. |
| `TotalFourBaggers` | `7` | integer | Four-bagger count. |
| `fourBaggerPct` | `35` | number | `7 / 20 × 100 = 35`; denominator appears to be rounds here. |
| `bagsInPct` | `78.75` | number | Hole-bag percentage. |
| `bagsOnPct` | `17.5` | number | Board-bag percentage. |
| `bagsOffPct` | `3.75` | number | Off-board percentage; three bag percentages sum to 100. |
| `avgBagsInPerRnd` | `3.15` | number | `63 / 20 = 3.15` in this sample. |
| `totalBags` | `80` | integer | Consistent with four bags across 20 rounds. |
| `bagsIn` | `63` | integer | Hole-bag count. |

## `GET /api/v1/match-stats/...`

Source: saved completed doubles match, event `216491`, match `10`, game `1`.

### Match summary sample

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `eventID` | `"216491"` | string | Identifier is a string here, unlike numeric event IDs in other endpoints. |
| `matchID` | `"10"` | string | String identifier. |
| `gameID` | `"1"` | string | String identifier. |
| `matchType` | `"D"` | string | Appears doubles. |
| `bracketType` | `"D"` | string | Meaning may differ from match type; confirm. |
| `matchStatus` | `5` | integer | Current code treats this as completed. |
| `matchStatusDesc` | `"Match Completed"` | string | Confirms completed status in this sample. |
| `homeTeamID` | `5` | integer | Home-side team identifier. |
| `awayTeamID` | `4` | integer | Away-side team identifier. |
| `homeTeamName` | `"Team 5"` | string | Team label. |
| `awayTeamName` | `"Team 4"` | string | Team label. |
| `winningTeam` | `-1` | integer | Does not directly match team ID; coding requires review. |
| `courtid` | `4` | integer | Court identifier. |
| `currentRound` | `12` | integer | Final/current round count. |
| `homeScore` | `15` | integer | Final home score. |
| `awayScore` | `21` | integer | Final away score. |
| `rounddesc` | `""` | string | Empty rather than null. |
| `roundLimit` | `-1` | integer | Likely sentinel for no limit; confirm. |

### Player match-total sample

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| identity/name/location fields | `[REDACTED_PERSONAL_DATA: player identity]` | mixed | Fields were returned but values are unnecessary here. |
| `teamid` | `4` | integer | Player's team. |
| `playedinnings`, `rounds` | `6`, `6` | integers | Equal in this sample. |
| `totalbagsin`, `totalbagson`, `totalbagsoff` | `9`, `8`, `7` | integers | Sum equals 24 bags. |
| `totalbagsthrown` | `24` | integer | Four bags across six rounds. |
| `teamhomeaway` | `"AWAY"` | string | Side designation. |
| `scoringavg` | `"5.83"` | string | Numeric statistic encoded as text. |
| `scoringpct` | `"70.83"` | string | Numeric statistic encoded as text; formula needs review. |
| `totalpts` | `35` | integer | Player points. |
| `ptsperrnd` | `5.83` | number | `35 / 6`, rounded. |
| `opponentpts` | `36` | integer | Opponent player/side points; definition needs review. |
| `opponentptsperrnd` | `6` | number | `36 / 6`. |
| `diffperrnd` | `-0.17` | number | Approximate PPR difference. |
| `totalfourbaggers` | `1` | integer | Four-bagger count. |
| `fourbaggerpct` | `16.67` | number | `1 / 6 × 100`, suggesting round denominator. |
| `bagsinpct`, `bagsonpct`, `bagsoffpct` | `37.5`, `33.33`, `29.17` | numbers | Sum to 100 in this sample. |

### Inning/round sample

| Variable | Observed value | Observed type | Review note |
|---|---:|---|---|
| `inningno` | `1` | integer | Current code treats inning as round. |
| `playerid` | `234396` | integer | ACL player identifier. |
| `teamid` | `5` | integer | Team identifier. |
| player name fields | `[REDACTED_PLAYER_NAME]` | strings | Names were returned. |
| `bagsin`, `bagson`, `bagsoff` | `0`, `3`, `1` | integers | Four bags total. |
| `totalpoints` | `3` | integer | Gross player points implied by bag placement. |
| `teamname` | `"Team 5"` | string | Team label. |
| `teamhomeaway` | `"HOME"` | string | Side designation. |
| `event_match_inning_summary[0].inningNo` | `1` | integer | Note capitalization differs from `inningno`. |
| `event_match_inning_summary[0].homeScore` | `0` | integer | Meaning requires review. |
| `event_match_inning_summary[0].awayScore` | `0` | integer | Meaning requires review. |

Validation across the full response:

- 24 history rows represented four players playing six innings each.
- All four player aggregate rows exactly matched sums calculated from inning history.
- The final inning summary was `15`–`21`, matching the header's final score.
- `winningTeam` was `-1`; it must not be treated as team ID `4` or as a reliable winner.
- Names, nicknames, city/state, photo URLs, and administrator identity were present and are
  intentionally redacted or omitted from documentation samples.

See the [match-stats endpoint review](./acl-api-endpoints/match-stats.md).

## Missing sample checklist

- Populated player-event responses
- Player-profile response
- Player-compare response
- Populated event standings
- Populated swap up-next response
- Populated swap schedule match lists
- All Swiss/Rounders responses
- Singles match stats
- Live/incomplete match stats
- Match-stat 401 and 403 response metadata/body
- Null-heavy and malformed responses
