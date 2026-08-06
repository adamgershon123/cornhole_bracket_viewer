# ACL API Calls Currently Used

Status: code inventory as of 2026-07-25. This records how the repository calls ACL; it does
not assert ACL's intended access-control policy.

## Authentication classification

None of the current ACL requests send authentication credentials. Specifically, the code
does not send an `Authorization` header, bearer token, API key, Basic Auth credentials,
session cookie, or authenticated `requests.Session`.

The browser-like `Origin`, `Referer`, `User-Agent`, `Accept`, and `x-app-version` headers are
request context, not authentication.

| Method | Endpoint | Current use | Credentials sent | Current classification | Review notes |
|---|---|---|---|---|---|
| GET | `/api/v1/events/{event_id}` | Event metadata | None | Unauthenticated | Falls back to `bracket-data` in `season_standings.py`. |
| GET | `/api/v1/bracket-data/{event_id}` | Event, bracket, teams, matches, and game targets | None | Unauthenticated | Called directly in multiple modules. |
| GET | `/api/v1/player-events-grouped/{player_id}?bucket_id={bucket_id}&eventStatus={status}` | Player event history for `ACTIVE` and/or `COMPLETED` | None | Unauthenticated | Uses Fanzone-style headers. |
| GET | `/api/auth/v1/players/{player_id}?dw=false&nd=true&dwt=true` | Player/account, membership, director, and proximity data | None in current code | **Session required in observed tests** | On 2026-07-25, player `142125` returned HTTP 403 with `NOT Authorized - No session found` without credentials. A user-supplied response from a valid session succeeded and exposed sensitive account/contact/location/financial data. Current implementation supplies no session, so its network refresh cannot succeed under the observed behavior. |
| POST | `/api/v1/player-compare-stats` | ACL season/career player statistics by player IDs and bucket | None | Unauthenticated | JSON body contains `playerIDs` and `bucketID`; uses App-style headers including `x-app-version`. |
| GET | `/api/v1/event-standings/{event_id}` | Event results and standings | None | Unauthenticated | May fall back to swap endpoints when no rows are returned. |
| GET | `/api/v1/swap-standings/{event_id}` | Swap-event standings | None | Unauthenticated | Used by both season ingestion and live-event views. |
| GET | `/api/v1/swap-up-next-players-list/{event_id}` | Swap-event queued/up-next players | None | Unauthenticated | Uses Fanzone/App-style browser headers depending on call site. |
| GET | `/api/v1/swap-schedule-breakdown/{event_id}` | Swap-event schedule and live match state | None | Unauthenticated | Completed-event capture returned event metadata, an empty in-progress list, and a 64-player roster; it did not return completed schedule/history keys. |
| GET | `/api/v1/swiss-pairing-schedule-breakdown/{event_id}` | Swiss/Rounders schedule and live match state | None | Unauthenticated, validated | Event `248002` returned 75 completed matches across five rounds, with 30 fixed two-player teams. |
| GET | `/api/v1/swiss-pairing-standings/{event_id}?roundID=0` | Swiss/Rounders standings | None | Unauthenticated, validated | Event `248002` returned 30 team standings; wins, losses, total points, and differential reconciled to all 75 schedule matches. |
| GET | `/api/v1/swiss-pairing-up-next-players-list/{event_id}?roundID=0` | Swiss/Rounders queued/up-next players | None | Unauthenticated, endpoint validated | Completed event `248002` returned an empty list and count zero; populated item schema remains unvalidated. |
| GET | `/api/v1/event-player-stats/{event_id}` | Event-level official player statistics | None | Unauthenticated | Uses a longer timeout and one retry on request exceptions. |
| GET | `/api/v1/match-stats/eventid/{event_id}/matchid/{match_id}/gameid/{game_id}` | Game summary, inning/round history, and player match statistics | None | **Unauthenticated, sometimes auth-blocked** | The code treats HTTP 401/403 as authentication-required and skips the game. Cookie fallback is explicitly disabled. |

## Request-header profiles

Detailed player-profile results: [`acl-api-endpoints/player-profile.md`](./acl-api-endpoints/player-profile.md).

Detailed event response: [`acl-api-endpoints/event-details.md`](./acl-api-endpoints/event-details.md).

Detailed player-aggregate response:
[`acl-api-endpoints/player-compare-stats.md`](./acl-api-endpoints/player-compare-stats.md).

Detailed bracket response:
[`acl-api-endpoints/bracket-data.md`](./acl-api-endpoints/bracket-data.md).

Detailed event-player aggregate response:
[`acl-api-endpoints/event-player-stats.md`](./acl-api-endpoints/event-player-stats.md).

Detailed event-standings response:
[`acl-api-endpoints/event-standings.md`](./acl-api-endpoints/event-standings.md).

Detailed swap-standings response:
[`acl-api-endpoints/swap-standings.md`](./acl-api-endpoints/swap-standings.md).

Detailed swap-schedule response:
[`acl-api-endpoints/swap-schedule-breakdown.md`](./acl-api-endpoints/swap-schedule-breakdown.md).

Detailed match-stat response and reconciliation:
[`acl-api-endpoints/match-stats.md`](./acl-api-endpoints/match-stats.md).

Detailed Swiss/Rounders schedule response:
[`acl-api-endpoints/swiss-pairing-schedule-breakdown.md`](./acl-api-endpoints/swiss-pairing-schedule-breakdown.md).

Detailed Swiss/Rounders standings and up-next responses:
[`acl-api-endpoints/swiss-pairing-standings.md`](./acl-api-endpoints/swiss-pairing-standings.md).

### Fanzone-style

Typically:

```text
Accept: application/json, text/plain, */*
Origin: https://fanzone.iplayacl.com
Referer: https://fanzone.iplayacl.com/
User-Agent: Mozilla/5.0
```

Some match-stat calls also send `Accept-Language` and `If-None-Match` when an ETag was
cached. None of these fields authenticate the caller.

### App-style

Typically:

```text
Accept: application/json, text/plain, */*
Origin: https://app.iplayacl.com
Referer: https://app.iplayacl.com/
User-Agent: Mozilla/5.0
```

`player-compare-stats` also sends `Content-Type: application/json` and
`x-app-version: 14.1.0`. These are not credentials.

## Duplicate call paths

Several endpoints are called from more than one module:

- `bracket-data`: `backend/app.py`, `backend/season_platform.py`, and
  `backend/season_standings.py`;
- `player-events-grouped`: all three modules above;
- `event-standings`: `backend/season_platform.py` and `backend/season_standings.py`;
- `player-compare-stats`: two production call paths in `backend/app.py` plus
  `frontend/stats_test.py`;
- `match-stats`: `backend/season_platform.py` and `backend/match_stats_downloader.py`.

The audit should test the endpoint contract once per distinct request shape/header profile,
not merely once per URL.

## Required follow-up review: match-stat authentication gaps

Do not close the ACL API review without investigating this behavior:

> `/api/v1/match-stats/eventid/{event_id}/matchid/{match_id}/gameid/{game_id}` is currently
> called without credentials. Some requests return HTTP 401 or 403. Cookie fallback is
> disabled, so those games are skipped and their round-level data is absent.

The review must determine and document:

- which events, matches, games, dates, and event types return 401/403;
- whether access behavior is stable or intermittent;
- whether the response differs by App/Fanzone headers or request origin;
- whether the records are restricted because of age, live/completed state, privacy, event
  configuration, or another observable factor;
- whether ACL provides an authorized authentication mechanism for this data;
- whether the platform is permitted and expected to use authenticated access;
- how many games and rounds are missing because of these responses;
- how the missing coverage biases calculated PPR, DPR, consistency, and predictions;
- how the UI and model feature snapshots will disclose partial coverage;
- the safe fallback when authenticated access is unavailable.

Do not restore or introduce captured browser cookies as an implicit fallback. Any approved
authenticated integration must use an explicit, documented credential flow with secrets
kept outside source control and captured fixtures.

## Suggested review fields

For each endpoint, record:

- observed HTTP status with no credentials;
- whether browser context headers are actually required;
- method, path parameters, query parameters, and body schema;
- top-level response shape and all observed variants;
- field name, type, nullability, and meaning;
- identifier scope;
- timestamp meaning and timezone;
- singles/doubles and event-format differences;
- pagination, limits, cache headers, and rate behavior;
- whether returned statistics are raw facts or ACL-calculated aggregates;
- known coverage/window rules;
- whether 401/403 behavior varies by match, event, age, account, or request origin.

Do not add real tokens or cookies to fixtures or this document. If authenticated testing is
later required, credentials should be supplied through environment/secret configuration and
redacted from captured request metadata. Redaction must remain visible: preserve the field
name, use a typed marker such as `[REDACTED_COOKIE]` or `[REDACTED_TOKEN]`, and include the
JSON path and reason in the fixture's redaction summary.
