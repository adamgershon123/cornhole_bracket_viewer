# Upcoming-match discovery implementation

## Outcome

ACL schedule responses can now be normalized into auditable matchup candidates
and passed automatically to the shadow prediction workflow.

Supported public schedule sources:

- `swiss-pairing-schedule-breakdown/{event_id}`
- `swap-schedule-breakdown/{event_id}`

## Candidate requirements

A matchup is ready only when:

- it is not marked complete;
- both sides contain ACL player IDs;
- it has a scheduled start time;
- the timestamp includes an offset, or the caller supplies a verified IANA
  source timezone; and
- its start is still in the future.

The platform does not infer an event timezone from city, state, or server time.
Rows that cannot meet these requirements are retained with a specific discovery
issue such as `MISSING_SOURCE_TIMEZONE`, `MISSING_SCHEDULED_START`, or
`INCOMPLETE_SIDE_IDENTITIES`.

## Operation

The schedule fetch-and-index operation:

1. Retrieves the appropriate unauthenticated ACL schedule endpoint.
2. Preserves the response through the existing provenance/cache layer.
3. Deduplicates repeated schedule lists by match ID.
4. Stores normalized candidates and their source hashes.
5. Finds ready matchups within the configured look-ahead window.
6. Creates one pregame shadow prediction per event/match/model.

Completed Swiss responses may repeat the same matches in `overAllSchedule` and
`completedMatchList`; the normalizer deliberately selects one schedule list
rather than concatenating them.

## Current local status

At implementation time the local season database contained zero upcoming
candidate matchups and therefore zero shadow predictions. The pipeline is ready,
but it requires an active/upcoming ACL event ID, its format, and a verified event
timezone to begin collecting live observations.
