from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from shadow_predictions import initialize_shadow_schema
from outcome_ingestion import initialize_outcome_schema
from prediction_feedback import backfill_prediction_feedback, initialize_feedback_schema


def prediction_evaluation_report(
    conn: sqlite3.Connection,
    *,
    limit: int | None = 50,
) -> dict[str, Any]:
    """Return auditable, per-match evaluations for frozen pre-match forecasts."""
    initialize_shadow_schema(conn)
    initialize_outcome_schema(conn)
    initialize_feedback_schema(conn)
    backfill_prediction_feedback(conn, limit=250)
    total_resolved = int(conn.execute(
        """
        SELECT COUNT(*)
        FROM shadow_prediction_runs r
        JOIN prediction_records p ON p.prediction_id=r.prediction_id
        JOIN normalized_match_outcomes n
          ON n.event_id=r.event_id AND n.match_id=r.match_id
        WHERE r.status='PREDICTED'
        """
    ).fetchone()[0])
    query = """
        SELECT r.shadow_run_id, r.event_id, r.match_id, r.recorded_at,
               r.scheduled_start_at, r.timing_basis,
               p.side_a_probability, p.side_b_probability, p.evidence_tier,
               p.side_a_player_ids_json, p.side_b_player_ids_json,
               p.features_json,
               c.model_version AS challenger_model_version,
               c.status AS challenger_status,
               c.side_a_probability AS challenger_side_a_probability,
               pm.primary_reason, pm.reasons_json, pm.actual_performance_json,
               n.home_score, n.away_score, n.home_won, n.resolved_at
        FROM shadow_prediction_runs r
        JOIN prediction_records p ON p.prediction_id=r.prediction_id
        JOIN normalized_match_outcomes n
          ON n.event_id=r.event_id AND n.match_id=r.match_id
        LEFT JOIN shadow_challenger_predictions c
          ON c.shadow_run_id=r.shadow_run_id
        LEFT JOIN prediction_postmortems pm ON pm.shadow_run_id=r.shadow_run_id
        WHERE r.status='PREDICTED'
        ORDER BY n.resolved_at DESC, r.shadow_run_id DESC
        """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (max(1, int(limit)),)
    rows = conn.execute(query, params).fetchall()
    evaluations = [_evaluation(dict(row)) for row in rows]
    return {
        "resolvedPredictions": total_resolved,
        "returnedEvaluations": len(evaluations),
        "evaluations": evaluations,
        "methodology": {
            "probabilityError": (
                "Absolute distance between the frozen probability assigned to the "
                "eventual winner and 100%."
            ),
            "brierScore": "Squared probability error; lower is better.",
            "explanations": (
                "Explanations compare frozen pre-match feature values. They describe "
                "what the model believed, not a proven cause of the result."
            ),
        },
    }


def _evaluation(row: dict[str, Any]) -> dict[str, Any]:
    probability_a = float(row["side_a_probability"])
    outcome = int(row["home_won"])
    winner_probability = probability_a if outcome else 1.0 - probability_a
    predicted_a = probability_a >= 0.5
    correct = predicted_a == bool(outcome)
    feature_summary = _feature_summary(row.get("features_json"))
    challenger_probability = row.get("challenger_side_a_probability")
    challenger = None
    if row.get("challenger_status") == "PREDICTED" and challenger_probability is not None:
        challenger_a = float(challenger_probability)
        challenger_winner_probability = challenger_a if outcome else 1.0 - challenger_a
        challenger = {
            "modelVersion": row.get("challenger_model_version"),
            "sideAProbability": round(challenger_a, 6),
            "correct": (challenger_a >= 0.5) == bool(outcome),
            "winnerProbability": round(challenger_winner_probability, 6),
            "brierScore": round((challenger_a - outcome) ** 2, 6),
        }
    return {
        "shadowRunId": row["shadow_run_id"],
        "eventId": row["event_id"],
        "matchId": row["match_id"],
        "recordedAt": row["recorded_at"],
        "scheduledStartAt": row["scheduled_start_at"],
        "timingBasis": row["timing_basis"],
        "evidenceTier": row["evidence_tier"],
        "sideAPlayerIds": _json_list(row.get("side_a_player_ids_json")),
        "sideBPlayerIds": _json_list(row.get("side_b_player_ids_json")),
        "sideAProbability": round(probability_a, 6),
        "sideBProbability": round(1.0 - probability_a, 6),
        "predictedWinner": "SIDE_A" if predicted_a else "SIDE_B",
        "actualWinner": "SIDE_A" if outcome else "SIDE_B",
        "correct": correct,
        "homeScore": int(row["home_score"]),
        "awayScore": int(row["away_score"]),
        "actualMargin": abs(int(row["home_score"]) - int(row["away_score"])),
        "winnerProbability": round(winner_probability, 6),
        "probabilityError": round(1.0 - winner_probability, 6),
        "brierScore": round((probability_a - outcome) ** 2, 6),
        "logLoss": round(
            -(outcome * math.log(max(probability_a, 1e-15))
              + (1 - outcome) * math.log(max(1.0 - probability_a, 1e-15))),
            6,
        ),
        "resolvedAt": row["resolved_at"],
        "featureSummary": feature_summary,
        "explanation": _explanation(correct, predicted_a, feature_summary),
        "postmortem": {
            "primaryReason": row.get("primary_reason"),
            "reasons": _json_list(row.get("reasons_json")),
            "actualPerformance": _json_object(row.get("actual_performance_json")),
            "learningStatus": "CANDIDATE_TRAINING_POOL",
        } if row.get("primary_reason") else None,
        "challenger": challenger,
    }


def _feature_summary(raw: str | None) -> dict[str, Any]:
    try:
        features = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        features = {}
    deltas = features.get("deltasAminusB") or {}
    return {
        "predictivePprDelta": _number(deltas.get("predictivePpr")),
        "calculatedPprDelta": _number(deltas.get("calculatedPpr")),
        "roundsDelta": _number(deltas.get("rounds")),
        "modelReady": bool(features.get("modelReady")),
    }


def _explanation(
    correct: bool,
    predicted_a: bool,
    summary: dict[str, Any],
) -> dict[str, Any]:
    ppr_delta = summary.get("predictivePprDelta")
    if ppr_delta is None:
        headline = "Limited pre-match evidence"
        detail = "The frozen record does not contain a comparable predictive PPR advantage."
    else:
        favored_by_ppr = "SIDE_A" if ppr_delta >= 0 else "SIDE_B"
        magnitude = abs(float(ppr_delta))
        headline = (
            "Expected advantage held"
            if correct
            else "Expected advantage did not hold"
        )
        detail = (
            f"The model's primary frozen signal favored {favored_by_ppr} by "
            f"{magnitude:.2f} expected PPR. "
            + (
                "The final result agreed with that direction."
                if correct
                else "The final result went in the opposite direction."
            )
        )
    return {
        "headline": headline,
        "detail": detail,
        "classification": "SUPPORTED" if correct else "UPSET_OR_MODEL_MISS",
        "caveat": (
            "This is an attribution summary, not proof that one factor caused the result."
        ),
    }


def _json_list(raw: str | None) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _number(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None
