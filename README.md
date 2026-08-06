# Cornhole Live Scoreboard & Analytics Refactor

This package keeps the uploaded Flask project as the backend source of truth and preserves the existing ACL `bracket-data` and `match-stats` fetching behavior. The refactor adds normalized JSON APIs and a mobile-first React/Tailwind frontend.

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

ACL data calls use public/Fanzone-style headers. Cookie fallback is disabled; if ACL blocks a match-stat response with `401` or `403`, the API returns a coverage warning instead of retrying with authentication.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

For Flask to serve the frontend:

```bash
cd frontend
npm run build
cd ../backend
python app.py
```

Open:

```text
http://localhost:5001/?event_id=248182
```

## Normalized APIs

- `GET /api/events/<event_id>/bracket`  
  Pulls existing ACL bracket data and returns normalized event/match/team shell data.

- `GET /api/events/<event_id>/matches?stats=1`  
  Returns normalized matches. With `stats=1`, it also runs the existing match-stats downloader for missing/live game files and normalizes player stats and inning history.

- `GET /api/events/<event_id>/matches/<match_id>`  
  Returns one fully normalized match with games, players, round timeline, PPR, DPR, round win/tie/loss percentages, and momentum-ready round rows.

- `GET /api/events/<event_id>/live`  
  Returns live/current-court match data.

- `GET /api/events/<event_id>/standings`  
  Uses the uploaded standings calculation and returns JSON.

- `GET /api/events/<event_id>/tournament-stats`  
  Uses the uploaded consolidation logic and returns generated player totals/highlights JSON.

- `GET /api/raw/events/<event_id>`  
  Debug endpoint for the raw cached ACL bracket response.

## Season/Career Platform APIs

- `GET /api/season-platform/gather?playerId=<id>&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`
  Builds the player-focused season cache. It fetches player event indexes, bracket data, and only the selected player's match stats by default. The season platform does not use the ACL session cookie; if ACL blocks a match-stat request with `401` or `403`, the response includes a warning notification and marks that game as missing coverage. Add `playerIds=1,2,3` for multiple players, `refreshIndex=1` to refresh cached event indexes, `force=1` to force completed data refreshes, `profiles=1` to cache sanitized player profiles, or `mode=full` for heavier full-event match stat gathering.

- `GET /api/season-platform/leaderboard`
  Reads the normalized SQLite ledger and returns sortable leaderboard rows. Optional filters include `playerId`/`playerIds`, `startDate`, `endDate`, `locationId`, `partnerId`, `opponentId`, and `courtId`.

The season platform writes raw API payloads under `backend/data/season_platform/raw` and normalized data to `backend/data/season_platform/season_platform.db`. Repeated stats are calculated from the `player_rounds` ledger.

## What changed

- HTML card rendering is no longer the app contract.
- Existing pull/caching logic remains on the Flask side.
- Backend now exposes API data shaped around frontend screens: match state, score, players, rounds, player metrics, and tournament context.
- React frontend is mobile-first, with a phone-friendly live match hero, best-player section, momentum chart, round timeline, and tournament summary.

## File layout

```text
backend/
  app.py
  match_stats_downloader.py
  standings.py
  consolidate_tournament_stats.py
  requirements.txt
frontend/
  src/App.tsx
  src/lib/api.ts
  src/components/*
```
