from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from shadow_predictions import initialize_shadow_schema, record_shadow_outcome
from prediction_feedback import review_resolved_prediction


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_outcome_schema(conn: sqlite3.Connection) -> None:
    initialize_shadow_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS normalized_match_outcomes (
            event_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            home_score INTEGER NOT NULL,
            away_score INTEGER NOT NULL,
            home_won INTEGER NOT NULL,
            source_endpoint TEXT NOT NULL,
            source_payload_id INTEGER,
            source_status TEXT,
            resolved_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY(event_id, match_id),
            CHECK(home_won IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS inplay_experimental_predictions (
            experiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            model_label TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            observation_status TEXT NOT NULL,
            home_score_at_observation INTEGER,
            away_score_at_observation INTEGER,
            home_player_ids_json TEXT NOT NULL,
            away_player_ids_json TEXT NOT NULL,
            home_acl_ppr REAL NOT NULL,
            away_acl_ppr REAL NOT NULL,
            home_win_probability REAL NOT NULL,
            away_win_probability REAL NOT NULL,
            limitations_json TEXT NOT NULL,
            outcome_home_won INTEGER,
            resolved_at TEXT,
            UNIQUE(event_id, match_id, model_label)
        );
        """
    )
    conn.commit()


def completed_schedule_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", [])
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = (
            data.get("completedMatchList")
            or data.get("overAllSchedule")
            or data.get("schedule")
            or []
        )
    else:
        rows = []
    return [
        row for row in rows
        if isinstance(row, dict)
        and (
            str(row.get("matchStatusID")) == "5"
            or str(row.get("matchStatus", "")).strip().lower() == "completed"
        )
    ]


def ingest_completed_outcomes(
    conn: sqlite3.Connection,
    *,
    event_id: str | int,
    payload: dict[str, Any],
    source_endpoint: str,
    source_payload_id: int | None = None,
    resolved_at: str | None = None,
) -> dict[str, Any]:
    initialize_outcome_schema(conn)
    resolved_at = resolved_at or utc_now()
    result = {
        "completedRows": 0,
        "outcomesStored": 0,
        "shadowResolved": 0,
        "experimentalResolved": 0,
        "tiesOrInvalid": 0,
    }
    for row in completed_schedule_rows(payload):
        match_id = row.get("matchID") or row.get("matchId")
        try:
            home_score = int(row.get("homeScore"))
            away_score = int(row.get("awayScore"))
        except (TypeError, ValueError):
            result["tiesOrInvalid"] += 1
            continue
        result["completedRows"] += 1
        if match_id in (None, "") or home_score == away_score:
            result["tiesOrInvalid"] += 1
            continue
        home_won = int(home_score > away_score)
        conn.execute(
            """
            INSERT INTO normalized_match_outcomes(
                event_id, match_id, home_score, away_score, home_won,
                source_endpoint, source_payload_id, source_status,
                resolved_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, match_id) DO UPDATE SET
                home_score=excluded.home_score,
                away_score=excluded.away_score,
                home_won=excluded.home_won,
                source_endpoint=excluded.source_endpoint,
                source_payload_id=excluded.source_payload_id,
                source_status=excluded.source_status,
                resolved_at=excluded.resolved_at,
                recorded_at=excluded.recorded_at
            """,
            (
                str(event_id),
                str(match_id),
                home_score,
                away_score,
                home_won,
                source_endpoint,
                source_payload_id,
                row.get("matchStatus"),
                resolved_at,
                utc_now(),
            ),
        )
        result["outcomesStored"] += 1
        shadow = conn.execute(
            """
            SELECT r.shadow_run_id
            FROM shadow_prediction_runs r
            LEFT JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
            WHERE r.event_id=? AND r.match_id=? AND r.status='PREDICTED'
              AND o.outcome_id IS NULL
            """,
            (str(event_id), str(match_id)),
        ).fetchone()
        if shadow:
            record_shadow_outcome(
                conn,
                shadow_run_id=int(shadow["shadow_run_id"]),
                side_a_won=home_won,
                source=source_endpoint,
                source_payload_id=source_payload_id,
                resolved_at=resolved_at,
            )
            result["shadowResolved"] += 1
            review_resolved_prediction(conn, int(shadow["shadow_run_id"]))
        experimental = conn.execute(
            """
            UPDATE inplay_experimental_predictions
            SET outcome_home_won=?, resolved_at=?
            WHERE event_id=? AND match_id=? AND outcome_home_won IS NULL
            """,
            (home_won, resolved_at, str(event_id), str(match_id)),
        )
        result["experimentalResolved"] += int(experimental.rowcount)
    conn.commit()
    return result


def experimental_performance_report(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_outcome_schema(conn)
    rows = conn.execute(
        """
        SELECT home_win_probability, outcome_home_won
        FROM inplay_experimental_predictions
        WHERE outcome_home_won IS NOT NULL
        """
    ).fetchall()
    buckets = {
        "COIN_FLIP_50_55": {"predictions": 0, "correct": 0},
        "LEAN_55_70": {"predictions": 0, "correct": 0},
        "HIGH_CONFIDENCE_70_PLUS": {"predictions": 0, "correct": 0},
    }
    for row in rows:
        probability = float(row["home_win_probability"])
        confidence = max(probability, 1 - probability)
        if confidence < 0.55:
            key = "COIN_FLIP_50_55"
        elif confidence < 0.70:
            key = "LEAN_55_70"
        else:
            key = "HIGH_CONFIDENCE_70_PLUS"
        correct = int((probability >= 0.5) == bool(row["outcome_home_won"]))
        buckets[key]["predictions"] += 1
        buckets[key]["correct"] += correct
    for value in buckets.values():
        value["accuracy"] = (
            round(value["correct"] / value["predictions"], 6)
            if value["predictions"]
            else None
        )
    return {"resolvedPredictions": len(rows), "confidenceBuckets": buckets}
