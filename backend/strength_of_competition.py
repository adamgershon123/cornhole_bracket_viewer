from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any


MINIMUM_GAMES = 10


def strength_of_competition_ratings(
    conn: sqlite3.Connection,
    *,
    end_date: str | None = None,
) -> dict[int, dict[str, Any]]:
    records = _competition_records(conn, end_date=end_date)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[int(record["playerId"])].append(record)
    rated = []
    for player_id, player_records in grouped.items():
        if len(player_records) < MINIMUM_GAMES:
            continue
        opponent_values = [float(row["opponentExpectedPpr"]) for row in player_records]
        above = sum(row["opponentTier"] in {"ABOVE_AVERAGE", "STRONG", "ELITE"} for row in player_records)
        strong = sum(row["opponentTier"] in {"STRONG", "ELITE"} for row in player_records)
        elite = sum(row["opponentTier"] == "ELITE" for row in player_records)
        sample_confidence = len(player_records) / (len(player_records) + 30)
        rated.append({
            "playerId": player_id,
            "games": len(player_records),
            "events": len({int(row["eventId"]) for row in player_records}),
            "averageOpponentExpectedPpr": round(sum(opponent_values) / len(opponent_values), 4),
            "medianOpponentExpectedPpr": round(_median(opponent_values), 4),
            "minimumOpponentExpectedPpr": round(min(opponent_values), 4),
            "maximumOpponentExpectedPpr": round(max(opponent_values), 4),
            "aboveAverageOpponentRate": round(above / len(player_records), 4),
            "strongOpponentRate": round(strong / len(player_records), 4),
            "eliteOpponentRate": round(elite / len(player_records), 4),
            "sampleConfidence": round(sample_confidence, 4),
            "formatGameCounts": _format_counts(player_records),
            "lastCompetitionDate": max(row["eventDate"] for row in player_records),
            "recentOpponents": player_records[-10:][::-1],
        })
    ordered = sorted(rated, key=lambda row: row["averageOpponentExpectedPpr"])
    for index, row in enumerate(ordered):
        percentile = 100 * (index + 0.5) / len(ordered)
        row["strengthOfCompetitionRating"] = round(percentile)
        row["percentile"] = round(percentile, 1)
        row["label"] = _label(row["strengthOfCompetitionRating"])
        row["ratedPlayers"] = len(ordered)
        row["source"] = "CHEESEBAGGERS_RECONSTRUCTED_PREGAME_EXPECTED_PPR"
        row["status"] = "DESCRIPTIVE"
    return {int(row["playerId"]): row for row in ordered}


def event_strength_of_schedule(
    conn: sqlite3.Connection,
    event_id: int,
) -> dict[str, Any]:
    event = conn.execute(
        "SELECT event_id,event_name,event_date FROM events WHERE event_id=?",
        (int(event_id),),
    ).fetchone()
    if not event:
        return {"status": "NOT_FOUND", "eventId": int(event_id)}
    event_date = str(event["event_date"] or "")
    if not event_date:
        return {"status": "BLOCKED_MISSING_EVENT_DATE", "eventId": int(event_id)}
    expected = _expected_as_of(conn, event_date)
    members: dict[str, list[int]] = defaultdict(list)
    for row in conn.execute(
        "SELECT team_id,player_id FROM team_members WHERE event_id=?",
        (int(event_id),),
    ).fetchall():
        members[str(row["team_id"])].append(int(row["player_id"]))
    team_strength = {
        team_id: _team_expected(ids, expected)
        for team_id, ids in members.items()
    }
    schedules: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for game in conn.execute(
        """
        SELECT match_id,game_id,home_team_id,away_team_id,completed
        FROM games WHERE event_id=?
        ORDER BY CAST(match_id AS INTEGER),game_id
        """,
        (int(event_id),),
    ).fetchall():
        home, away = str(game["home_team_id"]), str(game["away_team_id"])
        if home in members and away in members:
            schedules[home].append(_schedule_row(game, away, team_strength.get(away)))
            schedules[away].append(_schedule_row(game, home, team_strength.get(home)))
    teams = []
    for team_id, player_ids in members.items():
        schedule = schedules.get(team_id, [])
        known = [
            float(row["opponentExpectedPpr"])
            for row in schedule if row["opponentExpectedPpr"] is not None
        ]
        teams.append({
            "teamId": team_id,
            "playerIds": sorted(player_ids),
            "teamExpectedPpr": team_strength.get(team_id),
            "knownScheduleGames": len(schedule),
            "knownOpponentStrengthGames": len(known),
            "strengthOfSchedule": round(sum(known) / len(known), 4) if known else None,
            "schedule": schedule,
        })
    return {
        "status": "COMPLETE",
        "eventId": int(event_id),
        "eventName": event["event_name"],
        "eventDate": event_date,
        "cutoffPolicy": "OPPONENT_EXPECTED_PPR_STRICTLY_BEFORE_EVENT_DATE",
        "teams": teams,
        "notes": [
            "Strength of Schedule includes only opponents already assigned in recorded games.",
            "Unknown future bracket opponents are not inferred.",
            "Completed and scheduled games remain separately identified.",
        ],
    }


def _competition_records(
    conn: sqlite3.Connection,
    *,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in conn.execute(
        """
        SELECT player_id,event_id,match_id,game_id,team_id,event_date,
               match_type,bracket_type,gross_points
        FROM player_rounds
        WHERE event_date IS NOT NULL AND team_id IS NOT NULL
          AND (? IS NULL OR event_date < ?)
        ORDER BY event_date,event_id,match_id,game_id,round_no
        """,
        (end_date, end_date),
    ).fetchall()]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row["event_date"])].append(row)
    histories: dict[int, list[dict[str, Any]]] = defaultdict(list)
    records = []
    for event_date in sorted(by_date):
        cutoff = date.fromisoformat(event_date)
        season_start = date(cutoff.year if cutoff.month >= 9 else cutoff.year - 1, 9, 1)
        expected = {
            player_id: _history_ppr(history, season_start.isoformat())
            for player_id, history in histories.items()
        }
        known_values = [float(value) for value in expected.values() if value is not None]
        population = sum(known_values) / len(known_values) if known_values else 7.0
        games: dict[tuple[Any, ...], dict[str, set[int]]] = defaultdict(
            lambda: defaultdict(set)
        )
        actual_by_game_player: dict[tuple[tuple[Any, ...], int], list[float]] = defaultdict(list)
        metadata: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in by_date[event_date]:
            key = (row["event_id"], str(row["match_id"]), row["game_id"])
            games[key][str(row["team_id"])].add(int(row["player_id"]))
            actual_by_game_player[(key, int(row["player_id"]))].append(
                float(row.get("gross_points") or 0)
            )
            metadata[key] = row
        for key, teams in games.items():
            if len(teams) != 2:
                continue
            team_items = list(teams.items())
            for index, (_team_id, player_ids) in enumerate(team_items):
                opponent_ids = team_items[1 - index][1]
                opponent_values = [
                    float(expected[player_id])
                    for player_id in opponent_ids
                    if expected.get(player_id) is not None
                ]
                if len(opponent_values) != len(opponent_ids):
                    continue
                opponent_strength = sum(opponent_values) / len(opponent_values)
                for player_id in player_ids:
                    actual_values = actual_by_game_player[(key, player_id)]
                    player_expected = expected.get(player_id)
                    records.append({
                        "playerId": player_id,
                        "eventId": int(key[0]),
                        "matchId": str(key[1]),
                        "gameId": int(key[2]),
                        "eventDate": event_date,
                        "opponentPlayerIds": sorted(opponent_ids),
                        "opponentExpectedPpr": round(opponent_strength, 4),
                        "playerExpectedPpr": (
                            round(float(player_expected), 4)
                            if player_expected is not None else None
                        ),
                        "actualPpr": (
                            round(sum(actual_values) / len(actual_values), 4)
                            if actual_values else None
                        ),
                        "performanceVsExpected": (
                            round(
                                sum(actual_values) / len(actual_values)
                                - float(player_expected),
                                4,
                            )
                            if actual_values and player_expected is not None else None
                        ),
                        "opponentTier": _tier(opponent_strength, population),
                        "populationExpectedPpr": round(population, 4),
                        "format": (
                            f"{str(metadata[key].get('match_type') or 'UNKNOWN').upper()}:"
                            f"{str(metadata[key].get('bracket_type') or 'UNKNOWN').upper()}"
                        ),
                    })
        for row in by_date[event_date]:
            histories[int(row["player_id"])].append(row)
    return records


def _expected_as_of(conn: sqlite3.Connection, cutoff_date: str) -> dict[int, float | None]:
    cutoff = date.fromisoformat(cutoff_date)
    season_start = date(cutoff.year if cutoff.month >= 9 else cutoff.year - 1, 9, 1)
    result = {}
    player_ids = conn.execute("SELECT DISTINCT player_id FROM player_rounds").fetchall()
    for row in player_ids:
        player_id = int(row[0])
        values = conn.execute(
            """
            SELECT gross_points FROM player_rounds
            WHERE player_id=? AND event_date>=? AND event_date<?
            """,
            (player_id, season_start.isoformat(), cutoff_date),
        ).fetchall()
        result[player_id] = (
            sum(float(value[0] or 0) for value in values) / len(values)
            if len(values) >= 30 else None
        )
    return result


def _history_ppr(history: list[dict[str, Any]], season_start: str) -> float | None:
    rows = [row for row in history if str(row["event_date"]) >= season_start]
    if len(rows) < 30:
        return None
    return sum(float(row.get("gross_points") or 0) for row in rows) / len(rows)


def _team_expected(player_ids: list[int], expected: dict[int, float | None]) -> float | None:
    values = [expected.get(player_id) for player_id in player_ids]
    if not values or any(value is None for value in values):
        return None
    return round(sum(float(value) for value in values) / len(values), 4)


def _schedule_row(game: sqlite3.Row, opponent_id: str, strength: float | None) -> dict[str, Any]:
    return {
        "matchId": str(game["match_id"]),
        "gameId": int(game["game_id"]),
        "opponentTeamId": opponent_id,
        "opponentExpectedPpr": strength,
        "completed": bool(game["completed"]),
    }


def _tier(value: float, population: float) -> str:
    difference = value - population
    if difference >= 1.0:
        return "ELITE"
    if difference >= 0.5:
        return "STRONG"
    if difference >= 0.15:
        return "ABOVE_AVERAGE"
    if difference <= -0.5:
        return "DEVELOPING"
    return "AVERAGE"


def _format_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row["format"])] += 1
    return dict(sorted(counts.items()))


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _label(rating: int) -> str:
    if rating >= 90:
        return "Elite Competition"
    if rating >= 75:
        return "Very Strong"
    if rating >= 60:
        return "Above Average"
    if rating >= 40:
        return "Average"
    if rating >= 25:
        return "Below Average"
    return "Developing Field"
