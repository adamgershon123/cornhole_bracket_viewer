"""Production background-worker entry point.

The web process is intentionally kept separate so collection and model work
cannot make the public interface unresponsive under concurrent traffic.
"""
from __future__ import annotations

import signal
import time

from app import start_prediction_lifecycle_worker
from historical_backfill import start_worker as start_historical_backfill_worker
from payload_archive import start_payload_archive_worker
from predictive_player_profile import start_player_analytics_snapshot_worker
from season_platform import db as season_platform_db


running = True


def stop_worker(*_: object) -> None:
    global running
    running = False


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    start_prediction_lifecycle_worker()
    start_historical_backfill_worker()
    start_payload_archive_worker(season_platform_db)
    start_player_analytics_snapshot_worker(season_platform_db)
    while running:
        time.sleep(5)

