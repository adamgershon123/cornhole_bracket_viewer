from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from statistics import mean
from typing import Any

from baseline_predictions import score_matchup
from stage_a_features import build_matchup_features


EVALUATION_VERSION = "chronological-v1"


def historical_matchups(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    clauses = [
        "e.event_date IS NOT NULL",
        "g.completed=1",
        "g.home_score IS NOT NULL",
        "g.away_score IS NOT NULL",
        "g.home_score != g.away_score",
    ]
    params: list[Any] = []
    if start_date:
        clauses.append("e.event_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("e.event_date <= ?")
        params.append(end_date)
    sql = f"""
        SELECT
            g.event_id, g.match_id, g.game_id,
            g.home_team_id, g.away_team_id,
            g.home_score, g.away_score,
            e.event_date, e.match_type, e.bracket_type
        FROM games g
        JOIN events e ON e.event_id=g.event_id
        WHERE {' AND '.join(clauses)}
        ORDER BY e.event_date, g.event_id, CAST(g.match_id AS INTEGER), g.game_id
    """
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        sql += " LIMIT ?"
        params.append(limit)
    game_rows = conn.execute(sql, params).fetchall()
    matchups: list[dict[str, Any]] = []
    for game in game_rows:
        (
            event_id,
            match_id,
            game_id,
            home_team_id,
            away_team_id,
            home_score,
            away_score,
            event_date,
            match_type,
            bracket_type,
        ) = game
        participants = conn.execute(
            """
            SELECT DISTINCT player_id, team_id, team_side
            FROM player_rounds
            WHERE event_id=? AND match_id=? AND game_id=?
            """,
            (event_id, str(match_id), game_id),
        ).fetchall()
        side_a: set[int] = set()
        side_b: set[int] = set()
        for player_id, team_id, team_side in participants:
            side = str(team_side or "").upper()
            if side == "HOME" or (
                not side and home_team_id is not None and str(team_id) == str(home_team_id)
            ):
                side_a.add(int(player_id))
            elif side == "AWAY" or (
                not side and away_team_id is not None and str(team_id) == str(away_team_id)
            ):
                side_b.add(int(player_id))
        if not side_a or not side_b or side_a.intersection(side_b):
            continue
        matchups.append({
            "eventId": int(event_id),
            "matchId": str(match_id),
            "gameId": int(game_id),
            "eventDate": str(event_date),
            "sideAPlayerIds": sorted(side_a),
            "sideBPlayerIds": sorted(side_b),
            "sideAScore": int(home_score),
            "sideBScore": int(away_score),
            "sideAWon": 1 if int(home_score) > int(away_score) else 0,
            "format": f"{str(match_type or 'UNKNOWN').upper()}:"
                      f"{str(bracket_type or 'UNKNOWN').upper()}",
        })
    return matchups


def _calibration_band(probability: float) -> str:
    lower = min(int(probability * 10) * 10, 90)
    return f"{lower:02d}-{lower + 10:02d}%"


def _metric_summary(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    if not predictions:
        return {
            "predictions": 0,
            "logLoss": None,
            "brierScore": None,
            "accuracy": None,
            "calibration": [],
        }
    losses: list[float] = []
    briers: list[float] = []
    accuracies: list[float] = []
    bands: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for item in predictions:
        probability = float(item["probability"])
        outcome = int(item["outcome"])
        clipped = min(max(probability, 1e-15), 1 - 1e-15)
        losses.append(-(outcome * math.log(clipped) + (1 - outcome) * math.log(1 - clipped)))
        briers.append((probability - outcome) ** 2)
        if probability == 0.5:
            accuracies.append(0.5)
        else:
            accuracies.append(float((probability > 0.5) == bool(outcome)))
        bands[_calibration_band(probability)].append((probability, outcome))
    calibration = []
    for band in sorted(bands):
        values = bands[band]
        calibration.append({
            "band": band,
            "count": len(values),
            "meanPredicted": round(mean(value[0] for value in values), 6),
            "observedWinRate": round(mean(value[1] for value in values), 6),
        })
    return {
        "predictions": len(predictions),
        "logLoss": round(mean(losses), 6),
        "brierScore": round(mean(briers), 6),
        "accuracy": round(mean(accuracies), 6),
        "calibration": calibration,
    }


def _group_metrics(
    predictions: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        groups[str(prediction[key])].append(prediction)
    return {
        group: _metric_summary(items)
        for group, items in sorted(groups.items())
    }


def evaluate_benchmarks(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    window_days: int | None = 365,
    limit: int | None = None,
) -> dict[str, Any]:
    targets = historical_matchups(
        conn,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    equal_predictions: list[dict[str, Any]] = []
    ppr_predictions: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []
    for target in targets:
        cutoff_at = f"{target['eventDate']}T00:00:00+00:00"
        matchup = build_matchup_features(
            conn,
            side_a_player_ids=target["sideAPlayerIds"],
            side_b_player_ids=target["sideBPlayerIds"],
            cutoff_at=cutoff_at,
            window_days=window_days,
            include_acl_snapshots=False,
        )
        common = {
            "eventId": target["eventId"],
            "matchId": target["matchId"],
            "gameId": target["gameId"],
            "eventDate": target["eventDate"],
            "format": target["format"],
            "outcome": target["sideAWon"],
        }
        equal_predictions.append({
            **common,
            "probability": 0.5,
            "evidenceTier": "CONTROL",
        })
        ppr = score_matchup(matchup, model_version="ppr-difference-v1")
        if ppr["status"] == "PREDICTED":
            ppr_predictions.append({
                **common,
                "probability": ppr["sideAProbability"],
                "rawProbability": ppr["rawSideAProbability"],
                "evidenceTier": ppr["evidenceTier"],
            })
        else:
            abstentions.append({
                **common,
                "reason": ppr["reason"],
            })

    ppr_keys = {
        (item["eventId"], item["matchId"], item["gameId"])
        for item in ppr_predictions
    }
    equal_common = [
        item
        for item in equal_predictions
        if (item["eventId"], item["matchId"], item["gameId"]) in ppr_keys
    ]
    equal_summary = _metric_summary(equal_predictions)
    ppr_summary = _metric_summary(ppr_predictions)
    equal_common_summary = _metric_summary(equal_common)
    return {
        "evaluationVersion": EVALUATION_VERSION,
        "featureVersion": "stage-a-v1",
        "windowDays": window_days,
        "startDate": start_date,
        "endDate": end_date,
        "historicalMatchups": len(targets),
        "models": {
            "equal-v1": {
                **equal_summary,
                "coverageRate": round(len(equal_predictions) / len(targets), 6) if targets else 0,
            },
            "ppr-difference-v1": {
                **ppr_summary,
                "abstentions": len(abstentions),
                "coverageRate": round(len(ppr_predictions) / len(targets), 6) if targets else 0,
                "byEvidenceTier": _group_metrics(ppr_predictions, "evidenceTier"),
                "byFormat": _group_metrics(ppr_predictions, "format"),
            },
        },
        "commonSampleComparison": {
            "matchups": len(ppr_predictions),
            "equal-v1": equal_common_summary,
            "ppr-difference-v1": ppr_summary,
            "pprLogLossImprovement": (
                round(equal_common_summary["logLoss"] - ppr_summary["logLoss"], 6)
                if ppr_predictions
                else None
            ),
            "pprBrierImprovement": (
                round(equal_common_summary["brierScore"] - ppr_summary["brierScore"], 6)
                if ppr_predictions
                else None
            ),
        },
        "abstentionReasons": dict(
            sorted(
                {
                    reason: sum(1 for item in abstentions if item["reason"] == reason)
                    for reason in {item["reason"] for item in abstentions}
                }.items()
            )
        ),
        "notes": [
            "Every target uses only event facts strictly before the target event date.",
            "Equal-v1 predicts every matchup with identified recorded sides.",
            "Model comparison uses the common subset where ppr-difference-v1 did not abstain.",
            "Accuracy gives a 50/50 forecast half credit; log loss and Brier score are primary.",
        ],
    }
