# ACL Event Details Endpoint Review

Endpoint:

```text
GET /api/v1/events/{event_id}
```

Validated example:

```text
GET /api/v1/events/247734
```

Review status: **Successful populated unauthenticated response confirmed**

## Response envelope

| Variable | Observed value | Meaning |
|---|---|---|
| `status` | `"OK"` | ACL application status |
| `message` | `"Successfully GET Event Details for Event 247734"` | Result message |
| `data` | object | Event-details record |

## Event identity and scheduling

| Variable(s) | Sanitized sample | Likely meaning |
|---|---|---|
| `leagueYear`, `leagueyear`, `eventYear` | `2026` | Year aliases; exact duplicate casing confirmed |
| `leagueSessionID`, `leaguesessionid` | `1` | Session/season segment aliases |
| `leagueID`, `leagueid`, `eventID` | `247734` | Event identifier aliases |
| `leaguename`, `leagueName`, `eventName` | `"ACL Friday Night Swap Club 52 - 7/17/2026"` | Event-name aliases |
| `leagueDay` | `"Thu"` | Configured day label; note event date was a Friday, so semantics/data quality need review |
| `leagueTime`, `starttime` | `"6:00 PM"` | Start-time aliases; timezone absent |
| `startdate`, `leaguestartdate`, `leagueStartDate` | `"2026-07-17"` | Start-date aliases |
| `leagueStatus` | `"C"` | Appears completed; code mapping needs confirmation |
| `bracketStarted` | `true` | Bracket-started flag |

## Event classification and format

| Variable(s) | Observed value | Likely meaning |
|---|---|---|
| `leagueTypeCOBS` | `"Y"` | Internal ACL classification; meaning unknown |
| `tourID` | `-1` | Likely “no tour” sentinel; confirm |
| `eventtype`, `eventType` | `"L"` | Event-type code |
| `eventsubtype`, `eventSubType` | `"O"` | Event-subtype code |
| `eventGenderType` | `"B"` | Gender/category code |
| `eventBaggerLevel` | `"-1"` | Player-level code encoded as string |
| `eventPlayerType` | `"E"` | Player/entry-type code |
| `matchtype`, `matchType` | `"D"` | Appears doubles |
| `brackettype`, `bracketType` | `"P"` | Appears swap/pool phase; confirm |
| `winnerBracketType`, `loserBracketType` | `0`, `0` | Bracket configuration codes |
| `teamTourney` | `"N"` | String flag |
| `leagueBlindDraw`, `blindDraw` | `1`, `1` | Blind-draw aliases |
| `eventGroupID`, `eventGroupSubID`, `eventGroupDesc` | `1`, `"L"`, `"ACL"` | Event grouping |
| `eventGroupCollegeName` | `"undefined"` | String sentinel, not JSON null |
| `eventGroupCollegeType` | `""` | Empty-string value |
| `eventListType` | `"bracket"` | Event listing/type label |
| `superEventID`, `superEventName`, `superEventStatus` | `null` | No parent/super-event in sample |

## Courts, rounds, and scoring

| Variable | Observed value | Likely meaning |
|---|---|---|
| `courtTotal` | `1` | Configured court count |
| `courtTotalType` | `"R"` | Court-allocation type code |
| `courtTotalDetails` | `"1,2,3,4,5,6,7,8,9,10"` | Court detail string; conflicts with `courtTotal: 1`, so meaning needs review |
| `liveRoundStats` | `"0"` | String-encoded live-stat setting |
| `eventScoringType` | `"ANY"` | Scoring configuration |
| `roundLimit` | `14` | Round limit |
| `roundLimitBracket` | `4` | Bracket round-limit setting |
| `playerPoolSize` | `4` | Pool size |
| `redZoneActiveFlag` | `0` | RedZone feature flag |
| `autoAssignCourt` | `"Y"` | Auto-assignment flag |
| `reservedCourtID` | `""` | No reserved court |
| `deviceDisplayMode` | `"ROUND"` | Scoring/display mode |
| `useABGrouping` | `0` | A/B grouping flag |

## Registration, fees, and event operations

| Variable/group | Observed example | Likely meaning |
|---|---|---|
| `preRegistrationOpen`, `leaguePreRegistrationOpen` | `"Y"`, `"Y"` | Pre-registration flags |
| `eventFee` | `20` | Event fee; currency inferred from context but not returned here |
| `leagueNotes` | `"null"` | String sentinel, not JSON null |
| `entryFeePerPersonGoldPlatinum` | `0` | Membership-specific fee |
| `additionalMoneyForPayouts` | `0` | Added payout money |
| `addDirectorNonMemberFeeToPayout` | `"0"` | String-encoded payout setting |
| `directorRevenue` | `null` | Director revenue |
| `holdMySpotStatus` | `0` | Registration feature status |
| `holdMySpotMaxTeamCount`, `holdMySpotPaymentOptions` | `null` | Registration configuration absent |
| `sendCourtSMS`, `sendScoreSMS` | `"Y"`, `"Y"` | SMS settings |
| `leagueESPNFlag`, `espnFlag` | `"N"`, `"N"` | ESPN/broadcast flags |
| `fantasyExternalID` | `-1` | Likely no fantasy integration |
| `fantasyExternalEventInfo` | `null` | No fantasy metadata |
| `eventCharityFlag`, `eventCharityAmountRaised` | `"N"`, `0` | Charity settings |
| `matchPlayFormat`, `matchPlayBracketFormat` | `"B"`, `"D"` | Match-play format codes |
| Match-play spot counts | `0` | No configured match-play spots |
| `aclLite` | `0` | ACL Lite flag |
| `indoor` | `null` | Indoor/outdoor status not supplied |
| `teamCount` | `0` | Zero despite populated event; definition/timing needs review |

## Venue data

| Variable/group | Sanitized sample | Likely meaning |
|---|---|---|
| `leagueLocationID` | `6125` | ACL location identifier |
| `leagueLocationName`, `locationName` | `"Club 52"` | Venue-name aliases |
| `leagueAddress`, `locationAddress` | `[REDACTED_ADDRESS]` | Venue street-address aliases |
| `locationCity`, `locationState`, `locationZip` | `"Melbourne"`, `"FL"`, `[REDACTED_ADDRESS]` | Venue geographic fields |
| `locationLat`, `locationLng` | `[REDACTED_PRECISE_LOCATION]` | Venue coordinates |
| `countryCode` | `"US"` | Country code |
| `leaguePhone`, `leagueEmailAddress` | Empty strings | Venue contact fields empty in sample |
| `leagueWebsite` | Public venue website returned | Venue website |
| `leagueImage` | Public venue image URL returned | Venue image |
| `leagueMiscDetails` | `""` | Additional venue details |

Venue information may be appropriate for event presentation, but exact address and
coordinates should be excluded from generic analytics fixtures unless needed for an
approved geographic feature.

## Administrator data

| Variable/group | Sanitized sample | Likely meaning |
|---|---|---|
| `fldPlayerID`, `eventAdminID`, `adminID` | Same integer in sample | Administrator/player ID aliases |
| Player/admin name fields | `[REDACTED_PLAYER_NAME]` | Administrator identity |
| `playerEmail`, `adminEmail` | `[REDACTED_EMAIL]` | Administrator email aliases |

Administrator identity/contact data is not required for prediction analytics and should be
excluded from normalized prediction data.

## Membership bucket

| Variable | Observed value | Likely meaning |
|---|---|---|
| `eventBucketID`, `bucketID` | `11`, `11` | Event season/statistical bucket aliases |

This is important for joining event statistics to the correct ACL season/bucket.

## Confirmed data-quality behaviors

- Exact duplicate aliases with different capitalization occur in one response.
- Boolean-like values use booleans, integers, and `"Y"`/`"N"` strings.
- Missing values use JSON `null`, empty strings, and sentinel strings such as `"null"` and
  `"undefined"`.
- IDs and enum-like values may use negative sentinels such as `-1`.
- `leagueDay: "Thu"` does not appear to match `startdate: "2026-07-17"` (Friday).
- `courtTotal: 1` coexists with ten comma-separated values in `courtTotalDetails`.
- `teamCount: 0` does not necessarily mean the event had no players or matches.

These values must be preserved raw. Normalization should map them only through documented,
tested rules and retain the original value/provenance.

## Visible redaction summary

| JSON path | Marker | Reason |
|---|---|---|
| `data.leagueAddress`, `data.locationAddress`, `data.locationZip` | `[REDACTED_ADDRESS]` | Exact address unnecessary for response review |
| `data.locationLat`, `data.locationLng` | `[REDACTED_PRECISE_LOCATION]` | Exact coordinates unnecessary for response review |
| Player/admin name fields | `[REDACTED_PLAYER_NAME]` | Identity unnecessary for event-schema review |
| `data.playerEmail`, `data.adminEmail` | `[REDACTED_EMAIL]` | Personal contact data |

## Rounders format validation

A second successful event-details response was supplied for event `248002`, a completed
event named `East Coast Beach Baggers South - 25/26 Season Regional #9 - Rounders Doubles
BYOP`.

| Variable | Observed value | Interpretation |
|---|---:|---|
| `eventID` | `248002` | Rounders test event. |
| `bracketType`, `brackettype` | `"W"` | Confirms the application's `"W"` selector for this Rounders event. |
| `matchType`, `matchtype` | `"D"` | Doubles match format. |
| `blindDraw`, `leagueBlindDraw` | `0` | Not a blind-draw event. |
| `leagueStatus` | `"C"` | Completed. |
| `teamCount` | `30` | Thirty registered teams reported. |
| `roundLimit` | `14` | Event-level round limit. |
| `roundLimitBracket` | `5` | Bracket/phase-specific limit; exact semantics need confirmation. |
| `bucketID`, `eventBucketID` | `11` | ACL season/bucket association. |

This validates event identification only. It does not yet validate that the three
`swiss-pairing-*` URLs return successful responses or establish their response schemas.
The response also exposed organizer names and email addresses; their values are represented
as `[REDACTED_PLAYER_NAME]` and `[REDACTED_EMAIL]`.

## Follow-up validation

1. Compare active and completed events.
2. Compare singles, doubles, swap, Swiss/Rounders, and bracket events.
3. Determine enum mappings for event, subtype, gender, player, match, and bracket codes.
4. Determine why day/date, court count/details, and team count appear inconsistent.
5. Confirm whether event bucket reliably identifies the applicable ACL season.
6. Check whether administrator and venue values change when the event is re-fetched.
