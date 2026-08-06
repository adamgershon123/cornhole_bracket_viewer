# `GET /api/v1/match-stats/eventid/{event_id}/matchid/{match_id}/gameid/{game_id}`

Review date: 2026-07-25  
Authentication in current code: none; some records return HTTP 401/403  
Validated response: event `216491`, match `10`, game `1`

## Response grain

This response represents one game within one match. The inspected game was completed
doubles play with four players, two players per team, and 12 innings/rounds.

| Structure | Rows | Grain |
|---|---:|---|
| Match header | 1 | Game identity, state, teams, court, and final score |
| `event_match_details[]` | 4 | One aggregate row per player for this game |
| `event_team_details[]` | 4 | One player-to-team membership row |
| `event_match_inning_history[]` | 24 | One player performance per inning |
| `event_match_inning_summary[]` | 12 | One cumulative game-score state per inning |

## Internal validation

For every player, summing the inning-history records exactly reproduced the corresponding
aggregate row:

- six played innings;
- 24 bags thrown;
- hole, board, and off-board totals;
- total gross points; and
- reported PPR after rounding (`totalpts / rounds`).

Every inning-history row contained four bags:
`bagsin + bagson + bagsoff = 4`. The last inning summary was home `15`, away `21`, exactly
matching the header score. The inning summaries therefore behave as cumulative
cancellation-scoring game scores in this sample, not gross player points.

The players' gross points summed to 70 for the home team and 76 for the away team. Those
values should not be compared directly with the 15–21 cancellation score.

## Important interpretation rules

- `event_match_details[].ptsperrnd` is an ACL-reported **game PPR** and is independently
  calculable from this payload.
- `event_match_details[].opponentpts` is the gross total for the opposing player faced in
  the same alternating set of doubles innings, not the opposing team's full gross total.
- `diffperrnd` equals player PPR minus that opposing player's PPR in this sample.
- `playedinnings` and `rounds` are equal here, but other match formats still need testing.
- `winningTeam` was `-1` even though away team ID `4` won 21–15. Treat `-1` as
  unknown/unpopulated and derive the winner from the completed score, with match status
  validation, rather than trusting this field.
- Identifier types vary: `eventID`, `matchID`, and `gameID` are strings in this response,
  while team and player IDs are numbers. Normalize identifiers at ingestion.
- Several statistics are numeric strings (`scoringavg`, `scoringpct`, `avgbagsin`,
  `avgbagson`) while related fields are numeric. Parse deliberately and retain the raw value.

## Prediction-engine value

This is the best validated public source captured so far for player performance at the
game and inning level. It supports:

- internally calculated game PPR;
- bag-placement rates;
- four-bagger rates;
- opponent-adjusted features;
- player-versus-player inning assignments; and
- match-state reconstruction.

It does not supply CPI. CPI must remain an ACL-supplied snapshot from an endpoint that
explicitly returns CPI.

Retain both values when comparing season statistics:

1. ACL-provided season/profile PPR, with source and collection timestamp; and
2. internally calculated PPR from match-stat history, with the included game population and
   calculation version.

Differences may reflect unavailable games, 401/403 responses, season boundaries, format
filters, corrections, or ACL's undisclosed inclusion rules. The platform may identify those
possible causes but must not claim a certain cause without evidence.

## Authentication and missingness

The code calls this endpoint without credentials. Some event/match/game records return
401/403, and cookie fallback is disabled, so those records are skipped. Any aggregate
calculated from downloaded match data must therefore carry coverage metadata such as:

- expected games;
- successfully retrieved games;
- authorization-blocked games;
- other failed games; and
- earliest/latest included event dates.

Without coverage metadata, internal season PPR can look authoritative while representing
only a partial sample.

## Privacy/redaction

The payload includes player names, nicknames, city/state, and photo URLs, plus an
administrator ID. Published samples replace names with `[REDACTED_PLAYER_NAME]` and omit
unnecessary location, photo, nickname, and administrator values. Player IDs are retained
where needed for reproducible joins.
