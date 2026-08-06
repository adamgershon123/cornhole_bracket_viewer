# Public Event CPI/PPR History Test — 2026-07-25

## Question

When an old event's public roster is fetched today, does it return:

1. the player's CPI/PPR as of the event;
2. the player's current CPI/PPR; or
3. some other cached player-stat snapshot?

## Method

- Player: ACL ID `142125`
- Event discovery:
  `GET /api/v1/player-events-grouped/142125?bucket_id=11&eventStatus=COMPLETED`
- Tested public roster:
  `GET /api/v1/swap-schedule-breakdown/{event_id}`
- Authentication: none
- Extracted fields only:
  `playerCPI`, `cPITimeStamp`, `playerPPR`, and `playerPPRPlayerInfo`
- Contact, identity, and other personal fields were not output.

The authenticated player-profile response supplied by the user reported:

```text
playerCPI: 6.35
cPITimeStamp: 2026-07-22 13:29:30
playerPPR: 7.39
playerPPRPlayerInfo: 7.4153
```

## Results

| Event ID | Event date | Returned CPI | Returned CPI timestamp | Returned PPR | PPR player info |
|---:|---|---:|---|---:|---:|
| 216959 | 2025-09-10 | 6.24 | 2025-10-02 05:28:11 | 7.36 | 7.4153 |
| 217035 | 2025-09-24 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 217461 | 2025-09-26 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 219227 | 2025-10-08 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 220073 | 2025-10-15 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 246358 | 2026-05-20 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 247523 | 2026-05-25 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 247818 | 2026-05-27 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 249170 | 2026-06-03 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 247728 | 2026-06-05 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 249868 | 2026-06-10 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 250547 | 2026-06-24 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 252025 | 2026-07-01 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 250766 | 2026-07-01 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 252646 | 2026-07-08 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 252116 | 2026-07-15 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |
| 254035 | 2026-07-24 | 6.35 | 2026-07-22 13:29:30 | 7.39 | 7.4153 |

## Findings

1. Public old-event rosters do **not** reliably preserve event-time CPI or PPR.
2. Sixteen tested events returned the same CPI/PPR values and CPI timestamp as the supplied
   current authenticated profile, including events many months before that timestamp.
3. Event `216959` returned an older CPI/PPR snapshot, proving old events are not uniformly
   joined to the current profile either.
4. Even the older snapshot is not event-time: the event occurred on 2025-09-10, while its
   CPI timestamp is 2025-10-02. Using it for a prediction before or at that event would be
   future leakage.
5. `playerPPRPlayerInfo` remained `7.4153` in both the old and current-like rows, while
   `playerPPR` changed. These fields cannot be treated as equivalent without an ACL
   definition.

## Best-supported interpretation

The public event roster appears to contain a player-stat snapshot associated with ACL's
event cache or a later refresh. That snapshot may be old or current, but it is not reliably
anchored to the event date.

This is an inference from observed results, not a confirmed ACL implementation detail.

The older event `216959` may be an anomaly or may retain a prior-season/bucket snapshot.
The event date (2025-09-10), CPI timestamp (2025-10-02), and later current-like values are
consistent with several possible cache/bucket behaviors. A single observation cannot
distinguish among them.

A subsequent populated `event-standings` response for event `216491` showed the same
pattern across an entire field: the event was on 2025-09-01, while 26 of 28 player rows
carried CPI timestamps on 2025-10-02. Player `142125` carried the same CPI `6.24` and PPR
`7.36` seen in the older public-event test. This makes an isolated one-player anomaly less
likely, but it still does not distinguish a prior-bucket snapshot from a post-event cache
refresh.

## Rules resulting from this test

- Do not use an event roster's CPI/PPR merely because the event predates a prediction.
- Eligibility for backtesting is controlled by `cPITimeStamp` when present, not event date.
- If CPI timestamp is after the prediction cutoff, exclude the CPI observation.
- If CPI timestamp is absent, the observation is known only at retrieval time and is not
  eligible for earlier historical replay.
- PPR without a source effective timestamp must be treated as known at retrieval time only,
  unless another ACL contract supplies a valid historical window.
- Public event rows remain useful for collecting ACL-reported observations and current
  production features, but not as automatic historical snapshots.

## Follow-up tests

1. Re-fetch the same event IDs later and detect whether values/timestamps change.
2. Test additional players and event formats.
3. Compare `swap-standings`, `swap-schedule-breakdown`, and `swap-up-next` for the same event
   at the same time.
4. Test whether ACL provides a CPI history or standings-snapshot endpoint.
5. Audit `player-compare-stats` buckets for genuinely historical season aggregates.
6. Repeat the boundary test across multiple players who participated before and after the
   2025–2026 bucket transition.
