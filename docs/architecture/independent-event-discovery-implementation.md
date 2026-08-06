# Independent ACL event discovery

## Validated request

```text
POST https://api.iplayacl.com/api/v1/events-radius?bucket_id=11
```

The request was reproduced directly, without the ACL website or its service
worker, using the supplied JSON search payload and `x-app-version: 14.1.0`.

## Live validation result — 2026-07-25

- ACL reported 202 rows.
- 198 normal events with an `eventID` were indexed.
- Four registration/master rows were excluded from matchup discovery.
- Indexed dates ranged from 2026-07-25 through 2026-08-01.
- Provisional routing produced:
  - 174 bracket candidates;
  - 15 Swap candidates; and
  - 9 Swiss/Rounders candidates.

Format labels are discovery hints, not authoritative classifications. Schedule
and bracket endpoint responses remain the authority for actual matchup shape.

## Personal-data handling

The live response contained `playerEmail` once in every returned row. All 202
values were replaced with `[REDACTED_PERSONAL_DATA]` before the response entered
the provenance store. Email is not represented in the normalized
`discovered_events` table.

The search audit record explicitly stores the number of redacted fields, making
the redaction location and volume reviewable.

## Stored event fields

The normalized index retains only operational discovery data:

- event ID, name, date, and advertised time;
- active status and event/list type;
- singles/doubles, bracket type, and blind-draw flag;
- location name, city, state, country, and coordinates;
- returned distance; and
- provisional format candidate and its classification basis.

Event timezones remain unresolved until verified. The platform does not infer
them from state or city labels.
