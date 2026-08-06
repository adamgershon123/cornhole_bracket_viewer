from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ANALYSIS_VERSION = "double-dip-history-v1"
VENUE_PRIOR_EVENTS = 50.0
PLAYER_PRIOR_APPEARANCES = 12.0
_HISTORY_WORKER_STARTED = False
_HISTORY_WORKER_LOCK = threading.Lock()


def double_dip_report(
    conn: sqlite3.Connection,
    *,
    bracket_paths: Iterable[Path],
) -> dict[str, Any]:
    records = []
    for path in bracket_paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
            payload = payload["payload"]
        record = analyze_double_elimination_final(payload)
        if record:
            records.append(record)

    event_context = {
        int(row["event_id"]): row
        for row in conn.execute(
            """
            SELECT event_id, event_name, event_date,
                   COALESCE(location_id, '') AS location_id,
                   COALESCE(location_name, 'Unknown venue') AS location_name,
                   COALESCE(match_type, 'UNKNOWN') AS match_type
            FROM events
            """
        ).fetchall()
    }
    for record in records:
        context = event_context.get(record["eventId"])
        if context:
            record.update({
                "eventName": context["event_name"],
                "eventDate": context["event_date"],
                "locationId": str(context["location_id"] or ""),
                "venue": context["location_name"],
                "matchType": context["match_type"],
            })

    return {
        "status": "COMPLETE" if records else "INSUFFICIENT_HISTORY",
        "analysisVersion": ANALYSIS_VERSION,
        "overall": _summary(records),
        "byVenue": _grouped(records, lambda row: row.get("locationId") or row.get("venue") or "Unknown"),
        "byFieldSize": _grouped(records, lambda row: _field_bucket(row["teamCount"])),
        "byMatchType": _grouped(records, lambda row: str(row.get("matchType") or "UNKNOWN")),
        "events": sorted(records, key=lambda row: (str(row.get("eventDate") or ""), row["eventId"]), reverse=True),
        "notes": [
            "A reset means the championship match contains a second completed game.",
            "King-seat identity is derived from each finalist's immediately preceding winners/losers bracket path.",
            "Venue and player splits are descriptive until cutoff-safe holdout validation establishes predictive value.",
        ],
    }


def start_double_dip_history_worker(db_factory, *, data_dir: str | Path) -> None:
    """Populate the player ledger from already-cached brackets without delaying requests."""
    global _HISTORY_WORKER_STARTED
    with _HISTORY_WORKER_LOCK:
        if _HISTORY_WORKER_STARTED:
            return
        _HISTORY_WORKER_STARTED = True

    def run() -> None:
        try:
            root = Path(data_dir)
            paths = list(root.glob("event_*.json"))
            paths.extend((root / "season_platform" / "raw" / "brackets").glob("event_*.json"))
            with db_factory() as conn:
                report = double_dip_report(conn, bracket_paths=paths)
                records = report.get("events") or []
                for offset in range(0, len(records), 50):
                    store_double_dip_records(conn, records[offset:offset + 50])
        except Exception as exc:
            print(f"Double-dip history backfill failed: {exc}")

    threading.Thread(target=run, name="double-dip-history", daemon=True).start()


def store_double_dip_records(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> int:
    _init_schema(conn)
    for row in records:
        conn.execute(
            """
            INSERT INTO double_dip_events(
              event_id, venue_key, venue_name, event_date, match_type, team_count,
              king_seat_team_id, challenger_team_id, champion_team_id,
              reset_occurred, king_seat_won, king_seat_wait_minutes,
              challenger_wait_minutes, analysis_version
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO UPDATE SET
              venue_key=excluded.venue_key, venue_name=excluded.venue_name,
              event_date=excluded.event_date, match_type=excluded.match_type,
              team_count=excluded.team_count,
              king_seat_team_id=excluded.king_seat_team_id,
              challenger_team_id=excluded.challenger_team_id,
              champion_team_id=excluded.champion_team_id,
              reset_occurred=excluded.reset_occurred,
              king_seat_won=excluded.king_seat_won,
              king_seat_wait_minutes=excluded.king_seat_wait_minutes,
              challenger_wait_minutes=excluded.challenger_wait_minutes,
              analysis_version=excluded.analysis_version
            """,
            (
                row["eventId"], row.get("locationId") or row.get("venue") or "Unknown",
                row.get("venue"), row.get("eventDate"), row.get("matchType"), row["teamCount"],
                row["kingSeatTeamId"], row["challengerTeamId"], row["championTeamId"],
                int(bool(row["resetOccurred"])), int(bool(row["kingSeatWon"])),
                row.get("kingSeatWaitMinutes"), row.get("challengerWaitMinutes"), ANALYSIS_VERSION,
            ),
        )
        outcome = _outcome_code(row)
        for role, player_key in (
            ("KING_SEAT", "kingSeatPlayerIds"),
            ("CHALLENGER", "challengerPlayerIds"),
        ):
            conn.execute(
                "DELETE FROM double_dip_player_events WHERE event_id=? AND role=?",
                (row["eventId"], role),
            )
            for player_id in row.get(player_key) or []:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO double_dip_player_events(
                      event_id, player_id, role, outcome, analysis_version
                    ) VALUES(?,?,?,?,?)
                    """,
                    (row["eventId"], int(player_id), role, outcome, ANALYSIS_VERSION),
                )
    conn.commit()
    return len(records)


def double_dip_baseline(
    conn: sqlite3.Connection,
    *,
    venue_key: str | None,
    cutoff_date: str | None = None,
) -> dict[str, Any]:
    _init_schema(conn)
    cutoff_clause = " WHERE event_date < ?" if cutoff_date else ""
    cutoff_params = (str(cutoff_date),) if cutoff_date else ()
    overall = conn.execute(
        "SELECT COUNT(*) AS events, AVG(king_seat_won) AS king_rate, AVG(reset_occurred) AS reset_rate FROM double_dip_events"
        + cutoff_clause,
        cutoff_params,
    ).fetchone()
    total = int(overall["events"] or 0)
    overall_king = float(overall["king_rate"]) if total else 0.75
    overall_reset = float(overall["reset_rate"]) if total else 0.5
    venue = conn.execute(
        "SELECT COUNT(*) AS events, AVG(king_seat_won) AS king_rate, AVG(reset_occurred) AS reset_rate FROM double_dip_events WHERE venue_key=?"
        + (" AND event_date < ?" if cutoff_date else ""),
        (str(venue_key or ""), *cutoff_params),
    ).fetchone()
    venue_events = int(venue["events"] or 0)
    weight = venue_events / (venue_events + VENUE_PRIOR_EVENTS) if venue_events else 0.0
    venue_king = float(venue["king_rate"]) if venue_events else overall_king
    venue_reset = float(venue["reset_rate"]) if venue_events else overall_reset
    return {
        "overallEvents": total,
        "overallKingSeatChampionshipRate": round(overall_king, 6),
        "overallResetRate": round(overall_reset, 6),
        "venueKey": venue_key,
        "cutoffDate": cutoff_date,
        "venueEvents": venue_events,
        "venueWeight": round(weight, 6),
        "venueKingSeatChampionshipRate": round(venue_king, 6) if venue_events else None,
        "venueResetRate": round(venue_reset, 6) if venue_events else None,
        "blendedKingSeatChampionshipRate": round((1.0 - weight) * overall_king + weight * venue_king, 6),
        "blendedResetRate": round((1.0 - weight) * overall_reset + weight * venue_reset, 6),
    }


def championship_double_dip_profile(
    conn: sqlite3.Connection,
    *,
    payload: dict[str, Any],
    match_id: str | int,
) -> dict[str, Any] | None:
    """Return role-specific championship history for the two current finalists."""
    _init_schema(conn)
    context = championship_match_context(payload, match_id=match_id)
    if not context:
        return None

    completed = analyze_double_elimination_final(payload)
    if completed:
        store_double_dip_records(conn, [completed])

    overall_rows = conn.execute(
        "SELECT reset_occurred, king_seat_won FROM double_dip_events"
    ).fetchall()
    overall = _outcome_rates(overall_rows)
    return {
        **context,
        "analysisVersion": ANALYSIS_VERSION,
        "definitions": {
            "kingSeat": "Reached the championship without a loss and must be beaten twice.",
            "challenger": "Reached the championship through the elimination bracket and must win twice.",
            "rating": "Historical rate shrunk toward all recorded championships when the player sample is small.",
        },
        "kingSeat": _role_profile(
            conn,
            role="KING_SEAT",
            player_ids=context["kingSeatPlayerIds"],
            player_names=context["kingSeatPlayerNames"],
            overall=overall,
        ),
        "challenger": _role_profile(
            conn,
            role="CHALLENGER",
            player_ids=context["challengerPlayerIds"],
            player_names=context["challengerPlayerNames"],
            overall=overall,
        ),
    }


def championship_match_context(payload: dict[str, Any], *, match_id: str | int) -> dict[str, Any] | None:
    details = [row for row in payload.get("bracketDetails") or [] if isinstance(row, dict)]
    selected_id = _integer(match_id)
    if selected_id is None:
        return None
    rows = [row for row in details if _integer(row.get("bracketmatchid")) == selected_id]
    if len(rows) < 2 or not any(token in str(rows[0].get("rounddesc") or "").upper() for token in ("FINAL", "CHAMP")):
        return None
    top, bottom = _top_bottom(rows)
    if not top or not bottom:
        return None
    top_id, bottom_id = str(top.get("bracketteamid")), str(bottom.get("bracketteamid"))
    king_id = _king_seat_id(details, selected_id, {top_id, bottom_id})
    if not king_id:
        return None
    challenger_id = bottom_id if king_id == top_id else top_id
    teams = {top_id: top, bottom_id: bottom}

    def players(team_id: str) -> tuple[list[int], list[str]]:
        ids, names = [], []
        for player in teams[team_id].get("player_info") or []:
            player_id = _integer(player.get("playerid") or player.get("id"))
            if player_id is not None:
                ids.append(player_id)
            name = " ".join(filter(None, [player.get("firstname"), player.get("lastname")])).strip()
            names.append(name or (f"Player {player_id}" if player_id is not None else "Unknown player"))
        return ids, names

    king_ids, king_names = players(king_id)
    challenger_ids, challenger_names = players(challenger_id)
    return {
        "status": "AVAILABLE",
        "matchId": str(selected_id),
        "kingSeatTeamId": king_id,
        "challengerTeamId": challenger_id,
        "kingSeatPlayerIds": king_ids,
        "kingSeatPlayerNames": king_names,
        "challengerPlayerIds": challenger_ids,
        "challengerPlayerNames": challenger_names,
    }


def _role_profile(conn, *, role: str, player_ids: list[int], player_names: list[str], overall: dict[str, float]) -> dict[str, Any]:
    players = []
    for index, player_id in enumerate(player_ids):
        rows = conn.execute(
            """
            SELECT e.reset_occurred, e.king_seat_won
            FROM double_dip_player_events p
            JOIN double_dip_events e ON e.event_id=p.event_id
            WHERE p.player_id=? AND p.role=?
            """,
            (player_id, role),
        ).fetchall()
        players.append(_participant_summary(
            player_id=player_id,
            player_name=player_names[index] if index < len(player_names) else f"Player {player_id}",
            role=role,
            rows=rows,
            overall=overall,
        ))

    placeholders = ",".join("?" for _ in player_ids)
    combined_rows = []
    if placeholders:
        combined_rows = conn.execute(
            f"""
            SELECT DISTINCT e.event_id, e.reset_occurred, e.king_seat_won
            FROM double_dip_player_events p
            JOIN double_dip_events e ON e.event_id=p.event_id
            WHERE p.player_id IN ({placeholders}) AND p.role=?
            """,
            (*player_ids, role),
        ).fetchall()
    raw = _outcome_rates(combined_rows)
    keys = _role_keys(role)
    team_average = {
        key: round(mean([player["rating"][key] for player in players]), 4) if players else None
        for key in keys
    }
    return {
        "role": role,
        "players": players,
        "teamAverageRating": team_average,
        "combinedHistory": {
            "appearances": len(combined_rows),
            **{key: raw[key] for key in keys},
        },
    }


def _participant_summary(*, player_id: int, player_name: str, role: str, rows, overall) -> dict[str, Any]:
    raw = _outcome_rates(rows)
    appearances = len(rows)
    keys = _role_keys(role)
    weight = appearances / (appearances + PLAYER_PRIOR_APPEARANCES) if appearances else 0.0
    return {
        "playerId": player_id,
        "playerName": player_name,
        "appearances": appearances,
        "sampleConfidence": round(weight, 4),
        "raw": {key: raw[key] if appearances else None for key in keys},
        "rating": {
            key: round(weight * raw[key] + (1.0 - weight) * overall[key], 4)
            for key in keys
        },
    }


def _role_keys(role: str) -> tuple[str, str, str]:
    return ("winInOneRate", "winInTwoRate", "doubleDippedRate") if role == "KING_SEAT" else (
        "loseFirstRate", "loseSecondRate", "completeDoubleDipRate"
    )


def _outcome_rates(rows) -> dict[str, float]:
    count = len(rows)
    divisor = float(count or 1)
    king_one = sum(not bool(row["reset_occurred"]) and bool(row["king_seat_won"]) for row in rows)
    king_two = sum(bool(row["reset_occurred"]) and bool(row["king_seat_won"]) for row in rows)
    challenger = sum(bool(row["reset_occurred"]) and not bool(row["king_seat_won"]) for row in rows)
    return {
        "winInOneRate": king_one / divisor,
        "winInTwoRate": king_two / divisor,
        "doubleDippedRate": challenger / divisor,
        "loseFirstRate": king_one / divisor,
        "loseSecondRate": king_two / divisor,
        "completeDoubleDipRate": challenger / divisor,
    }


def _outcome_code(row: dict[str, Any]) -> str:
    if not row["resetOccurred"]:
        return "KING_WON_ONE"
    return "KING_WON_TWO" if row["kingSeatWon"] else "CHALLENGER_DOUBLE_DIP"


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS double_dip_events(
          event_id INTEGER PRIMARY KEY,
          venue_key TEXT, venue_name TEXT, event_date TEXT, match_type TEXT,
          team_count INTEGER, king_seat_team_id TEXT, challenger_team_id TEXT,
          champion_team_id TEXT, reset_occurred INTEGER, king_seat_won INTEGER,
          king_seat_wait_minutes REAL, challenger_wait_minutes REAL,
          analysis_version TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_double_dip_venue ON double_dip_events(venue_key)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS double_dip_player_events(
          event_id INTEGER NOT NULL, player_id INTEGER NOT NULL,
          role TEXT NOT NULL, outcome TEXT NOT NULL, analysis_version TEXT NOT NULL,
          PRIMARY KEY(event_id, player_id, role)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_double_dip_player_role ON double_dip_player_events(player_id, role)")
    conn.commit()


def analyze_double_elimination_final(payload: dict[str, Any]) -> dict[str, Any] | None:
    details = [row for row in payload.get("bracketDetails") or [] if isinstance(row, dict)]
    if not details or not any(str(row.get("bracketside") or "").upper() == "L" for row in details):
        return None
    event_info = payload.get("eventInfo") or {}
    event_id = _integer(event_info.get("eventID") or event_info.get("leagueID"))
    if not event_id:
        return None
    finals = defaultdict(list)
    for row in details:
        if str(row.get("rounddesc") or "").strip().upper() == "FINAL":
            finals[str(row.get("bracketmatchid"))].append(row)
    candidates = []
    for match_id, rows in finals.items():
        if len(rows) < 2:
            continue
        games = rows[0].get("gameResults") or rows[1].get("gameResults") or []
        completed = [game for game in games if _integer(game.get("matchStatusID")) == 5]
        if completed:
            candidates.append((_integer(match_id) or 0, rows, sorted(completed, key=lambda game: _integer(game.get("gameID") or game.get("gameId")) or 0)))
    if not candidates:
        return None
    final_match_id, rows, games = max(candidates, key=lambda item: item[0])
    top, bottom = _top_bottom(rows)
    if not top or not bottom:
        return None
    top_id, bottom_id = str(top.get("bracketteamid")), str(bottom.get("bracketteamid"))
    king_id = _king_seat_id(details, final_match_id, {top_id, bottom_id})
    if not king_id:
        return None
    challenger_id = bottom_id if king_id == top_id else top_id
    winners = [_game_winner(game, top_id, bottom_id) for game in games]
    winners = [winner for winner in winners if winner]
    if not winners:
        return None
    reset = len(winners) >= 2
    champion_id = winners[-1]
    team_players = {
        str(row.get("bracketteamid")): [
            int(player_id)
            for player in row.get("player_info") or []
            if (player_id := _integer(player.get("playerid") or player.get("id"))) is not None
        ]
        for row in (top, bottom)
    }
    prior_ends = {
        team_id: _last_completed_end(details, team_id, before_match_id=final_match_id)
        for team_id in (king_id, challenger_id)
    }
    final_start = _parse_time(games[0].get("matchStartTime"))
    waits = {
        team_id: round((final_start - prior_end).total_seconds() / 60, 2)
        if final_start and prior_end else None
        for team_id, prior_end in prior_ends.items()
    }
    return {
        "eventId": event_id,
        "eventName": event_info.get("eventName") or event_info.get("leagueName") or event_info.get("leaguename"),
        "eventDate": str(event_info.get("startdate") or event_info.get("leagueStartDate") or event_info.get("leaguestartdate") or "")[:10] or None,
        "locationId": str(event_info.get("leagueLocationID") or event_info.get("locationID") or ""),
        "venue": event_info.get("leagueLocationName") or event_info.get("locationName") or "Unknown venue",
        "matchType": event_info.get("matchType") or event_info.get("matchtype") or "UNKNOWN",
        "finalMatchId": str(final_match_id),
        "teamCount": len({str(row.get("bracketteamid")) for row in details if _valid_team(row)}),
        "kingSeatTeamId": king_id,
        "challengerTeamId": challenger_id,
        "championTeamId": champion_id,
        "kingSeatWon": champion_id == king_id,
        "resetOccurred": reset,
        "championshipGames": len(winners),
        "kingSeatWaitMinutes": waits.get(king_id),
        "challengerWaitMinutes": waits.get(challenger_id),
        "kingSeatPlayerIds": team_players.get(king_id, []),
        "challengerPlayerIds": team_players.get(challenger_id, []),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    resets = sum(bool(row["resetOccurred"]) for row in rows)
    king_wins = sum(bool(row["kingSeatWon"]) for row in rows)
    king_waits = [float(row["kingSeatWaitMinutes"]) for row in rows if row.get("kingSeatWaitMinutes") is not None and float(row["kingSeatWaitMinutes"]) >= 0]
    challenger_waits = [float(row["challengerWaitMinutes"]) for row in rows if row.get("challengerWaitMinutes") is not None and float(row["challengerWaitMinutes"]) >= 0]
    return {
        "events": count,
        "resets": resets,
        "resetRate": round(resets / count, 6) if count else None,
        "kingSeatChampionships": king_wins,
        "kingSeatChampionshipRate": round(king_wins / count, 6) if count else None,
        "challengerChampionshipRate": round((count - king_wins) / count, 6) if count else None,
        "averageKingSeatWaitMinutes": round(mean(king_waits), 2) if king_waits else None,
        "medianKingSeatWaitMinutes": round(median(king_waits), 2) if king_waits else None,
        "averageChallengerWaitMinutes": round(mean(challenger_waits), 2) if challenger_waits else None,
    }


def _grouped(rows, key_fn):
    groups = defaultdict(list)
    for row in rows:
        groups[str(key_fn(row))].append(row)
    return [
        {"key": key, **_summary(group)}
        for key, group in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def _king_seat_id(details, final_match_id: int, finalist_ids: set[str]) -> str | None:
    paths = defaultdict(list)
    for row in details:
        team_id = str(row.get("bracketteamid"))
        match_id = _integer(row.get("bracketmatchid"))
        if team_id in finalist_ids and match_id is not None and match_id < final_match_id:
            paths[team_id].append((match_id, str(row.get("bracketside") or "").upper()))
    prior_sides = {
        team_id: max(path, key=lambda item: item[0])[1]
        for team_id, path in paths.items() if path
    }
    winners = [team_id for team_id, side in prior_sides.items() if side == "W"]
    losers = [team_id for team_id, side in prior_sides.items() if side == "L"]
    return winners[0] if len(winners) == 1 and len(losers) == 1 else None


def _last_completed_end(details, team_id: str, *, before_match_id: int):
    candidates = []
    for row in details:
        if str(row.get("bracketteamid")) != team_id:
            continue
        match_id = _integer(row.get("bracketmatchid"))
        if match_id is None or match_id >= before_match_id:
            continue
        for game in row.get("gameResults") or []:
            if _integer(game.get("matchStatusID")) == 5:
                value = _parse_time(game.get("matchEndTime") or game.get("matchStartTime"))
                if value:
                    candidates.append(value)
    return max(candidates) if candidates else None


def _game_winner(game, top_id, bottom_id):
    home, away = _integer(game.get("scoreHome")), _integer(game.get("scoreAway"))
    if home is None or away is None or home == away:
        return None
    return top_id if home > away else bottom_id


def _top_bottom(rows):
    top = next((row for row in rows if str(row.get("bracketpos") or "").upper().endswith("T")), None)
    bottom = next((row for row in rows if str(row.get("bracketpos") or "").upper().endswith("B")), None)
    return top, bottom


def _valid_team(row):
    value = _integer(row.get("bracketteamid"))
    return value is not None and value > 0 and not str(row.get("bracketteamname") or "").lower().startswith("bye")


def _field_bucket(size: int) -> str:
    if size <= 8:
        return "2-8"
    if size <= 16:
        return "9-16"
    if size <= 32:
        return "17-32"
    if size <= 64:
        return "33-64"
    return "65+"


def _parse_time(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
