# Swiss/Rounders standings and up-next endpoints

Review date: 2026-07-25  
Authentication: none in the successful tests  
Validated event: completed Rounders doubles event `248002`

## `GET /api/v1/swiss-pairing-standings/{event_id}?roundID=0`

The endpoint returned 30 team-level rows—one for every fixed team in the five-round
schedule.

| Variable | Likely meaning | Validation/use guidance |
|---|---|---|
| `leagueID` | Event identifier. | `248002` in every inspected row. |
| `teamID`, `id` | Team identifiers. | Equal in the inspected response; retain both raw. |
| `seed` | Initial or assigned seed. | Zero in observed examples; semantics need confirmation. |
| `disbanded` | Team-disbanded flag. | Operational eligibility metadata. |
| `droppedOut` | Team withdrawal flag. | Operational eligibility metadata. |
| `teamPlayerList[]` | Two embedded player/profile rows. | Fixed team membership plus ACL profile-stat snapshots. |
| `wins`, `losses` | Team match record. | Exactly reproduced from the schedule for all 30 teams. |
| `tiebreaker` | ACL-calculated Swiss tiebreak value. | Preserve as ACL authoritative; formula is not established. |
| `teamDifferentialPoints` | Total score differential. | Exactly equals points scored minus points allowed from the schedule. |
| `teamTotalPoints` | Total match points scored. | Exactly reproduced from the schedule. |
| `isNegativeDiff` | Sign flag for differential. | Consistent with observed positive/negative values. |
| `rank` | ACL final/display rank. | Rows were ordered 1 through 30. |

Wins summed to 75 and losses summed to 75, matching the 75 completed matches. Ranking is
clearly driven first by wins in this capture, and differential commonly orders teams with
the same record. Exact tied cases and the role/formula of `tiebreaker` remain unknown. Use
ACL's supplied `rank` as official; label any reconstructed rank as calculated.

The 30 teams contained 60 unique players, exactly two per team. Embedded player rows use the
same identity, contact, location, skill, conference, PPR, CPI, and CPI timestamp structure
seen in the Swiss schedule. These are later profile snapshots: the event occurred on
2026-06-13 while the CPI timestamps were dated 2026-07-22.

## `GET /api/v1/swiss-pairing-up-next-players-list/{event_id}?roundID=0`

| Variable | Observed value | Interpretation |
|---|---:|---|
| `status` | `"OK"` | Endpoint and URL are valid without authentication. |
| `message` | `"Successfull Round Robin Get Up Next Player List"` | ACL labels the operation Round Robin despite the Swiss URL. |
| `data` | `[]` | No queued players after event completion. |
| `upNextPlayerCount` | `0` | Agrees with the empty array. |

This validates the endpoint but not a populated item schema. Capture during an active
Rounders event is still required.

## Prediction-engine use

- Use standings for ACL-authoritative team rank and ACL tiebreaker.
- Recalculate wins, losses, scored points, and differential from the schedule for validation
  and transparent modeling features.
- Keep official ACL rank and any calculated rank separate with explicit source labels.
- Do not use embedded profile PPR/CPI as ratings at the time of these June matches.

## Privacy/redaction

All 60 embedded player rows contained email and phone values. Names, city/state, photo URLs,
and profile details were also returned. Documentation replaces contact and identity values
with `[REDACTED_EMAIL]`, `[REDACTED_PHONE]`, and `[REDACTED_PLAYER_NAME]` and omits
unnecessary location/photo values.
