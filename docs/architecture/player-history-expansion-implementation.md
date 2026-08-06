# Player-history expansion

## Purpose

Players discovered in live or upcoming matchups are placed in a durable,
deduplicated history queue. This targets collection effort at the players whose
missing data is actively causing prediction abstentions.

## Queue behavior

- Player ID is the queue identity.
- Multiple event/match discovery reasons accumulate without creating duplicate
  work.
- Ready pregame matchups receive higher priority than already-live matchups.
- Failed or partial players can be requeued.
- Before/after round and event coverage is recorded.
- ACL 401/403 match-stat gaps are counted separately.
- Cached completed event and game data is reused by the existing collector.

## First live batch — event 254155

Eight unique players were queued from the two live Swap matches. A measured
two-player batch completed successfully:

| Player | Rounds before | Rounds after | Events after | Auth-blocked games |
|---|---:|---:|---:|---:|
| 210823 | 0 | 515 | 24 | 0 |
| 212085 | 49 | 779 | 45 | 0 |

The first batch added or confirmed 1,294 player-round records across the two
players. Six event players remain pending. The batch required approximately
nine minutes, so subsequent processing should remain bounded and resumable
rather than attempting every discovered player in one request.

## Readiness threshold

The current queue marks a player complete at 20 historical rounds. This is a
collection-readiness threshold, not a claim that 20 rounds provides high model
confidence. The prediction feature and evidence-tier safeguards continue to
control whether a matchup is scored.
