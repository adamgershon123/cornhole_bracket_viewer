from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
import requests

from event_discovery import redact_discovery_payload, search_acl_events
from event_timezone import advertised_start_utc, timezone_from_coordinates
from outcome_ingestion import experimental_performance_report, ingest_completed_outcomes
from prediction_evaluation import prediction_evaluation_report
from prediction_feedback import prediction_learning_report
from prediction_performance import prediction_performance_report
from player_history_queue import (
    enqueue_players,
    queued_history_report,
)
from provenance import record_ingestion_attempt, record_source_payload
from shadow_predictions import shadow_performance_report
from upcoming_matchups import (
    create_due_shadow_predictions,
    ingest_schedule_matchups,
    matchup_discovery_report,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_lifecycle_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS monitored_events (
            event_id TEXT PRIMARY KEY,
            schedule_format TEXT NOT NULL,
            source_timezone TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            added_at TEXT NOT NULL,
            last_polled_at TEXT,
            last_poll_status TEXT,
            last_poll_message TEXT,
            poll_start_at TEXT,
            priority INTEGER NOT NULL DEFAULT 100,
            priority_label TEXT,
            auto_freeze_prediction INTEGER NOT NULL DEFAULT 0,
            auto_grade_on_complete INTEGER NOT NULL DEFAULT 0,
            CHECK(schedule_format IN ('SWISS', 'SWAP', 'BRACKET'))
        );

        CREATE TABLE IF NOT EXISTS lifecycle_runs (
            lifecycle_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            discovery_events INTEGER NOT NULL DEFAULT 0,
            schedules_polled INTEGER NOT NULL DEFAULT 0,
            predictions_created INTEGER NOT NULL DEFAULT 0,
            abstentions_created INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT
        );
        """
    )
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(monitored_events)").fetchall()
    }
    if "poll_start_at" not in columns:
        conn.execute("ALTER TABLE monitored_events ADD COLUMN poll_start_at TEXT")
    if "priority" not in columns:
        conn.execute(
            "ALTER TABLE monitored_events ADD COLUMN priority INTEGER NOT NULL DEFAULT 100"
        )
    if "priority_label" not in columns:
        conn.execute("ALTER TABLE monitored_events ADD COLUMN priority_label TEXT")
    if "auto_freeze_prediction" not in columns:
        conn.execute("ALTER TABLE monitored_events ADD COLUMN auto_freeze_prediction INTEGER NOT NULL DEFAULT 0")
    if "auto_grade_on_complete" not in columns:
        conn.execute("ALTER TABLE monitored_events ADD COLUMN auto_grade_on_complete INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def classify_no_activity_events(
    conn: sqlite3.Connection,
    *,
    as_of_date: str | None = None,
) -> int:
    """Archive past scheduled events that never produced competitive data."""
    initialize_lifecycle_schema(conn)
    cutoff = as_of_date or datetime.now(timezone.utc).date().isoformat()
    updated = conn.execute(
        """
        UPDATE monitored_events
        SET enabled=0,
            last_poll_status='NO_ACTIVITY',
            last_poll_message='No roster, matchup, match, standings, results, or round data was recorded before the monitoring window closed.'
        WHERE event_id IN (
            SELECT CAST(d.event_id AS TEXT)
            FROM discovered_events d
            WHERE d.event_date IS NOT NULL AND d.event_date < ?
        )
          AND COALESCE(last_poll_status, '') != 'NO_ACTIVITY'
          AND NOT EXISTS (
              SELECT 1 FROM upcoming_matchup_candidates c
              WHERE c.event_id=monitored_events.event_id
                AND (c.home_player_ids_json NOT IN ('', '[]')
                     OR c.away_player_ids_json NOT IN ('', '[]'))
          )
          AND NOT EXISTS (SELECT 1 FROM matches x WHERE CAST(x.event_id AS TEXT)=monitored_events.event_id)
          AND NOT EXISTS (SELECT 1 FROM player_rounds r WHERE CAST(r.event_id AS TEXT)=monitored_events.event_id)
          AND NOT EXISTS (SELECT 1 FROM swap_standings s WHERE CAST(s.event_id AS TEXT)=monitored_events.event_id)
          AND NOT EXISTS (SELECT 1 FROM event_results er WHERE CAST(er.event_id AS TEXT)=monitored_events.event_id)
          AND NOT EXISTS (SELECT 1 FROM team_members tm WHERE CAST(tm.event_id AS TEXT)=monitored_events.event_id)
          AND NOT EXISTS (SELECT 1 FROM bracket_prediction_snapshots b WHERE CAST(b.event_id AS TEXT)=monitored_events.event_id)
          AND NOT EXISTS (SELECT 1 FROM shadow_prediction_runs p WHERE p.event_id=monitored_events.event_id)
        """,
        (cutoff,),
    ).rowcount
    conn.commit()
    return int(updated or 0)


def monitor_event(
    conn: sqlite3.Connection,
    *,
    event_id: str | int,
    schedule_format: str,
    source_timezone: str | None,
    auto_freeze_prediction: bool | None = None,
    auto_grade_on_complete: bool | None = None,
) -> None:
    initialize_lifecycle_schema(conn)
    normalized = schedule_format.strip().upper()
    if normalized not in {"SWISS", "SWAP", "BRACKET"}:
        raise ValueError("schedule_format must be SWISS, SWAP, or BRACKET")
    conn.execute(
        """
        INSERT INTO monitored_events(
            event_id, schedule_format, source_timezone, enabled, added_at,
            auto_freeze_prediction, auto_grade_on_complete
        ) VALUES (?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            schedule_format=excluded.schedule_format,
            source_timezone=excluded.source_timezone,
            enabled=1,
            auto_freeze_prediction=COALESCE(?, monitored_events.auto_freeze_prediction),
            auto_grade_on_complete=COALESCE(?, monitored_events.auto_grade_on_complete)
        """,
        (str(event_id), normalized, source_timezone, utc_now(),
         int(bool(auto_freeze_prediction)) if auto_freeze_prediction is not None else 0,
         int(bool(auto_grade_on_complete)) if auto_grade_on_complete is not None else 0,
         int(bool(auto_freeze_prediction)) if auto_freeze_prediction is not None else None,
         int(bool(auto_grade_on_complete)) if auto_grade_on_complete is not None else None),
    )
    known = conn.execute(
        """
        SELECT status, bracket_completed
        FROM events WHERE event_id=?
        """,
        (int(event_id),),
    ).fetchone()
    if known and (
        int(known["bracket_completed"] or 0) == 1
        or str(known["status"] or "").strip().upper() in {"C", "COMPLETE", "COMPLETED"}
    ):
        conn.execute(
            """
            UPDATE monitored_events
            SET enabled=0, last_polled_at=?, last_poll_status='COMPLETE',
                last_poll_message='ACL event is complete; active polling stopped.'
            WHERE event_id=?
            """,
            (utc_now(), str(event_id)),
        )
    conn.commit()


def auto_monitor_discovered_events(
    conn: sqlite3.Connection,
    *,
    as_of: str | None = None,
    days_ahead: int = 2,
    limit: int = 50,
) -> dict[str, Any]:
    """Enroll nearby schedule-based events without weakening timestamp safety.

    A missing event timezone no longer prevents schedule polling. It still
    prevents a prediction when ACL supplies a naive match time; aware match
    timestamps remain usable without an event timezone.
    """
    initialize_lifecycle_schema(conn)
    now = datetime.fromisoformat((as_of or utc_now()).replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start_date = now.date().isoformat()
    end_date = (now.date() + timedelta(days=max(0, days_ahead))).isoformat()
    rows = conn.execute(
        """
        SELECT event_id, format_candidate, event_date, advertised_time,
               location_lat, location_lng
        FROM discovered_events
        WHERE event_date BETWEEN ? AND ?
          AND UPPER(COALESCE(status, '')) NOT IN ('C', 'COMPLETE', 'COMPLETED')
          AND format_candidate IN ('SWAP_CANDIDATE', 'SWISS_CANDIDATE')
        ORDER BY event_date, advertised_time, event_id
        LIMIT ?
        """,
        (start_date, end_date, max(1, limit)),
    ).fetchall()
    inserted = 0
    reenabled = 0
    timezone_blocked = 0
    completed = conn.execute(
        """
        UPDATE monitored_events
        SET enabled=0, last_polled_at=?, last_poll_status='COMPLETE',
            last_poll_message='Discovery reports the ACL event complete; active polling stopped.'
        WHERE enabled=1
          AND event_id IN (
              SELECT CAST(event_id AS TEXT)
              FROM discovered_events
              WHERE UPPER(COALESCE(status, '')) IN ('C', 'COMPLETE', 'COMPLETED')
          )
        """,
        (utc_now(),),
    ).rowcount
    for row in rows:
        event_id = str(row["event_id"])
        timezone_name = timezone_from_coordinates(
            row["location_lat"],
            row["location_lng"],
        )
        poll_start_at = (
            advertised_start_utc(
                row["event_date"],
                row["advertised_time"],
                timezone_name,
            )
            if timezone_name
            else None
        )
        if not timezone_name or not poll_start_at:
            timezone_blocked += 1
            continue
        existing = conn.execute(
            "SELECT enabled FROM monitored_events WHERE event_id=?",
            (event_id,),
        ).fetchone()
        schedule_format = (
            "SWISS" if row["format_candidate"] == "SWISS_CANDIDATE" else "SWAP"
        )
        conn.execute(
            """
            INSERT INTO monitored_events(
                event_id, schedule_format, source_timezone, enabled, added_at,
                poll_start_at
            ) VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                schedule_format=excluded.schedule_format,
                source_timezone=excluded.source_timezone,
                poll_start_at=excluded.poll_start_at,
                enabled=1
            """,
            (event_id, schedule_format, timezone_name, utc_now(), poll_start_at),
        )
        if existing is None:
            inserted += 1
        elif int(existing["enabled"] or 0) == 0:
            reenabled += 1
    conn.commit()
    return {
        "windowStart": start_date,
        "windowEnd": end_date,
        "eligible": len(rows),
        "added": inserted,
        "reenabled": reenabled,
        "completedDisabled": max(0, completed),
        "timezoneBlocked": timezone_blocked,
    }


def prioritize_acl_worlds_events(
    conn: sqlite3.Connection,
    *,
    as_of: str | None = None,
    days_ahead: int = 7,
) -> dict[str, Any]:
    """Promote the full ACL Worlds series into monitoring and fast-lane collection."""
    initialize_lifecycle_schema(conn)
    now = datetime.fromisoformat((as_of or utc_now()).replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start_date = now.date().isoformat()
    end_date = (now.date() + timedelta(days=max(0, days_ahead))).isoformat()
    rows = conn.execute(
        """
        SELECT event_id, event_name, event_date, advertised_time,
               format_candidate, location_lat, location_lng
        FROM discovered_events
        WHERE LOWER(COALESCE(event_name, '')) LIKE '%acl worlds%'
          AND event_date BETWEEN ? AND ?
          AND UPPER(COALESCE(status, '')) NOT IN ('C', 'COMPLETE', 'COMPLETED')
        ORDER BY event_date, advertised_time, event_id
        """,
        (start_date, end_date),
    ).fetchall()
    monitored = 0
    event_ids: list[int] = []
    for row in rows:
        event_ids.append(int(row["event_id"]))
        schedule_format = {
            "SWAP_CANDIDATE": "SWAP",
            "SWISS_CANDIDATE": "SWISS",
        }.get(row["format_candidate"], "BRACKET")
        timezone_name = timezone_from_coordinates(
            row["location_lat"],
            row["location_lng"],
        )
        poll_start_at = (
            advertised_start_utc(
                row["event_date"],
                row["advertised_time"],
                timezone_name,
            )
            if timezone_name and row["advertised_time"]
            else datetime.fromisoformat(row["event_date"]).replace(
                tzinfo=timezone.utc
            ).isoformat()
        )
        conn.execute(
            """
            INSERT INTO monitored_events(
                event_id, schedule_format, source_timezone, enabled, added_at,
                poll_start_at, priority, priority_label
            ) VALUES (?, ?, ?, 1, ?, ?, 0, 'ACL_WORLDS')
            ON CONFLICT(event_id) DO UPDATE SET
                schedule_format=excluded.schedule_format,
                source_timezone=COALESCE(excluded.source_timezone, monitored_events.source_timezone),
                poll_start_at=COALESCE(excluded.poll_start_at, monitored_events.poll_start_at),
                priority=0,
                priority_label='ACL_WORLDS',
                enabled=1
            """,
            (
                str(row["event_id"]),
                schedule_format,
                timezone_name,
                utc_now(),
                poll_start_at,
            ),
        )
        monitored += 1
    from historical_backfill import prioritize_events

    historical = prioritize_events(
        conn,
        event_ids,
        source=f"priority-series:acl-worlds:{start_date}:{end_date}",
        priority=1100,
        requeue_completed=False,
    )
    conn.commit()
    return {
        "windowStart": start_date,
        "windowEnd": end_date,
        "discovered": len(rows),
        "monitored": monitored,
        "historicalQueue": historical,
    }


def initialize_prediction_operations_snapshot_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_operations_snapshots (
            snapshot_id INTEGER PRIMARY KEY CHECK(snapshot_id = 1),
            payload_json TEXT,
            generated_at TEXT,
            refresh_started_at TEXT,
            refresh_finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'PREPARING',
            error_message TEXT
        )
        """
    )
    conn.commit()


def prediction_operations_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return the last prepared dashboard without running analytics in the request."""
    initialize_prediction_operations_snapshot_schema(conn)
    row = conn.execute(
        "SELECT * FROM prediction_operations_snapshots WHERE snapshot_id=1"
    ).fetchone()
    if row and row["payload_json"]:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        payload["snapshot"] = {
            "status": row["status"],
            "generatedAt": row["generated_at"],
            "refreshStartedAt": row["refresh_started_at"],
            "refreshFinishedAt": row["refresh_finished_at"],
            "error": row["error_message"],
            "prepared": True,
        }
        return payload
    return {
        "generatedAt": utc_now(),
        "snapshot": {
            "status": row["status"] if row else "PREPARING",
            "generatedAt": None,
            "refreshStartedAt": row["refresh_started_at"] if row else None,
            "refreshFinishedAt": None,
            "error": row["error_message"] if row else None,
            "prepared": False,
        },
        "discoveredEvents": {"total": 0, "byFormat": []},
        "monitoredEvents": [],
        "recentPredictions": [],
        "recentLifecycleRuns": [],
        "todayMonitoring": {"status": "PREPARING", "eventCount": 0, "events": []},
    }


def refresh_prediction_operations_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Prepare and atomically replace the durable operations-dashboard snapshot."""
    initialize_prediction_operations_snapshot_schema(conn)
    started_at = utc_now()
    conn.execute(
        """
        INSERT INTO prediction_operations_snapshots(snapshot_id, refresh_started_at, status)
        VALUES(1, ?, 'REFRESHING')
        ON CONFLICT(snapshot_id) DO UPDATE SET
            refresh_started_at=excluded.refresh_started_at,
            status='REFRESHING',
            error_message=NULL
        """,
        (started_at,),
    )
    conn.commit()
    try:
        payload = _build_prediction_operations_snapshot(conn)
        finished_at = utc_now()
        conn.execute(
            """
            UPDATE prediction_operations_snapshots
            SET payload_json=?, generated_at=?, refresh_finished_at=?,
                status='READY', error_message=NULL
            WHERE snapshot_id=1
            """,
            (json.dumps(payload, separators=(",", ":")), payload["generatedAt"], finished_at),
        )
        conn.commit()
        return payload
    except Exception as exc:
        conn.execute(
            """
            UPDATE prediction_operations_snapshots
            SET refresh_finished_at=?, status='ERROR', error_message=?
            WHERE snapshot_id=1
            """,
            (utc_now(), str(exc)[:1000]),
        )
        conn.commit()
        raise


def start_prediction_operations_snapshot_worker(db_factory: Any) -> None:
    def worker() -> None:
        time.sleep(10)
        while True:
            try:
                with db_factory() as worker_conn:
                    refresh_prediction_operations_snapshot(worker_conn)
                print("Prediction operations snapshot refreshed", flush=True)
            except Exception as exc:
                print(f"Prediction operations snapshot refresh failed: {exc}", flush=True)
            time.sleep(600)

    threading.Thread(
        target=worker,
        daemon=True,
        name="prediction-operations-snapshot",
    ).start()


def _build_prediction_operations_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_lifecycle_schema(conn)
    from event_analytics_jobs import ensure_event_analytics_job_schema
    from walker_repair import walker_repair_status
    ensure_event_analytics_job_schema(conn)
    discovered = conn.execute(
        """
        SELECT format_candidate, COUNT(*) AS count
        FROM discovered_events
        GROUP BY format_candidate
        ORDER BY count DESC
        """
    ).fetchall()
    monitored = conn.execute(
        """
        SELECT m.*, d.event_name, d.event_date, d.advertised_time,
               d.location_city, d.location_state, d.location_country,
               (SELECT j.status FROM event_analytics_jobs j WHERE j.event_id=CAST(m.event_id AS INTEGER) AND j.job_type='FROZEN_PREDICTION') AS frozen_prediction_job_status,
               (SELECT j.status FROM event_analytics_jobs j WHERE j.event_id=CAST(m.event_id AS INTEGER) AND j.job_type='TOURNAMENT_GRADES') AS tournament_grades_job_status,
               CASE
                 WHEN m.last_poll_status='NO_ACTIVITY' THEN 'NO_ACTIVITY'
                 WHEN m.enabled=1 THEN 'ACTIVE'
                 WHEN m.last_poll_status='COMPLETE' THEN 'COMPLETE'
                 ELSE 'ARCHIVED'
               END AS tracking_status
        FROM monitored_events m
        LEFT JOIN discovered_events d ON CAST(d.event_id AS TEXT)=m.event_id
        WHERE m.enabled=1
           OR m.last_poll_status='COMPLETE'
           OR m.last_poll_status='NO_ACTIVITY'
           OR d.event_date BETWEEN date('now', '-7 days') AND date('now')
        ORDER BY d.event_date DESC, d.advertised_time DESC, m.event_id
        """
    ).fetchall()
    candidates = conn.execute(
        """
        SELECT event_id, match_id, format, scheduled_start_at,
               discovery_status, discovery_issue
        FROM upcoming_matchup_candidates
        ORDER BY last_seen_at DESC
        LIMIT 50
        """
    ).fetchall()
    predictions = conn.execute(
        """
        SELECT r.shadow_run_id, r.event_id, r.match_id, r.status,
               r.abstention_reason, r.scheduled_start_at, r.recorded_at,
               COALESCE(e.event_name, d.event_name) AS event_name,
               p.side_a_probability, p.side_b_probability, p.evidence_tier,
               p.side_a_player_ids_json, p.side_b_player_ids_json,
               c.model_version AS challenger_model_version,
               c.status AS challenger_status,
               c.side_a_probability AS challenger_side_a_probability,
               c.side_b_probability AS challenger_side_b_probability,
               s.snapshot_version AS candidate_snapshot_version,
               s.completeness_rate AS candidate_snapshot_completeness,
               s.available_factors AS candidate_available_factors,
               s.expected_factors AS candidate_expected_factors,
               s.missing_reasons_json AS candidate_missing_reasons_json,
               o.side_a_won, o.resolved_at
        FROM shadow_prediction_runs r
        JOIN prediction_records p ON p.prediction_id=r.prediction_id
        LEFT JOIN shadow_challenger_predictions c ON c.shadow_run_id=r.shadow_run_id
        LEFT JOIN candidate_factor_snapshots s ON s.shadow_run_id=r.shadow_run_id
        LEFT JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
        LEFT JOIN events e ON CAST(e.event_id AS TEXT)=r.event_id
        LEFT JOIN discovered_events d ON CAST(d.event_id AS TEXT)=r.event_id
        ORDER BY r.recorded_at DESC
        LIMIT 50
        """
    ).fetchall()
    prediction_rows = [dict(row) for row in predictions]
    prediction_player_ids: set[int] = set()
    for row in prediction_rows:
        for field in ("side_a_player_ids_json", "side_b_player_ids_json"):
            prediction_player_ids.update(_safe_player_ids(row.get(field)))
    player_names: dict[int, str] = {}
    if prediction_player_ids:
        placeholders = ",".join("?" for _ in prediction_player_ids)
        name_rows = conn.execute(
            f"""
            SELECT player_id, MAX(player_name) AS player_name
            FROM (
                SELECT player_id, NULLIF(display_name, '') AS player_name
                FROM players WHERE player_id IN ({placeholders})
                UNION ALL
                SELECT player_id, NULLIF(player_name, '') AS player_name
                FROM player_rounds WHERE player_id IN ({placeholders})
                UNION ALL
                SELECT player_id, NULLIF(player_name, '') AS player_name
                FROM swap_standings WHERE player_id IN ({placeholders})
            )
            GROUP BY player_id
            """,
            (*prediction_player_ids, *prediction_player_ids, *prediction_player_ids),
        ).fetchall()
        player_names = {
            int(row["player_id"]): row["player_name"]
            for row in name_rows
            if row["player_name"]
        }
    for row in prediction_rows:
        row["player_names"] = {
            str(player_id): player_names.get(player_id, f"Player {player_id}")
            for field in ("side_a_player_ids_json", "side_b_player_ids_json")
            for player_id in _safe_player_ids(row.get(field))
        }
    recent_runs = conn.execute(
        """
        SELECT * FROM lifecycle_runs
        ORDER BY lifecycle_run_id DESC
        LIMIT 50
        """
    ).fetchall()
    latest_rapid_assistance: dict[str, Any] = {}
    for lifecycle_row in recent_runs:
        try:
            run_summary = json.loads(lifecycle_row["summary_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        assistance_options = [
            (run_summary.get("shadowCreation") or {}).get(
                "rapidHistoryAssistance"
            ),
            *[
                (entry or {}).get("rapidHistoryAssistance")
                for entry in reversed(run_summary.get("rapidPredictionPasses") or [])
            ],
        ]
        assistance = next(
            (
                option
                for option in assistance_options
                if option and (
                    int(option.get("requestedPlayers") or 0) > 0
                    or int(option.get("internallyCoveredPlayers") or 0) > 0
                )
            ),
            next((option for option in assistance_options if option), None),
        )
        if assistance:
            latest_rapid_assistance = {
                **assistance,
                "lifecycleRunId": lifecycle_row["lifecycle_run_id"],
                "completedAt": lifecycle_row["finished_at"],
            }
            break
    fresh_acl_assistance = int(conn.execute(
        """
        SELECT COUNT(DISTINCT player_id)
        FROM statistic_observations
        WHERE statistic_type='ACL_REPORTED_SEASON_PPR'
          AND availability_status='AVAILABLE'
          AND retrieved_at >= ?
        """,
        ((datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),),
    ).fetchone()[0])
    latest_rapid_assistance["cachedAssistedPlayers"] = fresh_acl_assistance
    if fresh_acl_assistance and not latest_rapid_assistance.get("status"):
        latest_rapid_assistance["status"] = "READY"
    active_today = [
        dict(row)
        for row in monitored
        if int(row["enabled"] or 0) == 1
        and row["event_date"] == datetime.now(timezone.utc).date().isoformat()
    ]
    performance = prediction_performance_report(conn)
    return {
        "generatedAt": utc_now(),
        "discoveredEvents": {
            "total": sum(int(row["count"]) for row in discovered),
            "byFormat": [dict(row) for row in discovered],
        },
        "monitoredEvents": [dict(row) for row in monitored],
        "matchupDiscovery": matchup_discovery_report(conn),
        "recentCandidates": [dict(row) for row in candidates],
        "historyQueue": queued_history_report(conn),
        "shadowPerformance": shadow_performance_report(conn),
        "experimentalPerformance": experimental_performance_report(conn),
        "predictionEvaluations": prediction_evaluation_report(conn),
        "predictionLearning": prediction_learning_report(conn),
        "predictionPerformance": performance,
        "recentPredictions": prediction_rows,
        "recentLifecycleRuns": [dict(row) for row in recent_runs],
        "lifecycleActivity": _lifecycle_activity(recent_runs),
        "rapidPredictionAssistance": latest_rapid_assistance,
        "todayMonitoring": {
            "status": "ON" if active_today else "IDLE",
            "eventCount": len(active_today),
            "events": active_today,
        },
        "prioritySeries": {
            "aclWorlds": {
                "monitored": sum(
                    1
                    for row in monitored
                    if row["priority_label"] == "ACL_WORLDS"
                    and int(row["enabled"] or 0) == 1
                ),
                "events": [
                    dict(row)
                    for row in monitored
                    if row["priority_label"] == "ACL_WORLDS"
                ],
            },
        },
        "historicalReference": _historical_reference(
            performance.get("historicalBacktest") or {}
        ),
        "walkerHistoryRepair": walker_repair_status(conn),
    }


def _lifecycle_activity(rows: list[sqlite3.Row]) -> dict[str, Any]:
    checks = []
    for row in rows:
        try:
            summary = json.loads(row["summary_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            summary = {}
        outcomes = sum(
            int(((poll or {}).get("outcomes") or {}).get("outcomesStored") or 0)
            for poll in summary.get("schedulePolls") or []
        )
        rosters = sum(
            int(((poll or {}).get("ingestion") or {}).get("predictionCandidates") or 0)
            for poll in summary.get("schedulePolls") or []
        )
        history_queued = sum(
            int((((poll or {}).get("ingestion") or {}).get("historyHydration") or {}).get("queued") or 0)
            for poll in summary.get("schedulePolls") or []
        )
        predictions = int(row["predictions_created"] or 0)
        abstentions = int(row["abstentions_created"] or 0)
        errors = int(row["errors"] or 0)
        discovery = int(row["discovery_events"] or 0)
        started = _parse_lifecycle_time(row["started_at"])
        finished = _parse_lifecycle_time(row["finished_at"])
        duration = round((finished - started).total_seconds(), 1) if started and finished else None
        meaningful = any((predictions, abstentions, outcomes, errors))
        checks.append({
            "cycleId": int(row["lifecycle_run_id"]),
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
            "status": row["status"],
            "durationSeconds": duration,
            "eventsPolled": int(row["schedules_polled"] or 0),
            "eventsReturnedBySearch": discovery,
            "matchupsIndexed": rosters,
            "playersQueued": history_queued,
            "predictionsFrozen": predictions,
            "abstentions": abstentions,
            "outcomesResolved": outcomes,
            "reviewsCreated": outcomes,
            "errors": errors,
            "meaningful": meaningful,
        })
    active = next((item for item in checks if item["status"] == "RUNNING"), None)
    latest = next((item for item in checks if item["status"] == "COMPLETE"), None)
    last_finished = _parse_lifecycle_time(latest.get("finishedAt")) if latest else None
    return {
        "lastCheck": latest,
        "activeCheck": active,
        "nextScheduledCheckAt": (
            (last_finished + timedelta(seconds=120)).isoformat() if last_finished else None
        ),
        "noChangeChecks": sum(not item["meaningful"] for item in checks),
        "checksInspected": len(checks),
        "notableChecks": [item for item in checks if item["meaningful"]][:10],
    }


def _parse_lifecycle_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _historical_reference(backtest: dict[str, Any]) -> dict[str, Any]:
    models = [
        row for row in (backtest.get("models") or [])
        if row.get("model") != "Equal odds" and row.get("accuracy") is not None
    ]
    preferred = max(models, key=lambda row: float(row.get("accuracy") or 0), default={})
    return {
        "accuracy": preferred.get("accuracy"),
        "coverageRate": preferred.get("coverageRate"),
        "logLoss": preferred.get("logLoss"),
        "brierScore": preferred.get("brierScore"),
        "evaluatedMatchups": preferred.get("evaluatedMatchups", 0),
        "generatedAt": backtest.get("generatedAt"),
        "model": preferred.get("model"),
    }


def _safe_player_ids(raw: Any) -> list[int]:
    try:
        return [int(value) for value in json.loads(raw or "[]")]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def run_lifecycle_cycle(
    conn: sqlite3.Connection,
    *,
    search_params: dict[str, Any] | None = None,
    lookahead_minutes: int = 180,
) -> dict[str, Any]:
    initialize_lifecycle_schema(conn)
    started = utc_now()
    cursor = conn.execute(
        "INSERT INTO lifecycle_runs(started_at, status) VALUES (?, 'RUNNING')",
        (started,),
    )
    run_id = int(cursor.lastrowid)
    conn.commit()
    summary: dict[str, Any] = {
        "runId": run_id,
        "discovery": None,
        "autoMonitoring": None,
        "schedulePolls": [],
        "rapidPredictionPasses": [],
        "shadowCreation": None,
        "errors": [],
        "defaultPlayerBracketEnrollment": None,
    }
    try:
        if search_params:
            summary["discovery"] = search_acl_events(conn, **search_params)
            summary["autoMonitoring"] = auto_monitor_discovered_events(conn)
        summary["aclWorldsPriority"] = prioritize_acl_worlds_events(conn)
        today_utc = datetime.now(timezone.utc).date().isoformat()
        # A tournament can run past midnight UTC, and ACL can publish final
        # scores after the advertised event date.  Never let a date rollover
        # strand an issued prediction without its result.  This also repairs
        # events disabled by the older date-only expiration rule.
        conn.execute(
            """
            UPDATE monitored_events
            SET enabled=1,
                last_poll_message='Result polling resumed for unresolved predictions.'
            WHERE enabled=0
              AND EXISTS (
                  SELECT 1
                  FROM shadow_prediction_runs r
                  LEFT JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
                  WHERE r.event_id=monitored_events.event_id
                    AND r.status='PREDICTED'
                    AND o.outcome_id IS NULL
              )
            """
        )
        conn.execute(
            """
            UPDATE monitored_events
            SET enabled=0,
                last_poll_message=COALESCE(
                    last_poll_message,
                    'Monitoring window expired after the event date.'
                )
            WHERE enabled=1
              AND event_id IN (
                  SELECT CAST(event_id AS TEXT)
                  FROM discovered_events
                  WHERE event_date IS NOT NULL AND event_date < ?
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM shadow_prediction_runs r
                  LEFT JOIN shadow_outcomes o ON o.shadow_run_id=r.shadow_run_id
                  WHERE r.event_id=monitored_events.event_id
                    AND r.status='PREDICTED'
                    AND o.outcome_id IS NULL
              )
            """,
            (today_utc,),
        )
        summary["noActivityArchived"] = classify_no_activity_events(
            conn,
            as_of_date=today_utc,
        )
        conn.commit()
        monitored = conn.execute(
            """
            SELECT m.* FROM monitored_events m
            LEFT JOIN discovered_events d
              ON CAST(d.event_id AS TEXT)=m.event_id
            WHERE m.enabled=1
              AND m.schedule_format IN ('SWISS', 'SWAP', 'BRACKET')
              AND (m.poll_start_at IS NULL OR m.poll_start_at <= ?)
            ORDER BY m.priority, COALESCE(m.poll_start_at, ''), d.event_date, d.advertised_time,
                     m.event_id
            """,
            (utc_now(),),
        ).fetchall()
        # Dynamic import avoids a module cycle: season_platform owns ACL fetching.
        from season_platform import (
            DATA_DIR,
            fetch_and_index_upcoming_schedule,
            fetch_bracket,
        )
        from bracket_prediction_snapshots import (
            bracket_player_ids,
            bracket_prediction_timeline,
            bracket_roster_ready,
        )

        for event in monitored:
            try:
                bracket_history_pending = False
                if event["schedule_format"] == "BRACKET":
                    bracket, meta = fetch_bracket(
                        conn,
                        int(event["event_id"]),
                    )
                    populated = sum(
                        bool(row.get("bracketteamid"))
                        for row in bracket.get("bracketDetails", [])
                        if isinstance(row, dict)
                    )
                    result = {
                        "eventId": int(event["event_id"]),
                        "format": "BRACKET",
                        "endpoint": "bracket-data",
                        "source": meta.get("source"),
                        "ingestion": {
                            "populatedBracketRows": populated,
                            "predictionCandidates": 0,
                            "reason": (
                                "Bracket polling is active; predictions wait for "
                                "trustworthy pregame side and timestamp data."
                            ),
                        },
                    }
                    if bracket_roster_ready(bracket):
                        event_info = bracket.get("eventInfo") or {}
                        player_ids = bracket_player_ids(bracket)
                        enqueue_players(
                            conn,
                            player_ids=player_ids,
                            reason={
                                "source": "bracket-roster",
                                "eventId": str(event["event_id"]),
                                "purpose": "frozen-bracket-prediction",
                            },
                            priority=0,
                        )
                        result["ingestion"]["historyHydration"] = {
                            "queued": len(player_ids),
                            "mode": "INDEPENDENT_BACKGROUND",
                        }
                        prediction = bracket_prediction_timeline(
                            conn,
                            bracket,
                            simulations=10_000,
                            data_dir=DATA_DIR,
                        )
                        result["ingestion"]["frozenPredictionAt"] = prediction.get("frozenAt")
                        result["ingestion"]["forecastResultsApplied"] = prediction.get(
                            "completedMatchesApplied", 0
                        )
                    event_info = bracket.get("eventInfo") or {}
                    bracket_is_complete = (
                        str(event_info.get("leagueStatus") or "").upper() in {"C", "COMPLETE", "COMPLETED"}
                        or meta.get("completionStatus") == "complete"
                    )
                else:
                    result = fetch_and_index_upcoming_schedule(
                        conn,
                        event_id=int(event["event_id"]),
                        schedule_format=event["schedule_format"],
                        source_timezone=event["source_timezone"],
                        event_start_at=event["poll_start_at"],
                        create_due=False,
                    )
                    # Score immediately after this roster is indexed. A long list
                    # of other monitored events must not delay its prediction.
                    rapid_pass = create_due_shadow_predictions(
                        conn,
                        lookahead_minutes=lookahead_minutes,
                    )
                    summary["rapidPredictionPasses"].append({
                        "eventId": event["event_id"],
                        **rapid_pass,
                    })
                    if event["priority_label"] == "ACL_WORLDS":
                        roster_rows = conn.execute(
                            """
                            SELECT home_player_ids_json, away_player_ids_json
                            FROM upcoming_matchup_candidates
                            WHERE event_id=? AND discovery_status='READY'
                            """,
                            (str(event["event_id"]),),
                        ).fetchall()
                        priority_players: set[int] = set()
                        for roster_row in roster_rows:
                            priority_players.update(
                                json.loads(roster_row["home_player_ids_json"] or "[]")
                            )
                            priority_players.update(
                                json.loads(roster_row["away_player_ids_json"] or "[]")
                            )
                        enqueue_players(
                            conn,
                            player_ids=priority_players,
                            reason={
                                "source": "acl-worlds-priority-roster",
                                "eventId": str(event["event_id"]),
                            },
                            priority=0,
                        )
                summary["schedulePolls"].append(result)
                if event["schedule_format"] == "SWAP":
                    endpoint = "swap-schedule-all"
                    url = (
                        "https://api.iplayacl.com/api/v1/"
                        f"{endpoint}/{event['event_id']}"
                    )
                    response = requests.get(
                        url,
                        headers={
                            "accept": "application/json, text/plain, */*",
                            "origin": "https://app.iplayacl.com",
                            "referer": "https://app.iplayacl.com/",
                            "x-app-version": "14.1.0",
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    raw_outcomes = response.json()
                    safe_outcomes, _ = redact_discovery_payload(raw_outcomes)
                    entity_key = f"event:{event['event_id']}"
                    source_payload_id = record_source_payload(
                        conn,
                        source_endpoint=endpoint,
                        entity_key=entity_key,
                        request_url=url,
                        payload=safe_outcomes,
                        http_status=response.status_code,
                    )
                    record_ingestion_attempt(
                        conn,
                        source_endpoint=endpoint,
                        entity_key=entity_key,
                        request_url=url,
                        outcome="success",
                        http_status=response.status_code,
                        source_payload_id=source_payload_id,
                    )
                    result["outcomes"] = ingest_completed_outcomes(
                        conn,
                        event_id=event["event_id"],
                        payload=raw_outcomes,
                        source_endpoint=endpoint,
                        source_payload_id=source_payload_id,
                    )
                    result["scheduleAllIngestion"] = ingest_schedule_matchups(
                        conn,
                        event_id=event["event_id"],
                        payload=raw_outcomes,
                        source_endpoint=endpoint,
                        format_name="SWAP",
                        source_timezone=event["source_timezone"],
                        event_start_at=event["poll_start_at"],
                    )
                final_status = "COMPLETE" if (
                    event["schedule_format"] == "BRACKET"
                    and bracket_is_complete
                    and not bracket_history_pending
                ) else "SUCCESS"
                conn.execute(
                    """
                    UPDATE monitored_events
                    SET last_polled_at=?, last_poll_status=?,
                        last_poll_message=?,
                        enabled=CASE WHEN ?='COMPLETE' THEN 0 ELSE enabled END
                    WHERE event_id=?
                    """,
                    (
                        utc_now(),
                        final_status,
                        "ACL event is complete; active polling stopped." if final_status == "COMPLETE" else None,
                        final_status,
                        event["event_id"],
                    ),
                )
                conn.commit()
            except Exception as exc:
                summary["errors"].append({
                    "eventId": event["event_id"],
                    "error": str(exc),
                })
                conn.execute(
                    """
                    UPDATE monitored_events
                    SET last_polled_at=?, last_poll_status='ERROR',
                        last_poll_message=?
                    WHERE event_id=?
                    """,
                    (utc_now(), str(exc), event["event_id"]),
                )
                conn.commit()
        # Use the rosters indexed by this very discovery/polling cycle. This is
        # a local database check, not a separate player-events API request.
        from shared_viewer_profile import enroll_default_player_brackets_from_collected_rosters
        summary["defaultPlayerBracketEnrollment"] = (
            enroll_default_player_brackets_from_collected_rosters(conn)
        )
        summary["shadowCreation"] = create_due_shadow_predictions(
            conn,
            lookahead_minutes=lookahead_minutes,
        )
        shadow = summary["shadowCreation"]
        conn.execute(
            """
            UPDATE lifecycle_runs
            SET finished_at=?, status='COMPLETE', discovery_events=?,
                schedules_polled=?, predictions_created=?,
                abstentions_created=?, errors=?, summary_json=?
            WHERE lifecycle_run_id=?
            """,
            (
                utc_now(),
                int((summary["discovery"] or {}).get("indexedEventCount") or 0),
                len(summary["schedulePolls"]),
                int(shadow.get("predicted") or 0),
                int(shadow.get("abstained") or 0),
                len(summary["errors"]),
                json.dumps(summary, sort_keys=True, default=str),
                run_id,
            ),
        )
        conn.commit()
        return summary
    except Exception as exc:
        conn.execute(
            """
            UPDATE lifecycle_runs
            SET finished_at=?, status='FAILED', errors=1, summary_json=?
            WHERE lifecycle_run_id=?
            """,
            (utc_now(), str(exc), run_id),
        )
        conn.commit()
        raise
