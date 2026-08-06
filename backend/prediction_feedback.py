from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from statistics import mean
from typing import Any


REVIEW_VERSION = "prediction-postmortem-v1"


def initialize_feedback_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS prediction_postmortems (
            shadow_run_id INTEGER PRIMARY KEY,
            review_version TEXT NOT NULL,
            correct INTEGER NOT NULL,
            primary_reason TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            actual_performance_json TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY(shadow_run_id) REFERENCES shadow_prediction_runs(shadow_run_id)
        );
        CREATE TABLE IF NOT EXISTS prediction_learning_examples (
            shadow_run_id INTEGER PRIMARY KEY,
            model_version TEXT NOT NULL,
            frozen_at TEXT NOT NULL,
            features_json TEXT NOT NULL,
            outcome INTEGER NOT NULL,
            postmortem_json TEXT NOT NULL,
            training_status TEXT NOT NULL DEFAULT 'CANDIDATE_TRAINING_POOL',
            created_at TEXT NOT NULL,
            FOREIGN KEY(shadow_run_id) REFERENCES shadow_prediction_runs(shadow_run_id)
        );
        """
    )
    conn.commit()


def review_resolved_prediction(conn: sqlite3.Connection, shadow_run_id: int) -> dict[str, Any] | None:
    initialize_feedback_schema(conn)
    existing = conn.execute(
        "SELECT * FROM prediction_postmortems WHERE shadow_run_id=?", (int(shadow_run_id),)
    ).fetchone()
    if existing:
        return _stored(existing)
    row = conn.execute(
        """
        SELECT r.shadow_run_id, r.event_id, r.match_id, r.model_version, r.recorded_at,
               p.side_a_probability, p.features_json, o.side_a_won,
               n.home_score, n.away_score
        FROM shadow_prediction_runs r
        JOIN prediction_records p ON p.prediction_id=r.prediction_id
        JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
        LEFT JOIN normalized_match_outcomes n
          ON n.event_id=r.event_id AND n.match_id=r.match_id
        WHERE r.shadow_run_id=?
        """,
        (int(shadow_run_id),),
    ).fetchone()
    if row is None:
        return None
    features = _json(row["features_json"])
    probability = float(row["side_a_probability"])
    predicted_a = probability >= 0.5
    actual_a = bool(row["side_a_won"])
    correct = predicted_a == actual_a
    actual = _actual_performance(conn, str(row["event_id"]), str(row["match_id"]))
    favored_key = "sideA" if predicted_a else "sideB"
    underdog_key = "sideB" if predicted_a else "sideA"
    favored = actual.get(favored_key) or {}
    underdog = actual.get(underdog_key) or {}
    favored_expected = _nested_number(features, favored_key, "aggregate", "predictivePpr")
    underdog_expected = _nested_number(features, underdog_key, "aggregate", "predictivePpr")
    reasons: list[dict[str, Any]] = []
    if not correct:
        if favored.get("ppr") is not None and favored_expected is not None:
            delta = float(favored["ppr"]) - favored_expected
            if delta <= -0.35:
                reasons.append(_reason("FAVORITE_UNDERPERFORMED", abs(delta), f"Favored side scored {abs(delta):.2f} PPR below its frozen expectation."))
        if underdog.get("ppr") is not None and underdog_expected is not None:
            delta = float(underdog["ppr"]) - underdog_expected
            if delta >= 0.35:
                reasons.append(_reason("UNDERDOG_OUTPERFORMED", delta, f"Underdog scored {delta:.2f} PPR above its frozen expectation."))
        if int(favored.get("largeSwingsConceded") or 0) >= 2:
            reasons.append(_reason("LARGE_SWINGS_CONCEDED", float(favored["largeSwingsConceded"]), f"Favored side conceded {favored['largeSwingsConceded']} rounds of five or more net points."))
        margin = abs(int(row["home_score"] or 0) - int(row["away_score"] or 0))
        if margin <= 3:
            reasons.append(_reason("CLOSE_MATCH_VARIANCE", 3.0 - margin, f"The upset margin was only {margin} points."))
        if not reasons:
            reasons.append(_reason("UNEXPLAINED_MODEL_MISS", 0.0, "Available match statistics do not isolate a reliable cause."))
    else:
        reasons.append(_reason("EXPECTED_ADVANTAGE_HELD", max(probability, 1 - probability) - 0.5, "The result followed the frozen model direction."))
    reasons.sort(key=lambda item: float(item["impact"]), reverse=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    review = {
        "reviewVersion": REVIEW_VERSION,
        "correct": correct,
        "primaryReason": reasons[0]["code"],
        "reasons": reasons,
        "actualPerformance": actual,
        "caveat": "Attributions identify measurable contributors, not certain causes.",
    }
    conn.execute(
        "INSERT INTO prediction_postmortems VALUES (?, ?, ?, ?, ?, ?, ?)",
        (int(shadow_run_id), REVIEW_VERSION, int(correct), review["primaryReason"], json.dumps(reasons), json.dumps(actual), generated_at),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO prediction_learning_examples(
          shadow_run_id, model_version, frozen_at, features_json, outcome,
          postmortem_json, training_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'CANDIDATE_TRAINING_POOL', ?)
        """,
        (int(shadow_run_id), row["model_version"], row["recorded_at"], row["features_json"], int(actual_a), json.dumps(review), generated_at),
    )
    conn.commit()
    return review


def backfill_prediction_feedback(conn: sqlite3.Connection, limit: int = 250) -> dict[str, int]:
    initialize_feedback_schema(conn)
    rows = conn.execute(
        """
        SELECT r.shadow_run_id FROM shadow_prediction_runs r
        JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
        LEFT JOIN prediction_postmortems p ON p.shadow_run_id=r.shadow_run_id
        WHERE p.shadow_run_id IS NULL ORDER BY r.shadow_run_id LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()
    created = sum(review_resolved_prediction(conn, int(row[0])) is not None for row in rows)
    return {"eligible": len(rows), "created": created}


def prediction_learning_report(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_feedback_schema(conn)
    total = int(conn.execute("SELECT COUNT(*) FROM prediction_learning_examples").fetchone()[0])
    incorrect = int(conn.execute(
        "SELECT COUNT(*) FROM prediction_postmortems WHERE correct=0"
    ).fetchone()[0])
    reasons = [dict(row) for row in conn.execute(
        """
        SELECT primary_reason AS reason, COUNT(*) AS predictions
        FROM prediction_postmortems
        GROUP BY primary_reason ORDER BY predictions DESC, primary_reason
        """
    ).fetchall()]
    status_rows = [dict(row) for row in conn.execute(
        """
        SELECT training_status AS status, COUNT(*) AS examples
        FROM prediction_learning_examples GROUP BY training_status
        """
    ).fetchall()]
    minimum = 500
    return {
        "learningExamples": total,
        "incorrectPredictions": incorrect,
        "correctPredictions": max(total - incorrect, 0),
        "missRate": round(incorrect / total, 6) if total else None,
        "reasonDistribution": reasons,
        "trainingStatuses": status_rows,
        "promotionGate": {
            "minimumCommonResolvedMatches": minimum,
            "currentExamples": total,
            "remaining": max(minimum - total, 0),
            "sampleThresholdMet": total >= minimum,
            "requiresAccuracyImprovement": True,
            "requiresBrierImprovement": True,
            "requiresLogLossImprovement": True,
            "requiresTemporalStability": True,
            "eligibleForRetrainingReview": total >= minimum,
        },
        "learningPolicy": (
            "Resolved frozen predictions enter the candidate pool. Model weights change "
            "only in a batch retraining run that passes chronological validation and a later holdout."
        ),
    }


def _actual_performance(conn: sqlite3.Connection, event_id: str, match_id: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT UPPER(COALESCE(team_side,'')) side, player_id,
               COUNT(*) rounds, SUM(COALESCE(gross_points,0)) gross,
               SUM(CASE WHEN UPPER(COALESCE(round_result,''))='L' THEN 1 ELSE 0 END) losses
        FROM player_rounds WHERE event_id=? AND match_id=?
        GROUP BY UPPER(COALESCE(team_side,'')), player_id
        """,
        (event_id, match_id),
    ).fetchall()
    output: dict[str, Any] = {}
    for side_name, side_code in (("sideA", "HOME"), ("sideB", "AWAY")):
        selected = [row for row in rows if str(row["side"]) == side_code and int(row["rounds"] or 0)]
        pprs = [float(row["gross"]) / int(row["rounds"]) for row in selected]
        loss_rates = [float(row["losses"]) / int(row["rounds"]) for row in selected]
        swings = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT game_id, round_no, SUM(COALESCE(net_points,0)) net
              FROM player_rounds WHERE event_id=? AND match_id=? AND UPPER(COALESCE(team_side,''))=?
              GROUP BY game_id, round_no HAVING net<=-5
            )
            """,
            (event_id, match_id, side_code),
        ).fetchone()[0]
        output[side_name] = {
            "ppr": round(mean(pprs), 4) if pprs else None,
            "roundLossRate": round(mean(loss_rates), 4) if loss_rates else None,
            "largeSwingsConceded": int(swings or 0),
            "players": len(selected),
        }
    return output


def _reason(code: str, impact: float, detail: str) -> dict[str, Any]:
    return {"code": code, "impact": round(float(impact), 4), "detail": detail}


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _nested_number(source: dict[str, Any], *keys: str) -> float | None:
    value: Any = source
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stored(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "reviewVersion": row["review_version"], "correct": bool(row["correct"]),
        "primaryReason": row["primary_reason"], "reasons": json.loads(row["reasons_json"]),
        "actualPerformance": json.loads(row["actual_performance_json"]),
    }
