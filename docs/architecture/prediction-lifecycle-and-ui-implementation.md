# Prediction lifecycle runner and operations UI

## Lifecycle cycle

The platform now exposes a bounded lifecycle operation that:

1. refreshes independent ACL event discovery;
2. polls enabled Swiss and Swap events that have verified timezones;
3. normalizes matchup candidates and queues their players;
4. creates due pregame shadow predictions;
5. fetches and normalizes completed Swap results from `swap-schedule-all`;
6. attaches outcomes to matching shadow or experimental records;
7. preserves per-event polling errors without stopping the remaining cycle; and
8. records an auditable lifecycle-run summary.

Player-history downloads remain a separate resumable queue because an individual
two-player collection batch can take several minutes. A web request does not
attempt to download every pending player's career.

## Monitoring configuration

Events are only polled when their format and timezone have been explicitly
registered. This prevents event-name heuristics or an unverified local time from
silently becoming modeling facts.

Event `254155` is registered as:

- format: `SWAP`;
- timezone: `America/Toronto`; and
- lifecycle polling: enabled.

## Operations API

- `GET /api/prediction-operations`
  returns the complete dashboard snapshot.
- `POST /api/prediction-operations/run`
  runs a bounded discovery/poll/prediction cycle.
- `POST /api/prediction-operations/monitor`
  registers or updates an event's verified format and timezone.

## User interface

The existing application now includes a **Predictions** view showing:

- discovered and monitored event counts;
- player-history queue readiness;
- live shadow coverage;
- rolling-origin reference accuracy and coverage;
- monitored event polling state;
- an event-format/timezone monitoring control;
- confidence-aware experimental performance; and
- recent lifecycle runs.

The **Run lifecycle cycle** action invokes the bounded backend cycle and then
refreshes the dashboard. The view also refreshes its read-only status every 30
seconds.

## Privacy

Lifecycle schedule fetching applies recursive personal-data redaction before new
responses enter cache or provenance storage. Player IDs and modeling statistics
remain available; email, phone, token, and cookie fields are replaced.

## Verification

- 53 backend tests pass.
- The production frontend build completes successfully.
- The Flask dashboard page and operations endpoint both return HTTP 200.
- The first lifecycle run completed successfully with no polling errors.
