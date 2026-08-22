from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

import requests


FROZEN_PREDICTION = "FROZEN_PREDICTION"
TOURNAMENT_GRADES = "TOURNAMENT_GRADES"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_event_analytics_job_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS event_analytics_jobs (
            event_id INTEGER NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            trigger_source TEXT,
            PRIMARY KEY(event_id, job_type)
        );
        """
    )


def enqueue_event_analytics_job(conn: sqlite3.Connection, event_id: int, job_type: str, trigger_source: str, force: bool = False) -> dict[str, Any]:
    ensure_event_analytics_job_schema(conn)
    if job_type not in {FROZEN_PREDICTION, TOURNAMENT_GRADES}:
        raise ValueError("Unknown event analytics job type")
    existing = conn.execute(
        "SELECT * FROM event_analytics_jobs WHERE event_id=? AND job_type=?",
        (event_id, job_type),
    ).fetchone()
    if existing and existing["status"] in {"QUEUED", "WAITING", "RUNNING"} and not force:
        return dict(existing)
    if existing and existing["status"] == "COMPLETE" and not force and trigger_source != "REPORT_CARD_PAGE":
        return dict(existing)
    now = _now()
    conn.execute(
        """
        INSERT INTO event_analytics_jobs(event_id, job_type, status, requested_at, updated_at, trigger_source)
        VALUES (?, ?, 'QUEUED', ?, ?, ?)
        ON CONFLICT(event_id, job_type) DO UPDATE SET
          status='QUEUED', requested_at=excluded.requested_at, updated_at=excluded.updated_at,
          started_at=NULL, completed_at=NULL, attempts=0, last_error=NULL,
          trigger_source=excluded.trigger_source
        """,
        (event_id, job_type, now, now, trigger_source),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM event_analytics_jobs WHERE event_id=? AND job_type=?", (event_id, job_type)).fetchone())


def event_analytics_job_status(conn: sqlite3.Connection, event_id: int) -> list[dict[str, Any]]:
    ensure_event_analytics_job_schema(conn)
    return [dict(row) for row in conn.execute(
        "SELECT * FROM event_analytics_jobs WHERE event_id=? ORDER BY job_type", (event_id,)
    ).fetchall()]


def _auto_enqueue(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT m.event_id, m.auto_freeze_prediction, m.auto_grade_on_complete,
               m.last_poll_status, e.status, e.bracket_completed
        FROM monitored_events m LEFT JOIN events e ON CAST(e.event_id AS TEXT)=m.event_id
        WHERE m.auto_freeze_prediction=1 OR m.auto_grade_on_complete=1
        """
    ).fetchall()
    for row in rows:
        event_id = int(row["event_id"])
        if row["auto_freeze_prediction"]:
            enqueue_event_analytics_job(conn, event_id, FROZEN_PREDICTION, "MONITOR_AUTOMATION")
        complete = int(row["bracket_completed"] or 0) == 1 or str(row["status"] or row["last_poll_status"] or "").upper() in {"C", "COMPLETE", "COMPLETED"}
        if row["auto_grade_on_complete"] and complete:
            enqueue_event_analytics_job(conn, event_id, TOURNAMENT_GRADES, "MONITOR_AUTOMATION")


def process_one_event_analytics_job(conn: sqlite3.Connection, base_url: str) -> dict[str, Any]:
    ensure_event_analytics_job_schema(conn)
    row = conn.execute(
        "SELECT * FROM event_analytics_jobs WHERE status IN ('QUEUED','WAITING','FAILED') AND attempts < 20 ORDER BY requested_at LIMIT 1"
    ).fetchone()
    if not row:
        return {"status": "IDLE"}
    event_id, job_type = int(row["event_id"]), row["job_type"]
    conn.execute(
        "UPDATE event_analytics_jobs SET status='RUNNING', started_at=COALESCE(started_at, ?), updated_at=?, attempts=attempts+1 WHERE event_id=? AND job_type=?",
        (_now(), _now(), event_id, job_type),
    )
    conn.commit()
    try:
        if job_type == FROZEN_PREDICTION:
            response = requests.get(f"{base_url}/api/events/{event_id}/bracket-probabilities?simulations=10000&refresh=0", timeout=30)
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            pending = response.status_code == 202 or str(payload.get("status") or "").upper() in {"PENDING", "PREGAME_PENDING", "BUILDING", "WAITING_FOR_ROSTER"}
        else:
            response = requests.post(f"{base_url}/api/events/{event_id}/report-cards?refresh=1&refresh_live=0", timeout=120)
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            pending = response.status_code in {409, 425}
        if pending:
            status, error = "WAITING", str(payload.get("message") or payload.get("error") or "Required event data is not ready yet")[:1000]
        elif response.ok:
            status, error = "COMPLETE", None
        else:
            raise RuntimeError(str(payload.get("message") or payload.get("error") or f"HTTP {response.status_code}"))
        conn.execute(
            "UPDATE event_analytics_jobs SET status=?, updated_at=?, completed_at=?, last_error=? WHERE event_id=? AND job_type=?",
            (status, _now(), _now() if status == "COMPLETE" else None, error, event_id, job_type),
        )
        conn.commit()
        return {"status": status, "eventId": event_id, "jobType": job_type}
    except Exception as exc:
        conn.execute(
            "UPDATE event_analytics_jobs SET status='FAILED', updated_at=?, last_error=? WHERE event_id=? AND job_type=?",
            (_now(), str(exc)[:1000], event_id, job_type),
        )
        conn.commit()
        return {"status": "FAILED", "eventId": event_id, "jobType": job_type, "error": str(exc)}


def run_event_analytics_job_cycle(
    db_factory: Callable[[], sqlite3.Connection],
    base_url: str | None = None,
) -> dict[str, Any]:
    """Run one durable analytics-queue cycle in the caller's worker loop.

    Keeping this callable outside the daemon-thread wrapper lets the production
    supervisor own the queue directly, so a dead child thread cannot leave
    grade and frozen-prediction jobs permanently QUEUED with zero attempts.
    """
    target_url = (base_url or os.getenv("INTERNAL_WEB_URL", "http://web:5173")).rstrip("/")
    with db_factory() as conn:
        from shared_viewer_profile import enroll_default_player_brackets_from_collected_rosters

        enrollment = enroll_default_player_brackets_from_collected_rosters(conn)
        _auto_enqueue(conn)
        result = process_one_event_analytics_job(conn, target_url)
    result["defaultPlayerEnrollment"] = enrollment
    return result


def start_event_analytics_job_worker(db_factory: Callable[[], sqlite3.Connection]) -> None:
    base_url = os.getenv("INTERNAL_WEB_URL", "http://web:5173").rstrip("/")

    def worker() -> None:
        time.sleep(15)
        while True:
            try:
                result = run_event_analytics_job_cycle(db_factory, base_url)
                enrollment = result.pop("defaultPlayerEnrollment", {})
                if enrollment.get("newlyEnabled"):
                    print(f"Default-player brackets enrolled: {enrollment}", flush=True)
                if result.get("status") != "IDLE":
                    print(f"Event analytics job: {result}", flush=True)
            except Exception as exc:
                print(f"Event analytics queue cycle failed: {exc}", flush=True)
            time.sleep(10)

    threading.Thread(target=worker, daemon=True, name="event-analytics-jobs").start()
