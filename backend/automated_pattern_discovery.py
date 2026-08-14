"""Cutoff-safe automated feature discovery for the research lab.

This worker proposes reproducible nonlinear transformations using development
data, selects them on chronological validation data, and only then scores the
locked candidates on the untouched holdout.  It never changes production
prediction weights.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from statistics import median
from typing import Any, Callable

from chronological_evaluation import historical_matchups
from historical_archive_backtest import (
    _cutoff_safe_examples,
    _fit_logistic,
    _metrics,
    _paired_comparison,
    _predict,
)


DISCOVERY_VERSION = "automated-pattern-discovery-v1"
DISCOVERY_DB_PATH = os.path.join(
    os.environ.get("DATA_DIR", "data"), "research", "automated_discovery.db"
)
BASE_FEATURES = (
    "pprDelta", "fourBaggerDelta", "bagsInDelta", "adjustedPprDelta",
    "recentFormDelta", "roundLossRateDelta", "recentRoundLossDelta",
    "teamSkillGapDelta", "venueEffectDelta", "formatEffectDelta",
)
MAX_LOCKED_CANDIDATES = 12


def discovery_status(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    owns_connection = conn is None
    if conn is None:
        conn = _state_db()
    try:
        state = conn.execute(
            "SELECT * FROM automated_discovery_state WHERE state_id=1"
        ).fetchone()
        candidates = conn.execute(
            """
            SELECT candidate_key, name, family, status, definition_json,
                   validation_accuracy, validation_brier, holdout_accuracy,
                   holdout_brier, accuracy_delta, brier_improvement,
                   evaluated_matchups, generated_at
            FROM automated_discovery_candidates
            WHERE discovery_version=?
            ORDER BY CASE status WHEN 'HOLDOUT_PROMISING' THEN 0 WHEN 'HOLDOUT_SCORED' THEN 1 ELSE 2 END,
                     COALESCE(accuracy_delta,-99) DESC, COALESCE(brier_improvement,-99) DESC
            LIMIT 20
            """,
            (DISCOVERY_VERSION,),
        ).fetchall()
    except sqlite3.Error:
        state, candidates = None, []
    result = {
        "version": DISCOVERY_VERSION,
        "status": str(state["status"] if state else "WAITING"),
        "phase": str(state["phase"] if state else "WAITING_FOR_FIRST_RUN"),
        "runId": state["run_id"] if state else None,
        "ledgerSignature": state["ledger_signature"] if state else None,
        "startedAt": state["started_at"] if state else None,
        "updatedAt": state["updated_at"] if state else None,
        "completedAt": state["completed_at"] if state else None,
        "examplesScanned": int((state["examples_scanned"] if state else 0) or 0),
        "candidatesGenerated": int((state["candidates_generated"] if state else 0) or 0),
        "candidatesValidated": int((state["candidates_validated"] if state else 0) or 0),
        "candidatesLocked": int((state["candidates_locked"] if state else 0) or 0),
        "candidatesHoldoutScored": int((state["candidates_holdout_scored"] if state else 0) or 0),
        "lastCandidate": state["last_candidate"] if state else None,
        "lastError": state["last_error"] if state else None,
        "candidates": [
            {
                **dict(row),
                "definition": _json(row["definition_json"]),
            }
            for row in candidates
        ],
        "safety": {
            "productionWeightsChanged": False,
            "selectionPolicy": "GENERATE_ON_DEVELOPMENT_SELECT_ON_VALIDATION_SCORE_LOCKED_ON_HOLDOUT",
        },
    }
    if owns_connection:
        conn.close()
    return result


def run_discovery(conn: sqlite3.Connection, *, force: bool = False) -> dict[str, Any]:
    state_conn = _state_db()
    _init_schema(state_conn)
    signature = _ledger_signature(conn)
    state = state_conn.execute("SELECT * FROM automated_discovery_state WHERE state_id=1").fetchone()
    if state and state["status"] == "COMPLETE" and state["ledger_signature"] == signature and not force:
        result = discovery_status(state_conn)
        state_conn.close()
        return result

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    _set_state(state_conn, status="RUNNING", phase="BUILDING_CUTOFF_SAFE_DATASET", run_id=run_id,
               ledger_signature=signature, started_at=_now(), completed_at=None, last_error=None,
               examples_scanned=0, candidates_generated=0, candidates_validated=0,
               candidates_locked=0, candidates_holdout_scored=0, last_candidate=None)
    try:
        conn.execute("PRAGMA query_only=ON")
        examples = _cutoff_safe_examples(conn, historical_matchups(conn))
        dates = sorted({str(row["eventDate"]) for row in examples})
        if len(dates) < 3:
            raise RuntimeError("Not enough chronological event dates for discovery")
        validation_index = min(max(int(len(dates) * 0.60), 1), len(dates) - 2)
        holdout_index = min(max(int(len(dates) * 0.80), validation_index + 1), len(dates) - 1)
        validation_start, holdout_start = dates[validation_index], dates[holdout_index]
        development = [row for row in examples if row["eventDate"] < validation_start]
        validation = [row for row in examples if validation_start <= row["eventDate"] < holdout_start]
        holdout = [row for row in examples if row["eventDate"] >= holdout_start]
        _set_state(state_conn, phase="GENERATING_CANDIDATES", examples_scanned=len(examples))

        definitions = _candidate_definitions(development)
        _set_state(state_conn, candidates_generated=len(definitions), phase="VALIDATING_CANDIDATES")
        baseline_model = _fit_logistic(development, ("pprDelta",))
        baseline_validation = _predict(validation, baseline_model)
        baseline_holdout = _predict(holdout, baseline_model)
        baseline_validation_metrics = _metrics(baseline_validation, len(validation))
        baseline_holdout_metrics = _metrics(baseline_holdout, len(holdout))

        validated: list[dict[str, Any]] = []
        for index, definition in enumerate(definitions, start=1):
            _set_state(state_conn, last_candidate=definition["name"], candidates_validated=index - 1)
            transformed_development = _apply_definition(development, definition)
            transformed_validation = _apply_definition(validation, definition)
            feature_names = ("pprDelta", definition["key"])
            model = _fit_logistic(transformed_development, feature_names)
            predictions = _predict(transformed_validation, model)
            metrics = _metrics(predictions, len(validation))
            score = _selection_score(metrics, baseline_validation_metrics)
            validated.append({"definition": definition, "model": model, "validation": metrics, "score": score})
        _set_state(state_conn, candidates_validated=len(validated), phase="LOCKING_BEFORE_HOLDOUT")

        locked = sorted(validated, key=lambda row: row["score"], reverse=True)[:MAX_LOCKED_CANDIDATES]
        _set_state(state_conn, candidates_locked=len(locked), phase="SCORING_UNTOUCHED_HOLDOUT")
        state_conn.execute("DELETE FROM automated_discovery_candidates WHERE discovery_version=?", (DISCOVERY_VERSION,))
        for index, row in enumerate(locked, start=1):
            definition = row["definition"]
            holdout_rows = _apply_definition(holdout, definition)
            predictions = _predict(holdout_rows, row["model"])
            metrics = _metrics(predictions, len(holdout))
            paired = _paired_comparison(baseline_holdout, predictions) or {}
            accuracy_delta = _num(metrics.get("accuracy")) - _num(baseline_holdout_metrics.get("accuracy"))
            brier_improvement = _num(baseline_holdout_metrics.get("brierScore")) - _num(metrics.get("brierScore"))
            promising = accuracy_delta > 0 and brier_improvement > 0
            state_conn.execute(
                """
                INSERT INTO automated_discovery_candidates(
                  discovery_version,candidate_key,name,family,status,definition_json,
                  validation_accuracy,validation_brier,holdout_accuracy,holdout_brier,
                  accuracy_delta,brier_improvement,evaluated_matchups,comparison_json,generated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (DISCOVERY_VERSION, definition["key"], definition["name"], definition["family"],
                 "HOLDOUT_PROMISING" if promising else "HOLDOUT_SCORED", json.dumps(definition),
                 row["validation"].get("accuracy"), row["validation"].get("brierScore"),
                 metrics.get("accuracy"), metrics.get("brierScore"), accuracy_delta,
                 brier_improvement, metrics.get("evaluatedMatchups"), json.dumps(paired), _now()),
            )
            state_conn.commit()
            _set_state(state_conn, candidates_holdout_scored=index, last_candidate=definition["name"])
        _set_state(state_conn, status="COMPLETE", phase="COMPLETE", completed_at=_now(), last_candidate=None)
    except Exception as exc:
        _set_state(state_conn, status="FAILED", phase="FAILED", last_error=str(exc), completed_at=_now())
        state_conn.close()
        raise
    result = discovery_status(state_conn)
    state_conn.close()
    return result


def start_automated_discovery_worker(db_factory: Callable[[], Any], *, initial_delay: int = 90,
                                     interval_seconds: int = 6 * 60 * 60) -> threading.Thread:
    def worker() -> None:
        time.sleep(initial_delay)
        while True:
            try:
                with db_factory() as conn:
                    result = run_discovery(conn)
                print(f"Automated discovery: {result['status']} · {result['candidatesHoldoutScored']} locked candidates scored", flush=True)
            except Exception as exc:
                print(f"Automated discovery failed: {exc}", flush=True)
            time.sleep(interval_seconds)
    thread = threading.Thread(target=worker, daemon=True, name="automated-pattern-discovery")
    thread.start()
    return thread


def _candidate_definitions(development: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for feature in BASE_FEATURES[1:]:
        values = [abs(float(row["features"].get(feature) or 0)) for row in development]
        threshold = median(values) if values else 0.0
        definitions.extend([
            {"key": f"auto_{feature}_linear", "name": f"PPR + {feature}", "family": "LINEAR", "source": feature},
            {"key": f"auto_{feature}_curve", "name": f"Nonlinear {feature}", "family": "SIGNED_CURVE", "source": feature},
            {"key": f"auto_{feature}_ppr_context", "name": f"PPR × {feature} magnitude", "family": "PPR_CONTEXT", "source": feature},
            {"key": f"auto_{feature}_threshold", "name": f"Large {feature} cohort", "family": "THRESHOLD", "source": feature, "threshold": threshold},
        ])
    return definitions


def _apply_definition(rows: list[dict[str, Any]], definition: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        copied = {**row, "features": dict(row["features"])}
        source = float(copied["features"].get(definition["source"]) or 0)
        ppr = float(copied["features"].get("pprDelta") or 0)
        family = definition["family"]
        if family == "LINEAR":
            value = source
        elif family == "SIGNED_CURVE":
            value = source * abs(source)
        elif family == "PPR_CONTEXT":
            value = ppr * abs(source)
        else:
            value = math.copysign(1.0, source) if abs(source) >= float(definition.get("threshold") or 0) and source else 0.0
        copied["features"][definition["key"]] = value
        output.append(copied)
    return output


def _selection_score(metrics: dict[str, Any], baseline: dict[str, Any]) -> float:
    return ((_num(metrics.get("accuracy")) - _num(baseline.get("accuracy"))) * 2.0
            + (_num(baseline.get("brierScore")) - _num(metrics.get("brierScore"))))


def _ledger_signature(conn: sqlite3.Connection) -> str:
    return f"games:{conn.execute('SELECT COUNT(*) FROM games').fetchone()[0]}:rounds:{conn.execute('SELECT COUNT(*) FROM player_rounds').fetchone()[0]}"


def _set_state(conn: sqlite3.Connection, **values: Any) -> None:
    allowed = {"status", "phase", "run_id", "ledger_signature", "started_at", "updated_at", "completed_at", "examples_scanned", "candidates_generated", "candidates_validated", "candidates_locked", "candidates_holdout_scored", "last_candidate", "last_error"}
    values = {key: value for key, value in values.items() if key in allowed}
    values["updated_at"] = _now()
    columns = list(values)
    conn.execute(
        f"INSERT INTO automated_discovery_state(state_id,{','.join(columns)}) VALUES (1,{','.join('?' for _ in columns)}) ON CONFLICT(state_id) DO UPDATE SET "
        + ",".join(f"{column}=excluded.{column}" for column in columns),
        tuple(values[column] for column in columns),
    )
    conn.commit()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS automated_discovery_state(
      state_id INTEGER PRIMARY KEY CHECK(state_id=1), status TEXT NOT NULL DEFAULT 'WAITING',
      phase TEXT NOT NULL DEFAULT 'WAITING_FOR_FIRST_RUN', run_id TEXT, ledger_signature TEXT,
      started_at TEXT, updated_at TEXT, completed_at TEXT, examples_scanned INTEGER NOT NULL DEFAULT 0,
      candidates_generated INTEGER NOT NULL DEFAULT 0, candidates_validated INTEGER NOT NULL DEFAULT 0,
      candidates_locked INTEGER NOT NULL DEFAULT 0, candidates_holdout_scored INTEGER NOT NULL DEFAULT 0,
      last_candidate TEXT, last_error TEXT
    );
    CREATE TABLE IF NOT EXISTS automated_discovery_candidates(
      discovery_version TEXT NOT NULL, candidate_key TEXT NOT NULL, name TEXT NOT NULL, family TEXT NOT NULL,
      status TEXT NOT NULL, definition_json TEXT NOT NULL, validation_accuracy REAL, validation_brier REAL,
      holdout_accuracy REAL, holdout_brier REAL, accuracy_delta REAL, brier_improvement REAL,
      evaluated_matchups INTEGER, comparison_json TEXT, generated_at TEXT NOT NULL,
      PRIMARY KEY(discovery_version,candidate_key)
    );
    """)
    conn.execute("INSERT OR IGNORE INTO automated_discovery_state(state_id) VALUES (1)")
    conn.commit()


def _state_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DISCOVERY_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DISCOVERY_DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _json(value: Any) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
