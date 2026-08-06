from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from bracket_prediction_snapshots import _init_schema as initialize_bracket_snapshot_schema
from historical_archive_backtest import historical_backtest_report
from historical_tournament_replay import historical_tournament_replay_status
from prediction_evaluation import prediction_evaluation_report


FIELD_SIZE_BUCKETS = (
    (2, 8, "2–8 teams"),
    (9, 16, "9–16 teams"),
    (17, 32, "17–32 teams"),
    (33, 64, "33–64 teams"),
    (65, 10_000, "65+ teams"),
)


def prediction_performance_report(conn: sqlite3.Connection) -> dict[str, Any]:
    """Score frozen match and tournament forecasts against final results."""
    match_rows = prediction_evaluation_report(conn, limit=250)["evaluations"]
    replay_status = historical_tournament_replay_status(conn)
    tournament_rows = _tournament_evaluations(conn)
    return {
        "historicalBacktest": historical_backtest_report(conn),
        "historicalTournamentReplay": replay_status,
        "matchPerformance": {
            "overall": _binary_summary(match_rows),
            "byConfidence": _grouped_binary_summary(
                match_rows,
                lambda row: _confidence_bucket(
                    max(float(row["sideAProbability"]), float(row["sideBProbability"]))
                ),
            ),
            "byActualMargin": _grouped_binary_summary(
                match_rows,
                lambda row: _margin_bucket(int(row["actualMargin"])),
            ),
        },
        "tournamentPerformance": {
            "overall": _tournament_summary(tournament_rows),
            "byBracketSize": _grouped_tournament_summary(
                tournament_rows, lambda row: _field_size_bucket(row["teamCount"])
            ),
            "calibration": _calibration(tournament_rows),
            "modelComparison": _model_comparison(tournament_rows),
            "events": sorted(
                [
                    {
                        key: value for key, value in row.items()
                        if key != "calibrationForecasts"
                    }
                    for row in tournament_rows
                ],
                key=lambda row: row["frozenAt"],
                reverse=True,
            )[:50],
        },
        "methodology": {
            "match": (
                "Only predictions frozen before play and later joined to a final ACL "
                "match result are scored."
            ),
            "tournament": (
                "The frozen pregame champion distribution is scored against the final "
                "first-place team. Favorite accuracy, top-three hit rate, champion rank, "
                "multiclass Brier score, and champion log loss are reported."
            ),
            "bracketSize": (
                "Tournament performance is separated by the number of real teams in the "
                "frozen field. Byes and unresolved placeholder teams are not competitors."
            ),
        },
    }


def _tournament_evaluations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    initialize_bracket_snapshot_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_prediction_evaluation_cache(
          event_id INTEGER PRIMARY KEY,
          snapshot_created_at TEXT NOT NULL,
          evaluation_json TEXT NOT NULL,
          cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Iterate the cursor instead of fetchall(). Historical replay can create
    # thousands of snapshots whose JSON payloads are large; retaining all raw
    # JSON strings at once can exhaust the web worker before scoring begins.
    snapshots = conn.execute(
        """
        SELECT s.event_id, s.payload_json, s.created_at,
               o.champion_player_ids_json AS replay_champion_player_ids_json,
               e.event_name, e.event_date, e.bracket_type, e.match_type
        FROM bracket_prediction_snapshots s
        LEFT JOIN events e ON e.event_id=s.event_id
        LEFT JOIN historical_tournament_replay_outcomes o ON o.event_id=s.event_id
        WHERE s.snapshot_type='PREGAME'
        ORDER BY s.created_at
        """
    )
    rows = []
    for snapshot in snapshots:
        # Historical replay snapshots and their archived outcomes are immutable.
        # Score each once, then reuse the compact evaluation instead of parsing
        # and sorting thousands of full forecast payloads on every UI refresh.
        if snapshot["replay_champion_player_ids_json"]:
            cached = conn.execute(
                """
                SELECT evaluation_json
                FROM tournament_prediction_evaluation_cache
                WHERE event_id=? AND snapshot_created_at=?
                """,
                (int(snapshot["event_id"]), snapshot["created_at"]),
            ).fetchone()
            if cached:
                cached_row = _json(cached["evaluation_json"])
                if cached_row:
                    rows.append(cached_row)
                    continue
        payload = _json(snapshot["payload_json"])
        teams = [
            team for team in payload.get("teams") or []
            if _valid_team(team)
        ]
        if len(teams) < 2:
            continue
        event_id = int(snapshot["event_id"])
        if snapshot["replay_champion_player_ids_json"]:
            champion_player_ids = {
                int(value) for value in _json(snapshot["replay_champion_player_ids_json"])
            }
            resolution_source = "HISTORICAL_REPLAY_COMPLETED_BRACKET"
        else:
            champion_player_ids, resolution_source = _resolved_champion_player_ids(
                conn, event_id
            )
        if not champion_player_ids:
            continue
        champion = _match_champion_team(teams, champion_player_ids)
        if champion is None:
            continue
        ranked = sorted(
            teams,
            key=lambda team: float(team.get("winEventProbability") or 0),
            reverse=True,
        )
        probabilities = _normalized_probabilities(ranked)
        champion_index = next(
            index for index, team in enumerate(ranked)
            if str(team.get("teamId")) == str(champion.get("teamId"))
        )
        champion_probability = probabilities[champion_index]
        brier = sum(
            (probability - (1.0 if index == champion_index else 0.0)) ** 2
            for index, probability in enumerate(probabilities)
        )
        favorite = ranked[0]
        evaluation = {
            "eventId": int(snapshot["event_id"]),
            "eventName": snapshot["event_name"] or f"Event {snapshot['event_id']}",
            "eventDate": snapshot["event_date"],
            "bracketType": snapshot["bracket_type"],
            "matchType": snapshot["match_type"],
            "frozenAt": snapshot["created_at"],
            "teamCount": len(ranked),
            "bracketSizeBucket": _field_size_bucket(len(ranked)),
            "favoriteTeamId": str(favorite.get("teamId")),
            "favoriteName": _team_name(favorite),
            "favoriteProbability": round(probabilities[0], 6),
            "championTeamId": str(champion.get("teamId")),
            "championName": _team_name(champion),
            "championResolutionSource": resolution_source,
            "championProbability": round(champion_probability, 6),
            "championPredictedRank": champion_index + 1,
            "favoriteWon": champion_index == 0,
            "topThreeHit": champion_index < min(3, len(ranked)),
            "multiclassBrierScore": round(brier, 6),
            "championLogLoss": round(-math.log(max(champion_probability, 1e-15)), 6),
            "modelCoverageRate": (
                payload.get("coverage", {}).get("modelCoverageRate")
            ),
            "modelVersion": payload.get("modelVersion") or "unknown",
            "snapshotOrigin": payload.get("snapshotOrigin") or "LIVE_FROZEN",
            # Calibration needs only probability/outcome pairs. Compact tuples
            # avoid retaining team dictionaries for every historical forecast.
            "calibrationForecasts": [
                (round(probabilities[index], 6), index == champion_index)
                for index in range(len(ranked))
            ],
        }
        rows.append(evaluation)
        if snapshot["replay_champion_player_ids_json"]:
            conn.execute(
                """
                INSERT INTO tournament_prediction_evaluation_cache(
                  event_id, snapshot_created_at, evaluation_json, cached_at
                ) VALUES(?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(event_id) DO UPDATE SET
                  snapshot_created_at=excluded.snapshot_created_at,
                  evaluation_json=excluded.evaluation_json,
                  cached_at=CURRENT_TIMESTAMP
                """,
                (
                    int(snapshot["event_id"]),
                    snapshot["created_at"],
                    json.dumps(evaluation, separators=(",", ":")),
                ),
            )
    conn.commit()
    return rows


def _resolved_champion_player_ids(
    conn: sqlite3.Connection, event_id: int
) -> tuple[set[int], str | None]:
    """Resolve the actual champion from the bracket, then unique standings."""
    bracket_ids = _bracket_champion_player_ids(event_id)
    if bracket_ids:
        return bracket_ids, "COMPLETED_BRACKET_FINAL"
    standings_ids = _unique_standings_champion_player_ids(conn, event_id)
    if standings_ids:
        return standings_ids, "UNIQUE_EVENT_STANDINGS"
    return set(), None


def _bracket_champion_player_ids(event_id: int) -> set[int]:
    payload = _cached_bracket_payload(event_id)
    details = payload.get("bracketDetails") or []
    final_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in details:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("rounddesc") or "").strip().upper()
        match_id = entry.get("bracketmatchid")
        if label == "FINAL" and match_id is not None:
            final_groups[str(match_id)].append(entry)

    completed_finals = []
    for match_id, entries in final_groups.items():
        if len(entries) < 2 or not all(
            _integer(entry.get("matchStatusID")) == 5 for entry in entries
        ):
            continue
        completed_finals.append((_integer(match_id) or 0, entries))
    if not completed_finals:
        return set()

    _, entries = max(completed_finals, key=lambda item: item[0])
    top = next(
        (entry for entry in entries if "T" in str(entry.get("bracketpos") or "")),
        entries[0],
    )
    bottom = next(
        (entry for entry in entries if "B" in str(entry.get("bracketpos") or "")),
        entries[1],
    )
    games = top.get("gameResults") or bottom.get("gameResults") or []
    completed_games = [
        game for game in games
        if isinstance(game, dict) and _integer(game.get("matchStatusID")) == 5
    ]
    if completed_games:
        latest = max(
            completed_games,
            key=lambda game: _integer(game.get("gameID") or game.get("gameId")) or 0,
        )
        home_score = _integer(latest.get("scoreHome"))
        away_score = _integer(latest.get("scoreAway"))
    else:
        scores = top.get("scores") or []
        latest = scores[-1] if scores and isinstance(scores[-1], dict) else {}
        home_score = _integer(latest.get("scorehome"))
        away_score = _integer(latest.get("scoreaway"))
    if home_score is None or away_score is None or home_score == away_score:
        return set()

    winner = top if home_score > away_score else bottom
    champion_ids = set()
    for player in winner.get("player_info") or []:
        player_id = player.get("playerid") or player.get("id")
        parsed = _integer(player_id)
        if parsed is not None:
            champion_ids.add(parsed)
    return champion_ids


def _cached_bracket_payload(event_id: int) -> dict[str, Any]:
    paths: list[Path] = []
    configured = os.environ.get("DATA_DIR")
    if configured:
        configured_path = Path(configured)
        configured_path = (
            configured_path if configured_path.is_absolute()
            else Path(__file__).resolve().parent / configured_path
        )
        paths.extend([
            configured_path / f"event_{event_id}.json",
            configured_path / "season_platform" / "raw" / "brackets" / f"event_{event_id}.json",
        ])
    module_data = Path(__file__).resolve().parent / "data"
    paths.extend([
        module_data / "season_platform" / "raw" / "brackets" / f"event_{event_id}.json",
        module_data / f"event_{event_id}.json",
    ])
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            continue
        # season_platform preserves response metadata around the raw ACL body;
        # the live-view cache stores that body directly.
        if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
            payload = payload["payload"]
        if isinstance(payload, dict):
            return payload
    return {}


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unique_standings_champion_player_ids(
    conn: sqlite3.Connection, event_id: int
) -> set[int]:
    best = conn.execute(
        "SELECT MIN(place) FROM event_results WHERE event_id=? AND place>0",
        (event_id,),
    ).fetchone()[0]
    if best is None:
        return set()
    champion_ids = {
        int(row[0])
        for row in conn.execute(
            "SELECT DISTINCT player_id FROM event_results WHERE event_id=? AND place=?",
            (event_id, int(best)),
        ).fetchall()
        if row[0] is not None
    }
    team_keys = {
        str(row[0])
        for row in conn.execute(
            "SELECT DISTINCT team_id FROM event_results WHERE event_id=? AND place=?",
            (event_id, int(best)),
        ).fetchall()
        if row[0] not in (None, "")
    }
    # Multiple first-place teams means ACL exposed a seed/rank rather than a
    # unique final tournament placement.
    return champion_ids if len(team_keys) <= 1 else set()


def _match_champion_team(
    teams: list[dict[str, Any]], champion_player_ids: set[int]
) -> dict[str, Any] | None:
    scored = []
    for team in teams:
        player_ids = _team_player_ids(team)
        overlap = len(player_ids & champion_player_ids)
        if overlap:
            scored.append((overlap, overlap / max(1, len(player_ids)), team))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if len(scored) > 1 and scored[0][:2] == scored[1][:2]:
        return None
    return scored[0][2]


def _tournament_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return _empty_tournament_summary()
    favorite_wins = sum(int(row["favoriteWon"]) for row in rows)
    top_three_hits = sum(int(row["topThreeHit"]) for row in rows)
    model_brier = mean(row["multiclassBrierScore"] for row in rows)
    model_log_loss = mean(row["championLogLoss"] for row in rows)
    equal_brier = mean(1.0 - (1.0 / row["teamCount"]) for row in rows)
    equal_log_loss = mean(math.log(row["teamCount"]) for row in rows)
    return {
        "resolvedTournaments": len(rows),
        "sampleStatus": _sample_status(len(rows)),
        "favoriteAccuracy": round(favorite_wins / len(rows), 6),
        "favoriteAccuracy95": _wilson_interval(favorite_wins, len(rows)),
        "topThreeHitRate": round(top_three_hits / len(rows), 6),
        "topThreeHitRate95": _wilson_interval(top_three_hits, len(rows)),
        "averageChampionRank": round(mean(row["championPredictedRank"] for row in rows), 3),
        "meanChampionProbability": round(mean(row["championProbability"] for row in rows), 6),
        "multiclassBrierScore": round(model_brier, 6),
        "championLogLoss": round(model_log_loss, 6),
        "equalOddsBrierScore": round(equal_brier, 6),
        "equalOddsLogLoss": round(equal_log_loss, 6),
        "brierSkillVsEqual": round(1.0 - model_brier / equal_brier, 6) if equal_brier else None,
        "logLossSkillVsEqual": round(1.0 - model_log_loss / equal_log_loss, 6) if equal_log_loss else None,
        "averageFieldSize": round(mean(row["teamCount"] for row in rows), 2),
    }


def _grouped_tournament_summary(rows, group_key):
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[group_key(row)].append(row)
    return [
        {"group": group, **_tournament_summary(group_rows)}
        for group, group_rows in sorted(
            groups.items(), key=lambda item: _field_size_sort(item[0])
        )
    ]


def _binary_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "resolvedMatches": 0,
            "accuracy": None,
            "brierScore": None,
            "logLoss": None,
            "averageWinnerProbability": None,
        }
    return {
        "resolvedMatches": len(rows),
        "accuracy": round(mean(int(row["correct"]) for row in rows), 6),
        "brierScore": round(mean(float(row["brierScore"]) for row in rows), 6),
        "logLoss": round(mean(float(row["logLoss"]) for row in rows), 6),
        "averageWinnerProbability": round(
            mean(float(row["winnerProbability"]) for row in rows), 6
        ),
    }


def _grouped_binary_summary(rows, group_key):
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[group_key(row)].append(row)
    return [
        {"group": group, **_binary_summary(group_rows)}
        for group, group_rows in groups.items()
    ]


def _normalized_probabilities(teams: Iterable[dict[str, Any]]) -> list[float]:
    values = [max(0.0, float(team.get("winEventProbability") or 0)) for team in teams]
    total = sum(values)
    if total <= 0:
        return [1.0 / len(values)] * len(values)
    return [value / total for value in values]


def _valid_team(team: dict[str, Any]) -> bool:
    name = _team_name(team).strip().lower()
    player_names = [
        str(player.get("playerName") or player.get("name") or "").strip().lower()
        for player in team.get("players") or []
    ]
    try:
        valid_id = int(team.get("teamId")) > 0
    except (TypeError, ValueError):
        valid_id = False
    return (
        valid_id
        and name not in {"bye", "team -1", "-1"}
        and not name.startswith("bye user")
        and not any(
            player_name == "bye" or player_name.startswith("bye user")
            for player_name in player_names
        )
        and bool(_team_player_ids(team))
    )


def _team_player_ids(team: dict[str, Any]) -> set[int]:
    values = team.get("playerIds") or [
        player.get("playerId") for player in team.get("players") or []
    ]
    result = set()
    for value in values:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _team_name(team: dict[str, Any]) -> str:
    players = [
        player.get("playerName") or player.get("name")
        for player in team.get("players") or []
    ]
    return " / ".join(filter(None, players)) or str(
        team.get("teamName") or f"Team {team.get('teamId')}"
    )


def _field_size_bucket(size: int) -> str:
    for minimum, maximum, label in FIELD_SIZE_BUCKETS:
        if minimum <= int(size) <= maximum:
            return label
    return "Unknown"


def _field_size_sort(label: str) -> int:
    return next(
        (minimum for minimum, _, item_label in FIELD_SIZE_BUCKETS if item_label == label),
        99_999,
    )


def _confidence_bucket(probability: float) -> str:
    if probability < 0.55:
        return "50–54%"
    if probability < 0.60:
        return "55–59%"
    if probability < 0.70:
        return "60–69%"
    return "70%+"


def _margin_bucket(margin: int) -> str:
    if margin <= 3:
        return "1–3 points"
    if margin <= 7:
        return "4–7 points"
    return "8+ points"


def _empty_tournament_summary() -> dict[str, Any]:
    return {
        "resolvedTournaments": 0,
        "sampleStatus": "NO_SAMPLE",
        "favoriteAccuracy": None,
        "favoriteAccuracy95": None,
        "topThreeHitRate": None,
        "topThreeHitRate95": None,
        "averageChampionRank": None,
        "meanChampionProbability": None,
        "multiclassBrierScore": None,
        "championLogLoss": None,
        "equalOddsBrierScore": None,
        "equalOddsLogLoss": None,
        "brierSkillVsEqual": None,
        "logLossSkillVsEqual": None,
        "averageFieldSize": None,
    }


def _calibration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = (
        (0.0, 0.05, "0–4%"),
        (0.05, 0.10, "5–9%"),
        (0.10, 0.20, "10–19%"),
        (0.20, 0.40, "20–39%"),
        (0.40, 1.01, "40%+"),
    )
    forecasts = [
        forecast
        for row in rows
        for forecast in row.get("calibrationForecasts") or []
    ]
    output = []
    for minimum, maximum, label in buckets:
        sample = [
            forecast for forecast in forecasts
            if minimum <= float(forecast[0]) < maximum
        ]
        if not sample:
            continue
        wins = sum(int(forecast[1]) for forecast in sample)
        output.append({
            "group": label,
            "teams": len(sample),
            "averagePredictedProbability": round(
                mean(float(forecast[0]) for forecast in sample), 6
            ),
            "actualChampionshipRate": round(wins / len(sample), 6),
            "actualChampionshipRate95": _wilson_interval(wins, len(sample)),
            "sampleStatus": _sample_status(len(sample)),
        })
    return output


def _model_comparison(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = _tournament_summary(rows)
    model_versions = sorted({
        str(row.get("modelVersion") or "unknown") for row in rows
    })
    return [
        {
            "model": "Equal odds",
            "status": "SCORED_BASELINE" if rows else "AWAITING_RESULTS",
            "resolvedTournaments": len(rows),
            "multiclassBrierScore": summary["equalOddsBrierScore"],
            "championLogLoss": summary["equalOddsLogLoss"],
        },
        {
            "model": " / ".join(model_versions) if model_versions else "fitted-ppr-logistic-v1",
            "status": "FROZEN_AND_SCORED" if rows else "AWAITING_RESULTS",
            "resolvedTournaments": len(rows),
            "multiclassBrierScore": summary["multiclassBrierScore"],
            "championLogLoss": summary["championLogLoss"],
            "brierSkillVsEqual": summary["brierSkillVsEqual"],
            "logLossSkillVsEqual": summary["logLossSkillVsEqual"],
        },
        {
            "model": "Advanced profile challenger",
            "status": "PROSPECTIVE_NOT_YET_FROZEN",
            "resolvedTournaments": 0,
            "multiclassBrierScore": None,
            "championLogLoss": None,
            "reason": (
                "Requires independently frozen tournament forecasts before it can "
                "be compared without hindsight."
            ),
        },
    ]


def _wilson_interval(successes: int, total: int) -> dict[str, float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + (z * z / total)
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return {
        "low": round(max(0.0, center - margin), 6),
        "high": round(min(1.0, center + margin), 6),
    }


def _sample_status(total: int) -> str:
    if total < 10:
        return "TOO_EARLY"
    if total < 30:
        return "DIRECTIONAL"
    return "ESTABLISHED"


def _json(raw: str | None) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
