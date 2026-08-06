# ACL API Response Field Dictionary

Status: **Working review document — not official ACL documentation**

This is a simple description of data returned by each ACL API call currently used in the
repository. Descriptions are based on saved responses and how the current code uses the
fields. They should be confirmed during the ACL API review.

Actual sanitized examples are in
[`acl-api-sample-values.md`](./acl-api-sample-values.md). The examples are kept separate so
this field dictionary remains readable.

Confidence labels:

- **Observed** — present in a saved response.
- **Code-inferred** — referenced by current code, but no representative saved response was
  available or populated.
- **Interpretation** — the description is our best reading of the name/value, not a
  confirmed ACL definition.

## Visible redaction convention

Redaction must be explicit. A sanitized sample must preserve the field and replace only its
value with a typed marker:

| Marker | Meaning |
|---|---|
| `[REDACTED_EMAIL]` | An email address was returned here. |
| `[REDACTED_PHONE]` | A phone number was returned here. |
| `[REDACTED_TOKEN]` | A token, API key, or authorization credential was returned here. |
| `[REDACTED_COOKIE]` | A cookie or session value was returned here. |
| `[REDACTED_ADDRESS]` | A personal street address was returned here. |
| `[REDACTED_PERSONAL_DATA: category]` | Other unnecessary personal data was returned; the category explains what was removed. |

Every sanitized fixture must include a redaction summary listing:

- endpoint and capture scenario;
- JSON path of every redacted field;
- redaction category;
- number of values redacted;
- reason for redaction;
- whether the field is needed by the platform.

Example:

```json
{
  "playerEmail": "[REDACTED_EMAIL]",
  "playerPhoneNo": "[REDACTED_PHONE]"
}
```

```text
Redaction summary
- data[].playerEmail — EMAIL — 60 values — not needed for analytics
- data[].playerPhoneNo — PHONE — 60 values — not needed for analytics
```

Do not remove the field entirely, replace it with `null`, or use a generic `***` marker.
Those approaches hide the fact that ACL returned sensitive data and make nullability/schema
review inaccurate. Redaction markers are documentation/fixture values only and must never
be ingested as source facts.

ACL frequently returns aliases differing only by capitalization, such as `leagueYear` and
`leagueyear`. Exact source names are retained below. Do not assume aliases always contain
identical values until tested.

## Common response and capture fields

| Variable | Likely meaning | Evidence |
|---|---|---|
| `status` | ACL request/application status, often a text value such as success or error. | Observed |
| `message` | ACL response message. | Observed |
| `data` | Primary response object or list; its shape varies by endpoint. | Observed |
| `cachedData` | Indicates ACL believes the response came from cached data. | Observed; interpretation |
| `_fetchedAt` | Timestamp added by Cheesebaggers when the response was saved. Not returned by ACL. | Observed in local cache |
| `_aclResponseDate` | ACL HTTP `Date` response header copied into the saved file. | Observed in local cache |
| `_aclEtag` | ACL HTTP `ETag` response header copied into the saved file. | Observed in local cache |
| `meta.*` | Cheesebaggers capture metadata wrapping some raw payloads. Not part of the ACL JSON body. | Observed in season-platform cache |
| `payload` | Original ACL response body inside the season-platform capture wrapper. | Observed |

## Shared event information object

Returned as `data` by `/events/{event_id}` and as `eventInfo` by bracket/schedule endpoints.

| Variable | Likely meaning | Evidence |
|---|---|---|
| `leagueID`, `leagueid`, `eventID` | ACL event identifier aliases. | Observed; interpretation |
| `leagueYear`, `leagueyear`, `eventYear` | Event/season year aliases. | Observed; interpretation |
| `leagueSessionID`, `leaguesessionid` | ACL session or season segment identifier. | Observed; interpretation |
| `leaguename`, `leagueName`, `eventName` | Event name aliases. | Observed |
| `leagueTypeCOBS` | Internal ACL league/event type code; exact definition unknown. | Observed; interpretation |
| `tourID` | Tour or circuit identifier. | Observed; interpretation |
| `leagueDay`, `leagueTime`, `starttime` | Scheduled day/time values. Exact timezone/format needs review. | Observed |
| `startdate`, `leaguestartdate`, `leagueStartDate` | Event start-date aliases. | Observed |
| `leagueStatus` | Event status. Value mapping needs review. | Observed |
| `eventtype`, `eventType` | Event-type aliases. | Observed |
| `eventsubtype`, `eventSubType` | Event-subtype aliases. | Observed |
| `eventGenderType` | Gender/category designation. | Observed; interpretation |
| `eventBaggerLevel` | Skill or player-level restriction. | Observed; interpretation |
| `eventPlayerType` | Player/entry type. Exact values need review. | Observed; interpretation |
| `teamTourney` | Flag indicating team-tournament behavior. | Observed; interpretation |
| `leagueBlindDraw`, `blindDraw` | Blind-draw configuration aliases. | Observed |
| `matchtype`, `matchType` | Singles/doubles or match-format code. | Observed; interpretation |
| `brackettype`, `bracketType` | Bracket-format code. Known code meanings need review. | Observed |
| `winnerBracketType`, `loserBracketType` | Winner/loser bracket configuration codes. | Observed; interpretation |
| `courtTotal` | Number of courts configured for the event. | Observed; interpretation |
| `courtTotalType`, `courtTotalDetails` | Court-count configuration details. | Observed; interpretation |
| `liveRoundStats` | Flag/configuration for live round statistics. | Observed; interpretation |
| `eventScoringType` | Event scoring-system code or label. | Observed; interpretation |
| `roundLimit`, `roundLimitBracket` | Configured round limits. Exact unit/behavior needs review. | Observed |
| `playerPoolSize` | Configured player-pool size. | Observed; interpretation |
| `redZoneActiveFlag` | ACL RedZone feature flag. Exact behavior unknown. | Observed; interpretation |
| `autoAssignCourt`, `reservedCourtID` | Court-assignment configuration. | Observed; interpretation |
| `deviceDisplayMode` | Display/scoring-device mode. | Observed; interpretation |
| `matchPlayFormat`, `matchPlayBracketFormat` | Match-play format configuration. | Observed; interpretation |
| `matchPlaySinglesSpots`, `matchPlayDoublesSpots`, `totalMatchPlaySpots` | Match-play capacity values. | Observed; interpretation |
| `eventBucketID`, `bucketID` | ACL season/statistical bucket identifier aliases. | Observed; interpretation |
| `eventGroupID`, `eventGroupSubID`, `eventGroupDesc` | Event grouping/category identifiers and description. | Observed; interpretation |
| `eventGroupCollegeName`, `eventGroupCollegeType` | College-event grouping information. | Observed; interpretation |
| `teamCount` | Number of registered teams/entries. | Observed |
| `bracketStarted` | Whether the event bracket has started. | Observed |
| `eventListType` | Event-list/category code. | Observed; interpretation |
| `superEventID`, `superEventName`, `superEventStatus` | Parent/super-event information when applicable. | Observed; interpretation |
| `leagueLocationID` | ACL venue/location identifier. | Observed |
| `leagueLocationName`, `locationName` | Venue-name aliases. | Observed |
| `leagueAddress`, `locationAddress` | Venue street address aliases. | Observed |
| `locationCity`, `locationState`, `locationZip`, `countryCode` | Venue geographic fields. | Observed |
| `locationLat`, `locationLng` | Venue coordinates. | Observed |
| `leaguePhone`, `leagueWebsite`, `leagueEmailAddress`, `leagueImage` | Event/venue contact and image fields. | Observed |
| `leagueMiscDetails`, `leagueNotes` | Free-text event details or notes. | Observed |
| `fldPlayerID`, `eventAdminID`, `adminID` | Event administrator/player identifier aliases. | Observed; interpretation |
| `playerFirstName`, `playerLastName`, `playerEmail` | Player/admin identity fields attached to the event. Exact role needs review. | Observed |
| `adminFirstName`, `adminLastName`, `adminEmail` | Event administrator contact fields. | Observed |
| `preRegistrationOpen`, `leaguePreRegistrationOpen` | Pre-registration flags. | Observed |
| `eventFee` | Event entry fee. Currency/unit needs review. | Observed |
| `entryFeePerPersonGoldPlatinum` | Entry fee for named membership levels. | Observed; interpretation |
| `entryFeesCollectedOnline`, `entryFeesCollectedCash`, `totalEntryFeesCollected` | Event fee collection totals. | Observed; interpretation |
| `payoutPercentage`, `totalAmountPaidOut`, `totalPrizePool` | Event payout information. | Observed; interpretation |
| `ACLFeesCollected`, `directorPerPlayerFee`, `directorRevenue` | ACL/director financial fields. | Observed; interpretation |
| `additionalMoneyForPayouts`, `addDirectorNonMemberFeeToPayout` | Additional payout configuration. | Observed; interpretation |
| `eventPaid`, `eventPaidTimeStamp` | Event payment status and timestamp. | Observed; interpretation |
| `leagueESPNFlag`, `espnFlag`, `fantasyExternalID`, `fantasyExternalEventInfo` | Broadcast/fantasy integration fields. | Observed; interpretation |
| `eventCharityFlag`, `eventCharityAmountRaised` | Charity-event configuration and amount. | Observed |
| `sendCourtSMS`, `sendScoreSMS` | SMS-notification configuration. | Observed |
| `holdMySpotStatus`, `holdMySpotMaxTeamCount`, `holdMySpotPaymentOptions` | Hold-my-spot registration configuration. | Observed; interpretation |
| `useABGrouping` | A/B grouping flag. Exact behavior needs review. | Observed; interpretation |
| `aclLite`, `indoor` | ACL Lite and indoor-event flags. | Observed; interpretation |

## `GET /api/v1/events/{event_id}`

Returns the shared event information object under `data`. See the table above.

See the consolidated [event-details endpoint review](./acl-api-endpoints/event-details.md)
for the live response, sanitized values, inconsistencies, and review questions.

## `GET /api/v1/bracket-data/{event_id}`

See the consolidated [bracket-data endpoint review](./acl-api-endpoints/bracket-data.md) for
the populated response, duplicate position-row model, synthetic participants, and timestamp
conflicts.

| Variable | Likely meaning | Evidence |
|---|---|---|
| `eventInfo` | Shared event information object. | Observed |
| `bracketDetails[]` | One bracket-position/team record per array item; two or more records may describe a match. | Observed; interpretation |
| `bracketDetails[].roundid` | Bracket round identifier. | Observed |
| `bracketDetails[].rounddesc` | Human-readable round description. | Observed |
| `bracketDetails[].forfeit` | Whether the entry/match is marked as a forfeit. | Observed |
| `bracketDetails[].bracketside` | Bracket side, likely winner/loser or another bracket partition. | Observed; interpretation |
| `bracketDetails[].bracketmatchid` | Match identifier within the event bracket. | Observed |
| `bracketDetails[].bracketpos` | Position in a match, commonly top/bottom notation. | Observed; interpretation |
| `bracketDetails[].courtid` | Assigned court identifier. | Observed |
| `bracketDetails[].bracketteamid` | Team/entry identifier within the bracket. | Observed |
| `bracketDetails[].bracketteamname` | Team/entry display name. | Observed |
| `bracketDetails[].scores` | Score/game-result structure; null in the inspected fixture and variant shape needs review. | Observed |
| `bracketDetails[].player_info[]` | Players belonging to the bracket team. Exact field set varies and needs capture. | Code-inferred |
| `bracketDetails[].gameResults[]` | Per-game IDs, status, and home/away scores when supplied. | Code-inferred |
| `rosterDetails` | Event roster summary object. | Observed |
| `rosterDetails.leaguename` | Event name in roster summary. | Observed |
| `rosterDetails.team_count` | Team/entry count. | Observed |
| `playoffsTypeID` | Playoff/bracket format identifier. | Observed; interpretation |

## `GET /api/v1/player-events-grouped/{player_id}`

The inspected cached response was empty. The following item fields are consumed by current
code and need confirmation with populated live responses.

| Variable | Likely meaning | Evidence |
|---|---|---|
| `eventsGrouped[]` | Events associated with the requested player and status/bucket filter. | Observed container |
| `leagueID` | Event identifier. | Code-inferred |
| `leagueName` | Event name. | Code-inferred |
| `leaguestartdate` | Event start date. | Code-inferred |
| `leagueTime` | Event start time. | Code-inferred |
| `leagueStatus` | Event status. | Code-inferred |
| `leagueLocationID`, `leagueLocationName` | Venue identifier and name. | Code-inferred |
| `locationCity`, `locationState` | Venue city and state. | Code-inferred |
| `matchType`, `bracketType` | Match and bracket formats. | Code-inferred |
| `blindDraw` | Blind-draw flag. | Code-inferred |
| `eventType`, `eventSubType` | Event classification. | Code-inferred |
| `scheduleCount` | Number of scheduled entries/matches; exact meaning needs review. | Code-inferred |
| `bracketStarted` | Whether bracket play has begun. | Code-inferred |
| `adminID`, `adminFirstName`, `adminLastName` | Event administrator identity. | Code-inferred |

## `GET /api/auth/v1/players/{player_id}`

The user supplied a successful response for player `142125`. The response contains far more
than a public player profile and includes sensitive account, contact, location, financial,
tax-form, membership, and director data.

See the consolidated [player-profile endpoint review](./acl-api-endpoints/player-profile.md)
for the authentication results, sanitized samples, response groups, and review decisions in
one place.

| Variable | Likely meaning | Evidence |
|---|---|---|
| `status`, `message` | Application status and success message. | Observed |
| `data[]` | Player/account profile rows; one row in the supplied response. | Observed |
| `playerMembershipInfo[]` | Player and director membership records combined. | Observed |
| `playerMembershipDetails[]` | Player-membership records. | Observed |
| `directorMembershipDetails[]` | Director-membership records. | Observed |
| `nearestDirector[]` | Nearby club/regional/state directors with coordinates and distance. | Observed |
| `nearestNonClubDirector[]` | Nearby non-club directors. | Observed |

### `data[]` player/account record

| Variable | Likely meaning | Evidence |
|---|---|---|
| `userID`, `playerID` | ACL user and player identifiers; equal in the sample. | Observed |
| `firstName`, `lastName`, `nickName` | Player identity/display-name fields. | Observed |
| `email`, `phoneNo` | **Sensitive contact data; redact and exclude from analytics by default.** | Observed |
| `profileImage` | Player profile-image URL. | Observed |
| `gender`, `playerGender`, `ageGroup` | Demographic/classification fields. | Observed |
| `dobYear`, `dobMonth`, `dobDay` | **Sensitive birth-date components; redact/exclude unless expressly required.** | Observed |
| `skillLevel`, `skillLevelDesc` | ACL skill code and label. | Observed |
| `state`, `city`, `countryCodeID` | Player location fields. | Observed |
| `playerLat`, `playerLng` | **Sensitive precise coordinates; redact/exclude by default.** | Observed |
| `playerCurrency` | Account/player currency code. | Observed |
| `status`, `lastLogin` | Account status and last-login timestamp. | Observed |
| `adminType`, `playerType`, `leagueAdmin`, `leagueAdminType` | Account/player/director role classifications. | Observed |
| `collegeName`, `conferenceLocked` | College and conference-lock values. `"NULL"`/`"FALSE"` may be string sentinels. | Observed |
| `paymentMethod`, `paypalEmail` | **Sensitive payment metadata; redact/exclude by default.** | Observed |
| `paymentAddress`, `paymentCity`, `paymentState`, `paymentZip` | **Sensitive payment address fields; redact/exclude by default.** | Observed |
| `w9Verified`, `w9Type`, `w9DeliveryMethod` | **Sensitive tax-form status/type/delivery metadata; exclude by default.** | Observed |
| `codeOfConduct`, `directorAgreement` | Agreement/acceptance flags. | Observed |
| `playerPPRPlayerInfo` | Higher-precision PPR-like account value; definition needs confirmation. | Observed |
| `playerPPR` | ACL-reported PPR. Scope/window needs confirmation. | Observed |
| `playerCPI` | ACL-reported CPI. | Observed |
| `cPITimeStamp` | CPI observation/update timestamp. | Observed |
| `resetPasscode` | **Credential-recovery field; never retain or expose, even when null.** | Observed |
| `playerServiceBackground`, `playerNotes` | Service/background flag and account notes. Exact purpose needs review. | Observed |
| `selectedDirectorID`, `selectedDirectorFirstName`, `selectedDirectorLastName` | Selected director identity. | Observed |
| `conferenceID`, `conferenceName`, `conferenceLogoUrl`, `conferenceFileName` | Conference information. | Observed |
| `conferenceDirectorID`, `conferenceDirectorFirstName`, `conferenceDirectorLastName` | Conference director identity. | Observed |
| `conferenceDirectorEmail` | **Third-party contact data; redact/exclude by default.** | Observed |
| `playerMembershipCount`, `playerMembershipID`, `playerMembershipName` | Player membership summary. | Observed |
| `directorMembershipCount`, `directorrMembershipID`, `directorMembershipName` | Director membership summary; note apparent `directorr` typo. | Observed |
| `playerDiscounts` | Player-discount eligibility flag. | Observed |
| `digitalWalletTotal` | **Sensitive account balance; exclude from analytics and normal fixtures.** | Observed |

### Membership records

| Variable group | Likely meaning | Evidence |
|---|---|---|
| Player/director identity and contact fields | Member and associated director identity. Emails/phones require redaction. | Observed |
| `playerMembershipID`, `playerMembershipName`, `playerMembershipDesc` | Membership identifier, label, and description. | Observed |
| `playerMembershipType`, `playerMembershipSubType` | Membership category codes. | Observed |
| Purchase/start/expiry/end timestamps | Membership lifecycle dates. | Observed |
| `playerMembershipStatus` | Membership status code. | Observed |
| `bucketID`, `bucketDesc` | Membership season/stat bucket. | Observed |
| `playerMembershipPrice`, `playerMembershipPointsSold` | **Financial/membership price values; retention needs review.** | Observed |
| `eventsResultsIncludedInStandings` | Whether event results count in standings. | Observed |
| Feature-access flags | Discounts, messaging, tour access, player information, membership processing, bracket restrictions. | Observed |

### Nearby-director records

| Variable | Likely meaning | Evidence |
|---|---|---|
| `directorPlayerID`, `directorID` | Director player/account identifiers. | Observed |
| `directorSubType`, `directorType` | Director role code and label. | Observed |
| `playerFirstName`, `playerLastName`, `playerState` | Director identity/location. | Observed |
| `fldPlayerLocationLat`, `fldPlayerLocationLng` | **Third-party precise coordinates; redact/exclude by default.** | Observed |
| `distance` | Distance from the requested player; unit appears likely miles but is unconfirmed. | Observed; interpretation |
| `rn` | Result row/rank number. | Observed; interpretation |

The analytics platform should use a strict allowlist for this endpoint rather than persisting
the complete successful response into general analytics storage. Raw retention, if required
for provenance, needs encrypted restricted storage and a documented retention policy.

## `POST /api/v1/player-compare-stats`

Each `data[]` item represents the ACL aggregate statistics for one requested player/bucket.

See the consolidated
[player-compare statistics review](./acl-api-endpoints/player-compare-stats.md) for the
successful response, arithmetic reconciliation, and unexplained round-classification gap.

| Variable | Likely meaning | Evidence |
|---|---|---|
| `playerID` | Player identifier. | Code-inferred |
| `playerFirstName`, `playerLastName` | Player name. | Code-inferred |
| `playerPhoto` | Profile image reference. | Code-inferred |
| `playerSkillLevel` | ACL skill-level label. | Code-inferred |
| `bucketID` | Statistical season/bucket identifier. | Code-inferred |
| `yearDesc` | Human-readable year/season description. | Code-inferred |
| `ptsPerRnd` | ACL-reported points per round (PPR) for the requested bucket. | Code-inferred |
| `DPR` | ACL-reported differential per round. Exact formula needs confirmation. | Code-inferred |
| `OppPtsPerRnd` | ACL-reported opponent points per round. | Code-inferred |
| `bagsTotal` | Total bags recorded. | Code-inferred |
| `bagsInTotal`, `bagsInPct` | Hole bags and percentage. | Code-inferred |
| `bagsOnTotal`, `bagsOnPct` | Board bags and percentage. | Code-inferred |
| `bagsOffTotal`, `bagsOffPct` | Off-board bags and percentage. | Code-inferred |
| `fourBaggersTotal`, `fourBagPct` | Four-bagger count and rate. Denominator needs confirmation. | Code-inferred |
| `rdsTotal` | Total rounds. | Code-inferred |
| `rdsWonTotal`, `roundsWonPct` | Rounds won and win percentage. | Code-inferred |
| `rdsLostTotal`, `roundsLostPct` | Rounds lost and loss percentage. | Code-inferred |
| `rdsTiedTotal`, `roundsTiedPct` | Tied/wash rounds and percentage. Exact definition needs review. | Code-inferred |
| `totPtsTotal` | Total player points. | Code-inferred |
| `oppPtsTotal` | Total opponent points. | Code-inferred |

## `GET /api/v1/event-standings/{event_id}`

A populated doubles response has now been validated. See the consolidated
[event-standings endpoint review](./acl-api-endpoints/event-standings.md) for row grain,
team/ranking behavior, CPI timing, and conflicting result fields.

Each `data[]` item contains:

| Variable | Likely meaning | Evidence |
|---|---|---|
| `fldEventRank` | Finishing rank/place. | Code-inferred |
| `fldEventPos` | Event position; distinction from rank needs review. | Code-inferred |
| `fldEventWeekPoints` | Points awarded for the event/week. | Code-inferred |
| `fldTeamID`, `fldTeamName` | Team identifier and name. | Code-inferred |
| `wins`, `losses` | Event match wins and losses. | Code-inferred |
| `playerPPR` | ACL-reported player PPR for the event. | Code-inferred |
| `fldPlayerID` | Player identifier. | Code-inferred |
| `fldPlayerFirstName`, `fldPlayerLastname` | Player name. | Code-inferred |

## Shared swap player/standing item

Used by `swap-standings`, `swap-up-next`, and `playersList` in schedule responses.

| Variable | Likely meaning | Evidence |
|---|---|---|
| `leagueID` | Event identifier. | Observed |
| `playerID`, `fldPlayerID` | Player identifier aliases. | Observed |
| `playerStatus` | Registration/player status. | Observed; interpretation |
| `playerCheckedIn` | Check-in status/flag. | Observed |
| `paidStatus` | Payment status. | Observed |
| `playerOptOut` | Opt-out status. Exact feature needs review. | Observed; interpretation |
| `dateTimeStamp` | Source record timestamp. Semantics/timezone need review. | Observed |
| `holdMySpotPaymentMethod`, `holdMySpotPaymentAmount` | Registration payment details. | Observed; interpretation |
| `playerGroup` | Player grouping/pool designation. | Observed; interpretation |
| `playerFirstName`, `playerLastName` | Player name. | Observed |
| `playerEmail`, `playerPhoneNo` | Player contact information. **Redaction required and must be highlighted in fixture summary.** | Observed |
| `playerPhoto` | Profile-image reference. | Observed |
| `playerCity`, `playerState` | Player location. | Observed |
| `playerSkillLevel` | ACL skill-level label. | Observed |
| `playerPPRPlayerInfo` | PPR-related player-info value; exact meaning is unknown. | Observed; interpretation |
| `playerPPR` | ACL-reported PPR in this event/registration context. Scope needs confirmation. | Observed |
| `playerCPI` | ACL-reported CPI. | Observed |
| `cPITimeStamp` | CPI observation/update timestamp. | Observed; interpretation |
| `conferenceID`, `conferenceName` | ACL conference identifier/name. | Observed |
| `playerMembershipType`, `playerMembershipName` | ACL membership information. | Observed |
| `partnerHistory[]` | Partner identifiers/history associated with the player/event. Item shape needs review. | Observed container |
| `wins`, `losses` | Current event wins/losses. | Observed |
| `playerDifferentialPoints` | Current point differential. | Observed; interpretation |
| `playerTotalPoints` | Current points total. | Observed; interpretation |
| `isNegativeDiff` | Whether differential points are negative. | Observed |
| `rank` | Current event rank. | Observed |

## `GET /api/v1/swap-standings/{event_id}`

Returns `data[]` using the shared swap player/standing item above.

See the consolidated [swap-standings endpoint review](./acl-api-endpoints/swap-standings.md)
for validated rank ordering, reciprocal partner histories, CPI timing, missing-stat
representation, and privacy findings.

## `GET /api/v1/swap-up-next-players-list/{event_id}`

| Variable | Likely meaning | Evidence |
|---|---|---|
| `data[]` | Players/entries waiting or eligible for upcoming matches; expected to resemble the shared swap player item. | Observed empty container; code-inferred items |
| `upNextPlayerCount` | Number of returned/eligible up-next players. | Observed |

## `GET /api/v1/swap-schedule-breakdown/{event_id}`

| Variable | Likely meaning | Evidence |
|---|---|---|
| `data.eventInfo` | Shared event information object. | Observed |
| `data.inProgressMatchList[]` | Matches currently in progress. Empty in inspected fixture. | Observed container |
| `data.inProgressMatchListCount` | Count of in-progress matches. | Observed |
| `data.availableMatchList[]` | Matches ready/available to be assigned or played. | Code-inferred |
| `data.overAllSchedule[]` | Overall event match schedule. | Code-inferred |
| `data.playersList[]` | Registered player list using the shared swap player item. | Observed |
| `data.playersListCount` | Registered-player count. | Observed |

In the completed event `254035` capture, `overAllSchedule` and `availableMatchList` were
absent—not empty arrays—and `inProgressMatchList` was empty. Its 64 player rows exactly
matched the 27 shared fields in `swap-standings/254035`; the standings endpoint additionally
returned results and partner history. Current code expects populated schedule match items to
include match/team/player identifiers, court, status, scores, round text, and player lists.
A capture during an active event is needed to record their exact names and variants.

See the consolidated
[swap-schedule-breakdown endpoint review](./acl-api-endpoints/swap-schedule-breakdown.md).

## Swiss/Rounders endpoints

### `GET /api/v1/swiss-pairing-schedule-breakdown/{event_id}`

Validated for completed event `248002`. It returned `overAllSchedule`,
`completedMatchList`, `inProgressMatchList`, and `availableMatchList` plus corresponding
count fields. Both overall and completed lists contained the same 75 match rows.

Each match row contains event/match/round IDs, fixed home/away team IDs, status, start/end
timestamps, court, compact score/standings-point objects, duplicated scalar scores, and two
embedded player arrays. The embedded player rows contain identity/contact/profile fields and
ACL PPR/CPI snapshots.

See the consolidated
[Swiss schedule endpoint review](./acl-api-endpoints/swiss-pairing-schedule-breakdown.md).

### `GET /api/v1/swiss-pairing-standings/{event_id}?roundID=0`

Validated for event `248002`. `data[]` contains one row per fixed team with `leagueID`,
`teamID`, `id`, `seed`, `disbanded`, `droppedOut`, `teamPlayerList`, `wins`, `losses`,
`tiebreaker`, `teamDifferentialPoints`, `teamTotalPoints`, `isNegativeDiff`, and `rank`.
Wins, losses, total points, and differential reconciled exactly to the schedule for all 30
teams. The tiebreak formula remains unknown.

### `GET /api/v1/swiss-pairing-up-next-players-list/{event_id}?roundID=0`

Validated with an empty completed-event response: `data: []` and `upNextPlayerCount: 0`.
Exact populated-item fields remain pending capture.

See the consolidated
[Swiss standings/up-next review](./acl-api-endpoints/swiss-pairing-standings.md).

## `GET /api/v1/event-player-stats/{event_id}`

See the consolidated
[event-player statistics review](./acl-api-endpoints/event-player-stats.md) for the
successful response, full-row arithmetic validation, ranking behavior, and synthetic
participant findings.

Each `data[]` item contains ACL-reported event statistics for one player.

| Variable | Likely meaning | Evidence |
|---|---|---|
| `ranking` | Player rank within the returned event-stat list. | Observed |
| `playerID` | Player identifier. | Observed |
| `playerFirstName`, `playerLastName` | Player name. | Observed |
| `skillLevel` | Player skill-level label. | Observed |
| `rounds` | Rounds recorded for this event statistic. | Observed |
| `totalPts` | Player points across those rounds. | Observed |
| `ptsPerRnd` | ACL-reported event PPR. | Observed |
| `opponentPts` | Opponent points across those rounds. | Observed |
| `opponentPtsPerRnd` | ACL-reported opponent PPR. | Observed |
| `diffPerRnd` | ACL-reported differential per round. | Observed |
| `TotalFourBaggers` | Four-bagger count. | Observed |
| `fourBaggerPct` | Four-bagger percentage. Denominator needs confirmation. | Observed |
| `bagsInPct`, `bagsOnPct`, `bagsOffPct` | Hole, board, and off-board bag percentages. | Observed |
| `avgBagsInPerRnd` | Average hole bags per round. | Observed |
| `totalBags` | Total bags recorded. | Observed |
| `bagsIn` | Total hole bags. | Observed |
| `isAdminDomain` | Whether response context is the ACL admin domain. | Observed; interpretation |
| `origin` | Origin/context value returned by the endpoint. | Observed; interpretation |

## `GET /api/v1/match-stats/eventid/{event_id}/matchid/{match_id}/gameid/{game_id}`

### Match/game summary

| Variable | Likely meaning | Evidence |
|---|---|---|
| `eventID`, `matchID`, `gameID` | Event, match, and game identifiers. | Observed |
| `week_id` | Event week/round grouping identifier; exact meaning needs review. | Observed; interpretation |
| `adminID` | Administrator identifier. | Observed |
| `event_name` | Event name. | Observed |
| `matchType`, `bracketType` | Match and bracket formats. | Observed |
| `eventGroupID`, `eventGroupSubID`, `eventGroupDesc` | Event group/category fields. | Observed |
| `matchStatus`, `matchStatusDesc` | Match status code and label. Current code treats `5` as complete. | Observed |
| `scoresheet` | Whether a scoresheet is available/enabled. | Observed; interpretation |
| `homeTeamID`, `awayTeamID` | Competing team identifiers. | Observed |
| `homeTeamName`, `awayTeamName` | Competing team names. | Observed |
| `winningTeam` | Winning team identifier or side value. It was `-1` in a completed 15–21 game, so `-1` is unknown/unpopulated rather than the winner. | Observed |
| `courtid` | Court identifier. | Observed |
| `homeColor`, `awayColor` | Display colors for each side. | Observed |
| `currentRound` | Current/final round number. | Observed |
| `homeScore`, `awayScore` | Game/match scores. | Observed |
| `homePlayerPoints`, `awayPlayerPoints` | Raw player points for each side. | Observed; interpretation |
| `homeRoundScore`, `awayRoundScore` | Current/final round score values. | Observed; interpretation |
| `homeBagsThrown`, `awayBagsThrown` | Bags thrown by each side. | Observed |
| `rounddesc` | Bracket round description. | Observed |
| `roundLimit` | Configured round limit. | Observed |

### `event_match_details[]` — player game totals

| Variable | Likely meaning | Evidence |
|---|---|---|
| `teamid`, `playerid` | Team and player identifiers. | Observed |
| `playerfirstname`, `playerlastname`, `playernickname` | Player name fields. | Observed |
| `playerstate`, `playercity`, `playerimage` | Player profile/location fields. | Observed |
| `playedinnings`, `rounds` | Innings/rounds played. Relationship needs confirmation. | Observed |
| `bagsin`, `bagson`, `bagsoff` | Hole, board, and off-board bag values; scope needs confirmation. | Observed |
| `avgbagsin`, `avgbagson` | Average hole/board bag values. | Observed |
| `totalbagsin`, `totalbagson`, `totalbagsoff`, `totalbagsthrown` | Bag totals for the game. | Observed |
| `teamhomeaway` | Home/away side label. | Observed |
| `scoringavg`, `scoringpct` | Scoring average/rate. Exact formula needs review. | Observed |
| `totalpts`, `ptsperrnd` | Total points and ACL-reported game PPR. | Observed |
| `opponentpts`, `opponentptsperrnd` | Opponent points and opponent PPR. | Observed |
| `diffperrnd` | Differential per round. | Observed |
| `totalfourbaggers`, `fourbaggerpct` | Four-bagger total and rate. | Observed |
| `bagsinpct`, `bagsonpct`, `bagsoffpct` | Hole/board/off-board percentages. | Observed |

### `event_team_details[]` — team membership

| Variable | Likely meaning | Evidence |
|---|---|---|
| `playerid` | Player identifier. | Observed |
| `teamid` | Team identifier. | Observed |
| `teamname` | Team name. | Observed |

### `event_match_inning_history[]` — player round facts

| Variable | Likely meaning | Evidence |
|---|---|---|
| `inningno` | Inning/round number. Current normalization treats it as a round. | Observed; interpretation |
| `playerid`, `teamid` | Player and team identifiers. | Observed |
| `playerfirstname`, `playerlastname` | Player name. | Observed |
| `bagsin`, `bagson`, `bagsoff` | Hole, board, and off-board bags for the player in that inning. | Observed |
| `totalpoints` | Player points in that inning. | Observed |
| `teamname` | Team name. | Observed |
| `teamhomeaway` | Home/away side. | Observed |

### `event_match_inning_summary[]` — side round scores

| Variable | Likely meaning | Evidence |
|---|---|---|
| `inningNo` | Inning/round number. Note capitalization differs from `inningno`. | Observed |
| `homeScore`, `awayScore` | Cumulative cancellation-scoring game score after the inning. The final row matched the 15–21 header score in the inspected game. | Observed; validated in one game |

### Other match-stat fields

| Variable | Likely meaning | Evidence |
|---|---|---|
| `matchPlayInfo` | Additional match-play configuration/details. Empty object in inspected response. | Observed |
| `matchPlayScorebugFlag` | Whether the match-play scorebug is enabled. | Observed; interpretation |

The aggregate player rows reconciled exactly to the inning history for all four players in
the inspected response. See the consolidated
[match-stats endpoint review](./acl-api-endpoints/match-stats.md).

## Review priorities exposed by this dictionary

1. Capture populated responses for player profile, player events, event standings, all
   Swiss endpoints, swap up-next, and every schedule list.
2. Confirm whether `inning` and `round` are always equivalent.
3. Confirm across other match formats that inning summaries remain cumulative
   cancellation-scoring match scores.
4. Document scope and inclusion rules for every ACL-reported PPR/DPR value.
5. Compare alias fields for equality across a representative corpus.
6. Classify personally identifiable and financial fields before raw-payload retention rules
   are finalized.
7. Record response variants for singles, doubles, swap, Swiss/Rounders, bracket play, live
   matches, completed matches, and 401/403 match-stat responses.
