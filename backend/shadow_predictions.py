from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable

from baseline_predictions import create_prediction, initialize_prediction_schema
from round_loss_recent_challenger import (
    MODEL_VERSION as CHALLENGER_MODEL_VERSION,
    PROFILE_FACTOR_POLICY,
    score_round_loss_recent_challenger,
)
from candidate_factor_snapshots import (
    build_candidate_factor_snapshot,
    initialize_candidate_snapshot_schema,
    persist_candidate_factor_snapshot,
)


SHADOW_MODEL_VERSION = "fitted-ppr-logistic-v2-acl-assisted"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_shadow_schema(conn: sqlite3.Connection) -> None:
    initialize_prediction_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS shadow_prediction_runs (
            shadow_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id INTEGER NOT NULL UNIQUE,
            event_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            model_version TEXT NOT NULL,
            status TEXT NOT NULL,
            abstention_reason TEXT,
            scheduled_start_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            timing_basis TEXT NOT NULL DEFAULT 'SCHEDULED_MATCH_START',
            FOREIGN KEY(prediction_id) REFERENCES prediction_records(prediction_id),
            UNIQUE(event_id, match_id, model_version),
            CHECK(status IN ('PREDICTED', 'ABSTAINED'))
        );

        CREATE TABLE IF NOT EXISTS shadow_outcomes (
            outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shadow_run_id INTEGER NOT NULL UNIQUE,
            side_a_won INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_payload_id INTEGER,
            resolved_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            FOREIGN KEY(shadow_run_id)
                REFERENCES shadow_prediction_runs(shadow_run_id),
            CHECK(side_a_won IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS shadow_challenger_predictions (
            challenger_prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shadow_run_id INTEGER NOT NULL,
            model_version TEXT NOT NULL,
            status TEXT NOT NULL,
            abstention_reason TEXT,
            side_a_probability REAL,
            side_b_probability REAL,
            feature_hash TEXT NOT NULL,
            features_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            FOREIGN KEY(shadow_run_id)
                REFERENCES shadow_prediction_runs(shadow_run_id),
            UNIQUE(shadow_run_id, model_version),
            CHECK(status IN ('PREDICTED', 'ABSTAINED'))
        );

        CREATE INDEX IF NOT EXISTS idx_shadow_pending
            ON shadow_prediction_runs(status, scheduled_start_at);
        """
    )
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(shadow_prediction_runs)").fetchall()
    }
    if "timing_basis" not in columns:
        conn.execute(
            "ALTER TABLE shadow_prediction_runs ADD COLUMN timing_basis TEXT NOT NULL DEFAULT 'SCHEDULED_MATCH_START'"
        )
    initialize_candidate_snapshot_schema(conn)
    conn.commit()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def create_shadow_prediction(
    conn: sqlite3.Connection,
    *,
    event_id: str | int,
    match_id: str | int,
    side_a_player_ids: Iterable[int],
    side_b_player_ids: Iterable[int],
    scheduled_start_at: str,
    recorded_at: str | None = None,
    window_days: int | None = 365,
    pregame_status_verified: bool = False,
    timing_basis: str = "SCHEDULED_MATCH_START",
) -> dict[str, Any]:
    initialize_shadow_schema(conn)
    side_a_player_ids = list(side_a_player_ids)
    side_b_player_ids = list(side_b_player_ids)
    recorded_at = recorded_at or utc_now()
    if (
        _parse_time(recorded_at) >= _parse_time(scheduled_start_at)
        and not pregame_status_verified
    ):
        raise ValueError("Shadow predictions must be recorded before scheduled start")
    existing = conn.execute(
        """
        SELECT r.*, p.side_a_probability, p.side_b_probability,
               p.evidence_tier, p.feature_hash
        FROM shadow_prediction_runs r
        JOIN prediction_records p ON p.prediction_id=r.prediction_id
        WHERE r.event_id=? AND r.match_id=? AND r.model_version=?
        """,
        (str(event_id), str(match_id), SHADOW_MODEL_VERSION),
    ).fetchone()
    if existing:
        return dict(existing)

    prediction = create_prediction(
        conn,
        side_a_player_ids=side_a_player_ids,
        side_b_player_ids=side_b_player_ids,
        cutoff_at=recorded_at,
        model_version=SHADOW_MODEL_VERSION,
        event_id=event_id,
        match_id=match_id,
    )
    reason = prediction.get("reason")
    cursor = conn.execute(
        """
        INSERT INTO shadow_prediction_runs(
            prediction_id, event_id, match_id, model_version, status,
            abstention_reason, scheduled_start_at, recorded_at, timing_basis
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prediction["predictionId"],
            str(event_id),
            str(match_id),
            SHADOW_MODEL_VERSION,
            prediction["status"],
            reason,
            scheduled_start_at,
            recorded_at,
            timing_basis,
        ),
    )
    shadow_run_id = int(cursor.lastrowid)
    stored = conn.execute(
        "SELECT feature_hash, features_json FROM prediction_records WHERE prediction_id=?",
        (prediction["predictionId"],),
    ).fetchone()
    matchup = json.loads(stored["features_json"])
    challenger = score_round_loss_recent_challenger(matchup)
    conn.execute(
        """
        INSERT INTO shadow_challenger_predictions(
            shadow_run_id, model_version, status, abstention_reason,
            side_a_probability, side_b_probability, feature_hash,
            features_json, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            shadow_run_id,
            CHALLENGER_MODEL_VERSION,
            challenger["status"],
            challenger.get("reason"),
            challenger.get("sideAProbability"),
            challenger.get("sideBProbability"),
            stored["feature_hash"],
            stored["features_json"],
            recorded_at,
        ),
    )
    candidate_snapshot = build_candidate_factor_snapshot(
        conn,
        side_a_player_ids=side_a_player_ids,
        side_b_player_ids=side_b_player_ids,
        cutoff_at=recorded_at,
    )
    persist_candidate_factor_snapshot(
        conn,
        shadow_run_id=shadow_run_id,
        snapshot=candidate_snapshot,
        recorded_at=recorded_at,
    )
    conn.commit()
    return {
        **prediction,
        "shadowRunId": shadow_run_id,
        "challenger": challenger,
        "scheduledStartAt": scheduled_start_at,
        "recordedAt": recorded_at,
        "mode": "SHADOW",
        "timingBasis": timing_basis,
        "candidateFactorSnapshot": {
            "snapshotVersion": candidate_snapshot["snapshotVersion"],
            "completenessRate": candidate_snapshot["completenessRate"],
            "availableFactors": candidate_snapshot["availableFactors"],
            "expectedFactors": candidate_snapshot["expectedFactors"],
            "missingReasons": candidate_snapshot["missingReasons"],
        },
    }


def record_shadow_outcome(
    conn: sqlite3.Connection,
    *,
    shadow_run_id: int,
    side_a_won: bool | int,
    source: str,
    resolved_at: str,
    source_payload_id: int | None = None,
) -> int:
    initialize_shadow_schema(conn)
    run = conn.execute(
        "SELECT scheduled_start_at FROM shadow_prediction_runs WHERE shadow_run_id=?",
        (shadow_run_id,),
    ).fetchone()
    if run is None:
        raise ValueError("Unknown shadow run")
    if _parse_time(resolved_at) < _parse_time(run["scheduled_start_at"]):
        raise ValueError("Outcome cannot be resolved before scheduled start")
    cursor = conn.execute(
        """
        INSERT INTO shadow_outcomes(
            shadow_run_id, side_a_won, source, source_payload_id,
            resolved_at, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            shadow_run_id,
            int(bool(side_a_won)),
            source,
            source_payload_id,
            resolved_at,
            utc_now(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def shadow_performance_report(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_shadow_schema(conn)
    runs = conn.execute(
        "SELECT status, abstention_reason FROM shadow_prediction_runs"
    ).fetchall()
    scored = conn.execute(
        """
        SELECT p.side_a_probability AS probability, o.side_a_won AS outcome
        FROM shadow_prediction_runs r
        JOIN prediction_records p ON p.prediction_id=r.prediction_id
        JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
        WHERE r.status='PREDICTED'
        """
    ).fetchall()
    probabilities = [
        (float(row["probability"]), int(row["outcome"])) for row in scored
    ]
    predicted = sum(row["status"] == "PREDICTED" for row in runs)
    abstentions = Counter(
        row["abstention_reason"] or "UNSPECIFIED"
        for row in runs
        if row["status"] == "ABSTAINED"
    )
    baseline_metrics = _metrics(probabilities)
    challenger_rows = conn.execute(
        """
        SELECT c.side_a_probability AS probability, o.side_a_won AS outcome
        FROM shadow_challenger_predictions c
        JOIN shadow_outcomes o ON o.shadow_run_id=c.shadow_run_id
        WHERE c.status='PREDICTED' AND c.model_version=?
        """,
        (CHALLENGER_MODEL_VERSION,),
    ).fetchall()
    challenger_probabilities = [
        (float(row["probability"]), int(row["outcome"]))
        for row in challenger_rows
    ]
    common_rows = conn.execute(
        """
        SELECT p.side_a_probability AS baseline_probability,
               c.side_a_probability AS challenger_probability,
               o.side_a_won AS outcome
        FROM shadow_prediction_runs r
        JOIN prediction_records p ON p.prediction_id=r.prediction_id
        JOIN shadow_challenger_predictions c ON c.shadow_run_id=r.shadow_run_id
        JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
        WHERE r.status='PREDICTED' AND c.status='PREDICTED'
          AND c.model_version=?
        """,
        (CHALLENGER_MODEL_VERSION,),
    ).fetchall()
    common_baseline = [
        (float(row["baseline_probability"]), int(row["outcome"]))
        for row in common_rows
    ]
    common_challenger = [
        (float(row["challenger_probability"]), int(row["outcome"]))
        for row in common_rows
    ]
    return {
        "modelVersion": SHADOW_MODEL_VERSION,
        "challengerModelVersion": CHALLENGER_MODEL_VERSION,
        "mode": "SHADOW",
        "totalRuns": len(runs),
        "predictedRuns": predicted,
        "abstainedRuns": len(runs) - predicted,
        "coverageRate": round(predicted / len(runs), 6) if runs else 0,
        "resolvedPredictions": len(probabilities),
        **baseline_metrics,
        "models": {
            SHADOW_MODEL_VERSION: baseline_metrics,
            CHALLENGER_MODEL_VERSION: _metrics(challenger_probabilities),
        },
        "commonSample": {
            "resolvedPredictions": len(common_rows),
            "baseline": _metrics(common_baseline),
            "challenger": _metrics(common_challenger),
            "leader": _leader(common_baseline, common_challenger),
        },
        "challengerFactorPolicy": PROFILE_FACTOR_POLICY,
        "abstentionReasons": dict(abstentions),
        "historicalReference": {
            "accuracy": 0.631436,
            "coverageRate": 0.68972,
            "logLoss": 0.649378,
            "brierScore": 0.22811,
        },
    }


def _metrics(rows: list[tuple[float, int]]) -> dict[str, Any]:
    if not rows:
        return {
            "resolvedPredictions": 0, "accuracy": None,
            "logLoss": None, "brierScore": None,
        }
    return {
        "resolvedPredictions": len(rows),
        "accuracy": round(mean(
            (probability >= 0.5) == bool(outcome)
            for probability, outcome in rows
        ), 6),
        "logLoss": round(mean(
            -(outcome * math.log(max(probability, 1e-15))
              + (1 - outcome) * math.log(max(1 - probability, 1e-15)))
            for probability, outcome in rows
        ), 6),
        "brierScore": round(mean(
            (probability - outcome) ** 2
            for probability, outcome in rows
        ), 6),
    }


def _leader(
    baseline: list[tuple[float, int]],
    challenger: list[tuple[float, int]],
) -> str:
    if not baseline or len(baseline) != len(challenger):
        return "INSUFFICIENT_COMMON_SAMPLE"
    baseline_brier = _metrics(baseline)["brierScore"]
    challenger_brier = _metrics(challenger)["brierScore"]
    if challenger_brier < baseline_brier:
        return CHALLENGER_MODEL_VERSION
    if baseline_brier < challenger_brier:
        return SHADOW_MODEL_VERSION
    return "TIED"
