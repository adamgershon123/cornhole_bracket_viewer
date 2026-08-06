# ACL Bracket Data Endpoint Review

Endpoint:

```text
GET /api/v1/bracket-data/{event_id}
```

Validated example:

```text
GET /api/v1/bracket-data/216491
```

Review status: **Successful populated unauthenticated response confirmed**

## Response envelope

| Variable | Observed value | Meaning |
|---|---|---|
| `status` | `"OK"` | ACL application status |
| `message` | `"Successfully Get Bracket Data"` | Result message |
| `eventInfo` | object | Event metadata |
| `bracketDetails` | 61 rows | Bracket position/participant records |
| `rosterDetails` | object | Event roster summary |
| `playoffsTypeID` | `2` | Playoff/bracket-type code; mapping unconfirmed |
| `cachedData` | `false` | ACL cache indicator |

## Event summary

| Variable | Sanitized value | Review note |
|---|---|---|
| Event ID | `216491` | IDs repeated through aliases |
| Event date | `"2025-09-01"` | Event year/bucket is 2025/bucket 10 |
| Event name | `"Lakeview Bar and Grill Labor Day Blind Draw Upper Bracket"` | Public event name |
| `leagueDay` | `"Sun"` | 2025-09-01 was Monday; source day/date conflict |
| `matchType` | `"D"` | Doubles |
| `bracketType` | `"D"` | Double-elimination appears plausible; confirm code |
| `teamCount` | `16` | Matches `rosterDetails.team_count` |
| `bucketID`, `eventBucketID` | `10`, `10` | Prior ACL bucket compared with current bucket 11 |
| Venue/address/admin fields | Visibly redacted where sensitive | Same event-info schema as `/events/{event_id}` |

The event object includes additional financial fields not present in the earlier event
sample, including entry-fee collection, payout, ACL fee, director fee/revenue, and event
payment fields. These should not be normalized into prediction data.

## Bracket row model

`bracketDetails[]` is not one row per match. It is primarily one row per bracket position
or participating side.

Observed structure:

| Measure | Result |
|---|---:|
| Bracket rows | 61 |
| Unique `bracketmatchid` values | 31 |
| Rows with scores/player/game data | 60 |
| Unique completed games represented | 30 |
| Player rows across positions | 120 |
| Unique player IDs | 32 |

Thirty populated matches appear twice—once for each top/bottom position. A 61st champion
placeholder row has no team, score, players, or game result.

Normalization must group populated rows by `(event ID, bracketmatchid)` before creating a
match. It must not create one match per `bracketDetails` row.

## Bracket-position fields

| Variable | Example/shape | Likely meaning |
|---|---|---|
| `roundid` | `"8"` on champion row; `null` on 60 match rows | Not a reliable round key in this response |
| `rounddesc` | `"Round 1"`, `"Round 3"`, `"Semi-Finals"`, `"FINAL"`, `"Champion"` | Human-readable bracket stage |
| `forfeit` | `false` on all 61 rows | Forfeit flag |
| `bracketside` | `"W"` or `"L"` | Winner/loser bracket side, not match winner |
| `bracketmatchid` | Mixed string/number values | Match identifier; normalize type carefully |
| `bracketpos` | Values such as `"M10T"` and `"M10B"` | Match/top-bottom position encoding |
| `courtid` | Positive court ID or `-1` | `-1` appears on unplayed/synthetic/placeholder positions |
| `bracketteamid` | Team ID or empty string | Team identifier; empty on champion placeholder |
| `bracketteamname` | Team label or empty string | Team display name |
| `matchStatusID` | `5` on all 60 populated rows | Completed status in this sample |
| `matchSortPos` | `1` or `2` | Side/order within match; appears top/bottom-related |

## Score and game-result fields

### `scores[]`

| Variable | Likely meaning |
|---|---|
| `gameno` | Game number |
| `leagueid` | Event ID |
| `matchid` | Match ID |
| `scorehome`, `scoreaway` | Home/away final game scores |
| `weekid` | Week/session grouping; exact meaning unconfirmed |

### `gameResults[]`

| Variable | Likely meaning |
|---|---|
| `leagueID`, `matchID`, `gameID` | Event/match/game identifiers |
| `scoreHome`, `scoreAway` | Home/away scores |
| `matchStatusID` | Game/match status |
| `matchStartTime`, `matchEndTime` | Source match timestamps; reliability is poor in this sample |

The same `scores[]` and `gameResults[]` record is repeated on both participant-position rows
for a match. Normalize it once per `(event, match, game)`.

## Player and team fields

Each populated position contains `player_info[]`, with two players because this sample is a
doubles event.

| Variable | Likely meaning |
|---|---|
| `teamid`, `teamname` | Team/entry identifier and label |
| `playerid` | ACL player identifier |
| `firstname`, `lastname`, `playernickname` | Player identity fields |
| `photoimage` | Player image URL or null |

Names and image values are redacted in review fixtures. Player IDs are retained for
relational testing.

## Synthetic players and byes

The response contains synthetic participant records:

- first names such as `"Bye"` and `"Ghost"`;
- last names such as `"User 128"`;
- player IDs including `9872`, `9873`, `9874`, `9875`, and `29683`.

Observed totals:

| Measure | Result |
|---|---:|
| Synthetic player appearances | 10 |
| Unique synthetic player IDs | 5 |

These must not automatically become normal real-player profiles. The ingestion model needs
an explicit participant classification such as `REAL_PLAYER`, `BYE_PLACEHOLDER`,
`GHOST_PLACEHOLDER`, or `UNKNOWN_SYNTHETIC`.

Do not infer synthetic status solely from one hard-coded ID list; retain source labels and
support reviewed classification rules.

## Timestamp data-quality findings

The source timestamps cannot be trusted as event-time facts without validation:

| Finding | Observed result |
|---|---:|
| Populated game-result rows | 60 |
| Rows where start equals end exactly | 60 |
| Unique games | 30 |
| Game-result rows dated in 2026 for a 2025 event | 8 |
| Unique future-dated games | 4 |

Most competitive games show 2025-09-01 timestamps, but four games involving bye/placeholder
positions show `2026-07-16` timestamps—more than ten months after the event. Those values
must not be used as match start/end times or chronological backtest cutoffs.

Even the apparently plausible rows have identical start and end timestamps, so these fields
may represent a save/update timestamp rather than actual game duration.

Recommended timestamp status:

- `SOURCE_TIMESTAMP_UNVERIFIED` by default;
- `SOURCE_TIMESTAMP_CONFLICT` when outside event bounds;
- use verified event date plus deterministic sequence only when actual match time is
  unavailable;
- never allow future-dated placeholder timestamps to reorder historical replay.

## Other data-quality findings

- `leagueDay: "Sun"` conflicts with the Monday event date.
- `roundid` is null on all 60 populated participant rows.
- `bracketmatchid` changes JSON type between rows.
- `courtid: -1` appears nine times.
- `forfeit` is false even on synthetic bye/ghost matchups.
- Final scores may exceed 21, which is valid-looking cornhole behavior and must not be
  constrained to exactly 21.
- Home/away is encoded in scores, while top/bottom is encoded by bracket position. They
  should not be assumed to be the same axis.
- The response includes duplicate player/team/score data by design of its position-row
  structure.

## Normalization rules supported by this response

1. Preserve the complete raw response first.
2. Create one event from `eventInfo`.
3. Group `bracketDetails` by normalized `bracketmatchid`.
4. Treat `M{match}T` and `M{match}B` as two bracket positions/sides.
5. Create one game per unique `(leagueID, matchID, gameID)`.
6. Deduplicate repeated scores/game results across positions.
7. Create match participants from each position's `player_info[]`.
8. Preserve top/bottom, home/away, and winner/loser-bracket concepts separately.
9. Classify synthetic participants explicitly.
10. Quarantine or flag conflicting/unverified timestamps.
11. Permit empty champion/advance placeholder rows without fabricating a match result.

## Visible redaction summary

| JSON path | Marker | Reason |
|---|---|---|
| `eventInfo` address and coordinate fields | Address/location markers | Exact venue details unnecessary for schema review |
| `eventInfo` administrator names/emails | Name/email markers | Personal contact data |
| `bracketDetails[].player_info[]` names/nicknames | `[REDACTED_PLAYER_NAME]` | Player identity unnecessary for structural review |
| `bracketDetails[].player_info[].photoimage` | `[REDACTED_PROFILE_IMAGE]` | Player-specific image URL |

## Required follow-up tests

1. Singles bracket response.
2. Active/incomplete bracket response.
3. Multi-game match response.
4. Real forfeit response.
5. Bracket reset or double-final response.
6. Swiss/Rounders response comparison.
7. Determine official meanings of bracket-side, bracket-position, and playoff-type codes.
8. Compare bracket timestamps with `match-stats` and live schedule timestamps.
9. Determine whether synthetic IDs and labels are stable across events.
