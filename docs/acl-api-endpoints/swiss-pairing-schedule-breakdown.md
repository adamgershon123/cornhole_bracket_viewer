# `GET /api/v1/swiss-pairing-schedule-breakdown/{event_id}`

Review date: 2026-07-25  
Authentication: none in the successful test  
Validated response: completed Rounders doubles event `248002`

## Response summary

| JSON path | Observed value | Interpretation |
|---|---:|---|
| `status` | `"OK"` | Request succeeded. |
| `cachedData` | `false` | ACL reported a non-cached response. |
| `data.overAllScheduleCount` | `75` | Total schedule records. |
| `data.overAllSchedule` | 75 rows | All five rounds of matches. |
| `data.completedMatchListCount` | `75` | Completed-match count. |
| `data.completedMatchList` | 75 rows | Byte-for-byte equivalent to `overAllSchedule` in this capture. |
| `data.inProgressMatchListCount` | `0` | No live matches in the completed event. |
| `data.availableMatchListCount` | `0` | No matches awaiting play. |

Do not concatenate `overAllSchedule` and `completedMatchList`: in this completed response
they contain the same 75 matches and would double-count every result.

## Tournament structure established by the schedule

- 30 unique fixed teams.
- Two players on every team.
- Five rounds.
- 15 matches in each round.
- Every team appeared exactly once per round and five times overall.
- Match IDs were 1 through 75.
- Every match had `matchStatusID: 5` and `matchStatus: "Completed"`.
- Match start timestamps ranged from `2026-06-13 10:08:09` to
  `2026-06-13 12:07:26`.
- `matchEndTime` was null for all 75 completed matches, so it is not a reliable completion
  timestamp in this response.

This demonstrates a major difference from Swap: Rounders used fixed two-player teams across
five Swiss rounds. The schedule itself contains the opponent pairing for every round.

## Match row

| Variable | Likely meaning | Validation/use guidance |
|---|---|---|
| `adminID`, `leagueID`, `matchID` | Administrator, event, and match identifiers. | `leagueID + matchID` identifies the match within this capture. |
| `roundID`, `round` | Swiss round identifiers. | Equal in all inspected examples; retain both raw. |
| `homeTeamID`, `awayTeamID` | Competing fixed-team IDs. | Team/opponent join keys. |
| `homeColor`, `awayColor` | UI display colors. | Display-only. |
| `matchDetailsRecordCount` | Likely underlying detail/inning-record count. | Variable across matches; compare with match-stats before assigning exact semantics. |
| `matchStatusID`, `matchStatus` | Match status code and description. | `5`/`Completed` in every row. |
| `matchStartTime`, `matchEndTime` | Match timestamps. | Start was populated; end was null even for every completed match. |
| `courtID` | Court assignment. | Operational and potentially useful for live state. |
| `loading` | Client/loading state flag. | False in every observed completed row; likely presentation-oriented. |
| `home`, `away` | Compact team result objects. | Contains team ID, score, and standings point. |
| `homeScore`, `awayScore` | Match scores duplicated outside compact objects. | Exactly matched `home.score`/`away.score` for all 75 matches. |
| `homeTeam[]`, `awayTeam[]` | Two player/profile rows for each fixed team. | Repeated in every match involving the team. |

For every match, winner points were internally consistent: one side received `1`, the other
received `0`. Scores—not the points flag alone—should remain the authoritative game result
input, with status validation.

## Embedded player row

The embedded player object includes:

- event, team, and player IDs;
- player name, email, phone, city/state, and photo;
- skill level and conference;
- `playerPPRPlayerInfo`, `playerPPR`, and `playerCPI`; and
- `cPITimeStamp`.

These are repeated profile/stat snapshots, not match-performance statistics. The event
occurred on 2026-06-13, but all observed CPI timestamps were on 2026-07-22. Therefore the
CPI and PPR values cannot be treated as pre-match or event-time ratings. Store them only as
ACL-supplied snapshots with their timestamps and collection time.

## Prediction-engine use

This endpoint is a strong source for:

- Rounders match chronology;
- fixed team membership;
- opponent pairings by round;
- completed scores and win/loss results;
- court assignments; and
- finding match IDs for subsequent match-stat requests.

Use `match-stats` to obtain player game/inning performance. Do not derive match PPR from the
profile PPR fields embedded here.

## Privacy/redaction

All 60 unique players had populated email and phone fields. The response also exposed names,
city/state, photo URLs, and `adminID`. Published fixtures must use `[REDACTED_EMAIL]`,
`[REDACTED_PHONE]`, and `[REDACTED_PLAYER_NAME]`, and omit unnecessary location, photo, and
administrator values.
