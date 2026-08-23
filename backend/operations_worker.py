"""Time-sensitive prediction and event-analytics worker."""
from __future__ import annotations

import os
import signal
import time

from app import start_prediction_lifecycle_worker
from event_analytics_jobs import run_event_analytics_job_cycle
from lifecycle_runner import start_prediction_operations_snapshot_worker
from season_platform import db as season_platform_db

running = True


def stop_worker(*_: object) -> None:
    global running
    running = False


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    delay = max(0, int(os.getenv("OPERATIONS_STARTUP_DELAY_SECONDS", "20")))
    deadline = time.monotonic() + delay
    while running and time.monotonic() < deadline:
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    if running:
        start_prediction_lifecycle_worker()
        start_prediction_operations_snapshot_worker(season_platform_db)
        print("Prediction and event analytics worker started", flush=True)
    while running:
        try:
            result = run_event_analytics_job_cycle(season_platform_db)
            enrollment = result.pop("defaultPlayerEnrollment", {})
            if enrollment.get("newlyEnabled"):
                print(f"Default-player brackets enrolled: {enrollment}", flush=True)
            if result.get("status") != "IDLE":
                print(f"Event analytics job: {result}", flush=True)
        except Exception as exc:
            print(f"Event analytics queue cycle failed: {exc}", flush=True)
        for _ in range(10):
            if not running:
                break
            time.sleep(1)
