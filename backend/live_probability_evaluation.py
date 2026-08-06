from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from typing import Any

from game_state_reconstruction import reconstruct_game_states
from live_win_probability import calculate_probability_series
from baseline_predictions import create_prediction


def evaluate_live_probability(
    conn: sqlite3.Connection,
    *,
    max_games: int = 100,
    simulations_per_state: int = 1_000,
) -> dict[str, Any]:
    games = conn.execute(
        """
        SELECT g.event_id, g.match_id, g.game_id, g.home_team_id, g.away_team_id,
               g.home_score, g.away_score, e.event_date
        FROM games g
        JOIN events e ON e.event_id=g.event_id
        WHERE g.completed=1 AND e.event_date IS NOT NULL
          AND g.home_team_id IS NOT NULL AND g.away_team_id IS NOT NULL
          AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
        ORDER BY e.event_date DESC, g.event_id DESC, g.match_id DESC, g.game_id DESC
        LIMIT ?
        """,
        (max(int(max_games), 1),),
    ).fetchall()
    predictions: dict[str, list[tuple[float, int]]] = defaultdict(list)
    calibration: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    exclusions: dict[str, int] = defaultdict(int)
    games_evaluated = 0
    states_evaluated = 0

    for game in games:
        row = dict(game)
        rounds = _rounds(conn, row)
        if not rounds:
            exclusions["NO_ROUNDS"] += 1
            continue
        home_ids = _team_players(conn, row["event_id"], row["home_team_id"])
        away_ids = _team_players(conn, row["event_id"], row["away_team_id"])
        if not home_ids or not away_ids:
            exclusions["MISSING_TEAM_MEMBERS"] += 1
            continue
        prior = _pregame_probability(conn, row, home_ids, away_ids)
        if prior is None:
            exclusions["NO_ELIGIBLE_PREGAME_MODEL"] += 1
            continue
        home_samples = _historical_samples(conn, home_ids, row["event_date"])
        away_samples = _historical_samples(conn, away_ids, row["event_date"])
        if not home_samples or not away_samples:
            exclusions["NO_PRIOR_PLAYER_ROUNDS"] += 1
            continue
        outcome = int(int(row["home_score"]) > int(row["away_score"]))
        seed = f"eval:{row['event_id']}:{row['match_id']}:{row['game_id']}"
        combined = calculate_probability_series(
            rounds,
            top_team_id=str(row["home_team_id"]),
            bottom_team_id=str(row["away_team_id"]),
            pregame_top_probability=prior,
            top_gross_samples=home_samples,
            bottom_gross_samples=away_samples,
            simulations=simulations_per_state,
            seed_key=seed,
            first_throw_net_edge=0.0,
        )["points"]
        combined_first_throw = calculate_probability_series(
            rounds,
            top_team_id=str(row["home_team_id"]),
            bottom_team_id=str(row["away_team_id"]),
            pregame_top_probability=prior,
            top_gross_samples=home_samples,
            bottom_gross_samples=away_samples,
            simulations=simulations_per_state,
            seed_key=f"{seed}:first-throw",
        )["points"]
        score_only = calculate_probability_series(
            rounds,
            top_team_id=str(row["home_team_id"]),
            bottom_team_id=str(row["away_team_id"]),
            pregame_top_probability=0.5,
            top_gross_samples=home_samples,
            bottom_gross_samples=away_samples,
            simulations=simulations_per_state,
            seed_key=f"{seed}:score",
            first_throw_net_edge=0.0,
        )["points"]
        # Exclude the resolved 100/0 point; it is an outcome, not a forecast.
        for combined_point, first_throw_point, score_point in zip(combined[:-1], combined_first_throw[:-1], score_only[:-1]):
            values = {
                "pregameOnly": prior,
                "scoreOnly": float(score_point["topWinProbability"]),
                "combined": float(combined_point["topWinProbability"]),
                "combinedFirstThrow": float(first_throw_point["topWinProbability"]),
            }
            for model, probability in values.items():
                predictions[model].append((probability, outcome))
                bucket = min(int(probability * 10), 9) * 10
                calibration[model][bucket].append(outcome)
            states_evaluated += 1
        games_evaluated += 1

    return {
        "gamesConsidered": len(games),
        "gamesEvaluated": games_evaluated,
        "statesEvaluated": states_evaluated,
        "simulationsPerState": simulations_per_state,
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE",
        "models": {
            model: {
                **_metrics(rows),
                "calibration": _calibration(calibration[model]),
            }
            for model, rows in predictions.items()
        },
        "exclusions": dict(sorted(exclusions.items())),
        "notes": [
            "Final resolved 100%/0% states are excluded from forecast scoring.",
            "Player round samples are restricted to events before the evaluated event date.",
            "First-throw state is reconstructed but has zero independent weight pending calibration.",
        ],
    }


def _rounds(conn: sqlite3.Connection, game: dict[str, Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.round_no, r.scoring_team_id, r.net_points,
               pr.player_id, pr.team_id, pr.player_name, pr.gross_points
        FROM rounds r
        LEFT JOIN player_rounds pr
          ON pr.event_id=r.event_id AND pr.match_id=r.match_id
         AND pr.game_id=r.game_id AND pr.round_no=r.round_no
        WHERE r.event_id=? AND r.match_id=? AND r.game_id=?
        ORDER BY r.round_no, pr.player_id
        """,
        (game["event_id"], game["match_id"], game["game_id"]),
    ).fetchall()
    grouped: dict[int, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        number = int(row["round_no"])
        scoring_team = (
            str(row["scoring_team_id"])
            if row["scoring_team_id"] is not None
            else None
        )
        if scoring_team is not None and ":" not in scoring_team:
            scoring_team = f"{game['event_id']}:{scoring_team}"
        item = grouped.setdefault(number, {
            "round": number,
            "scoringTeamId": scoring_team,
            "netPoints": int(row["net_points"] or 0),
            "players": [],
        })
        if row["player_id"] is not None:
            item["players"].append({
                "playerId": str(row["player_id"]),
                "teamId": str(row["team_id"]),
                "name": row["player_name"],
                "grossPoints": int(row["gross_points"] or 0),
            })
    result = list(grouped.values())
    states = reconstruct_game_states(result)
    for round_row, state in zip(result, states):
        round_row["gameState"] = state
    return result


def _team_players(conn: sqlite3.Connection, event_id: int, team_id: str) -> list[int]:
    return [
        int(row[0])
        for row in conn.execute(
            "SELECT player_id FROM team_members WHERE event_id=? AND team_id=?",
            (event_id, team_id),
        ).fetchall()
    ]


def _pregame_probability(
    conn: sqlite3.Connection,
    game: dict[str, Any],
    home_ids: list[int],
    away_ids: list[int],
) -> float | None:
    row = conn.execute(
        """
        SELECT side_a_player_ids_json, side_a_probability, side_b_probability
        FROM prediction_records
        WHERE event_id=? AND match_id=? AND prediction_status='PREDICTED'
          AND data_cutoff_at < ?
        ORDER BY prediction_id DESC LIMIT 1
        """,
        (str(game["event_id"]), str(game["match_id"]), f"{game['event_date']}T23:59:59+00:00"),
    ).fetchone()
    if row:
        side_a = {int(value) for value in json.loads(row["side_a_player_ids_json"])}
        if side_a == set(home_ids):
            return float(row["side_a_probability"])
        if side_a == set(away_ids):
            return float(row["side_b_probability"])
    reconstructed = create_prediction(
        conn,
        side_a_player_ids=home_ids,
        side_b_player_ids=away_ids,
        cutoff_at=f"{game['event_date']}T00:00:00+00:00",
        model_version="fitted-ppr-logistic-v1",
        event_id=game["event_id"],
        match_id=game["match_id"],
        persist=False,
    )
    if reconstructed.get("status") != "PREDICTED":
        return None
    return float(reconstructed["sideAProbability"])


def _historical_samples(
    conn: sqlite3.Connection,
    player_ids: list[int],
    before_date: str,
) -> list[int]:
    placeholders = ",".join("?" for _ in player_ids)
    rows = conn.execute(
        f"""
        SELECT gross_points FROM player_rounds
        WHERE player_id IN ({placeholders}) AND event_date < ?
          AND gross_points BETWEEN 0 AND 12
        ORDER BY event_date DESC LIMIT 5000
        """,
        (*player_ids, before_date),
    ).fetchall()
    return [int(row[0]) for row in rows]


def _metrics(rows: list[tuple[float, int]]) -> dict[str, Any]:
    if not rows:
        return {"states": 0, "brierScore": None, "logLoss": None, "accuracy": None}
    brier = sum((p - y) ** 2 for p, y in rows) / len(rows)
    log_loss = -sum(
        y * math.log(max(p, 1e-12)) + (1 - y) * math.log(max(1 - p, 1e-12))
        for p, y in rows
    ) / len(rows)
    accuracy = sum(int((p >= 0.5) == bool(y)) for p, y in rows) / len(rows)
    return {
        "states": len(rows),
        "brierScore": round(brier, 6),
        "logLoss": round(log_loss, 6),
        "accuracy": round(accuracy, 6),
    }


def _calibration(buckets: dict[int, list[int]]) -> list[dict[str, Any]]:
    return [
        {
            "bucket": f"{start}-{start + 10}%",
            "states": len(outcomes),
            "averageOutcome": round(sum(outcomes) / len(outcomes), 4),
        }
        for start, outcomes in sorted(buckets.items())
        if outcomes
    ]
