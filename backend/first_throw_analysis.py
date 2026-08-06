from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Any

from live_probability_evaluation import _rounds


def analyze_first_throw(
    conn: sqlite3.Connection,
    *,
    max_games: int = 1000,
    minimum_player_rounds: int = 20,
) -> dict[str, Any]:
    games = conn.execute(
        """
        SELECT g.event_id, g.match_id, g.game_id, g.home_team_id, g.away_team_id,
               g.home_score, g.away_score, e.event_date, e.match_type,
               e.bracket_type, e.blind_draw
        FROM games g
        JOIN events e ON e.event_id=g.event_id
        WHERE g.completed=1 AND e.event_date IS NOT NULL
          AND g.home_team_id IS NOT NULL AND g.away_team_id IS NOT NULL
        ORDER BY e.event_date DESC, g.event_id DESC, g.match_id DESC, g.game_id DESC
        LIMIT ?
        """,
        (max(max_games, 1),),
    ).fetchall()
    overall = _empty()
    formats: dict[str, dict[str, float]] = defaultdict(_empty)
    players: dict[str, dict[str, Any]] = defaultdict(_empty)
    games_with_rounds = 0
    unknown_opening_rounds = 0
    rounds_until_known: list[int] = []
    chronological_games: list[tuple[str, dict[str, Any]]] = []

    for raw_game in games:
        game = dict(raw_game)
        rounds = _rounds(conn, game)
        if not rounds:
            continue
        games_with_rounds += 1
        first_scoring_round = next(
            (
                int(round_row.get("round") or 0)
                for round_row in rounds
                if (round_row.get("gameState") or {}).get("roundScoringTeamId") is not None
            ),
            None,
        )
        if first_scoring_round is not None:
            rounds_until_known.append(first_scoring_round)
        winner = (
            str(game["home_team_id"])
            if int(game["home_score"] or 0) > int(game["away_score"] or 0)
            else str(game["away_team_id"])
        )
        format_key = _format_key(game)
        game_effect = _empty()
        for round_row in rounds:
            state = round_row.get("gameState") or {}
            first_team = state.get("firstThrowTeamId")
            if first_team is None:
                unknown_opening_rounds += 1
                continue
            scoring_team = state.get("roundScoringTeamId")
            first_player = state.get("firstThrowPlayerId")
            net = int(state.get("netPoints") or 0)
            _add(overall, first_team, scoring_team, net, winner)
            _add(game_effect, first_team, scoring_team, net, winner)
            _add(formats[format_key], first_team, scoring_team, net, winner)
            if first_player is not None:
                player = players[str(first_player)]
                player["playerId"] = str(first_player)
                player["playerName"] = _player_name(round_row, str(first_player))
                _add(player, first_team, scoring_team, net, winner)
        chronological_games.append((str(game["event_date"]), game_effect))

    overall_summary = _summarize(overall)
    player_rows = [
        _summarize(row)
        for row in players.values()
        if int(row["knownRounds"]) >= minimum_player_rounds
    ]
    player_rows.sort(key=lambda row: (-int(row["knownRounds"]), str(row.get("playerName") or "")))
    recommendation = _recommendation(overall_summary)
    return {
        "gamesConsidered": len(games),
        "gamesWithRoundData": games_with_rounds,
        "unknownOpeningRounds": unknown_opening_rounds,
        "firstThrowCertainty": _certainty_summary(rounds_until_known, games_with_rounds),
        "overall": overall_summary,
        "byFormat": [
            {"format": key, **_summarize(value)}
            for key, value in sorted(formats.items())
        ],
        "byPlayer": player_rows,
        "minimumPlayerRounds": minimum_player_rounds,
        "simulationRecommendation": recommendation,
        "chronologicalValidation": _chronological_validation(chronological_games),
        "notes": [
            "Opening first throw remains unknown unless manually supplied.",
            "After the first scoring round, ownership carries through washes.",
            "Game-win percentage is descriptive and repeated across round states; it is not used as an independent effect estimate.",
        ],
    }


def _empty() -> dict[str, Any]:
    return {
        "knownRounds": 0,
        "scoredRounds": 0,
        "concededRounds": 0,
        "washRounds": 0,
        "signedNetPoints": 0,
        "gameWinnerStates": 0,
    }


def _add(row: dict[str, Any], first_team: str, scoring_team: str | None, net: int, winner: str) -> None:
    row["knownRounds"] += 1
    row["gameWinnerStates"] += int(str(first_team) == str(winner))
    if scoring_team is None or net == 0:
        row["washRounds"] += 1
    elif str(scoring_team) == str(first_team):
        row["scoredRounds"] += 1
        row["signedNetPoints"] += net
    else:
        row["concededRounds"] += 1
        row["signedNetPoints"] -= net


def _summarize(row: dict[str, Any]) -> dict[str, Any]:
    rounds = int(row["knownRounds"])
    decisive = int(row["scoredRounds"]) + int(row["concededRounds"])
    scoring_share = row["scoredRounds"] / decisive if decisive else None
    interval = _wilson(int(row["scoredRounds"]), decisive) if decisive else (None, None)
    return {
        **{key: value for key, value in row.items() if key not in {"signedNetPoints", "gameWinnerStates"}},
        "firstThrowScoreRate": _rate(row["scoredRounds"], rounds),
        "firstThrowConcedeRate": _rate(row["concededRounds"], rounds),
        "washRate": _rate(row["washRounds"], rounds),
        "decisiveRoundScoringShare": round(scoring_share, 6) if scoring_share is not None else None,
        "decisiveScoringShare95CI": [
            round(interval[0], 6) if interval[0] is not None else None,
            round(interval[1], 6) if interval[1] is not None else None,
        ],
        "averageSignedNetPoints": row["signedNetPoints"] / rounds if rounds else None,
        "firstThrowTeamGameWinRate": _rate(row["gameWinnerStates"], rounds),
    }


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return center - margin, center + margin


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _format_key(game: dict[str, Any]) -> str:
    blind = "BLIND" if int(game.get("blind_draw") or 0) else "BYOP"
    return f"{str(game.get('match_type') or 'UNKNOWN').upper()}:{str(game.get('bracket_type') or 'UNKNOWN').upper()}:{blind}"


def _player_name(round_row: dict[str, Any], player_id: str) -> str:
    for player in round_row.get("players") or []:
        if str(player.get("playerId")) == player_id:
            return str(player.get("name") or f"Player {player_id}")
    return f"Player {player_id}"


def _recommendation(summary: dict[str, Any]) -> dict[str, Any]:
    rounds = int(summary["knownRounds"])
    low, high = summary["decisiveScoringShare95CI"]
    supported = rounds >= 500 and low is not None and (low > 0.5 or high < 0.5)
    return {
        "applyIndependentWeight": supported,
        "status": "SUPPORTED" if supported else "INSUFFICIENT_OR_INCONCLUSIVE",
        "reason": (
            "The decisive-round scoring interval excludes 50% with at least 500 known rounds."
            if supported
            else "Retain first throw as a model input with zero weight until the sample is sufficient and its interval excludes 50%."
        ),
    }


def _certainty_summary(values: list[int], games_with_rounds: int) -> dict[str, Any]:
    ordered = sorted(values)
    count = len(ordered)
    average = sum(ordered) / count if count else None
    median = (
        ordered[count // 2]
        if count % 2
        else (ordered[count // 2 - 1] + ordered[count // 2]) / 2
    ) if count else None
    distribution = [
        {
            "byEndOfRound": round_number,
            "gamesKnown": sum(value <= round_number for value in ordered),
            "knownRate": round(sum(value <= round_number for value in ordered) / games_with_rounds, 6)
            if games_with_rounds else None,
        }
        for round_number in range(1, min(max(ordered, default=0), 10) + 1)
    ]
    return {
        "unit": "COMPLETED_ROUNDS",
        "gamesResolved": count,
        "gamesUnresolved": max(games_with_rounds - count, 0),
        "averageRoundsUntilKnown": round(average, 4) if average is not None else None,
        "medianRoundsUntilKnown": median,
        "maximumRoundsUntilKnown": max(ordered) if ordered else None,
        "cumulativeByRound": distribution,
        "elapsedTimeAvailable": False,
        "elapsedTimeLimitation": "ACL round records do not currently provide reliable per-round timestamps.",
    }


def _chronological_validation(
    games: list[tuple[str, dict[str, Any]]],
    development_fraction: float = 0.7,
) -> dict[str, Any]:
    ordered = sorted(games, key=lambda item: item[0])
    split = max(1, min(len(ordered) - 1, int(len(ordered) * development_fraction))) if len(ordered) > 1 else len(ordered)
    development = _merge([row for _, row in ordered[:split]])
    holdout = _merge([row for _, row in ordered[split:]])
    development_summary = _summarize(development)
    holdout_summary = _summarize(holdout)
    dev_low, dev_high = development_summary["decisiveScoringShare95CI"]
    hold_low, hold_high = holdout_summary["decisiveScoringShare95CI"]
    stable = (
        dev_low is not None and hold_low is not None
        and dev_low > 0.5 and hold_low > 0.5
    )
    return {
        "policy": "OLDEST_70_PERCENT_DEVELOPMENT_NEWEST_30_PERCENT_HOLDOUT",
        "developmentGames": split,
        "holdoutGames": max(len(ordered) - split, 0),
        "development": development_summary,
        "holdout": holdout_summary,
        "effectReplicated": stable,
        "activationStatus": "READY_FOR_SIMULATION_WEIGHT" if stable else "DO_NOT_ACTIVATE",
    }


def _merge(rows: list[dict[str, Any]]) -> dict[str, Any]:
    merged = _empty()
    for row in rows:
        for key in merged:
            merged[key] += row.get(key, 0)
    return merged
