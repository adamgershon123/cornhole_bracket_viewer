"""Lower-priority archival, integrity, repair, and model-research worker."""
from __future__ import annotations

import os
import signal
import time

from app import DATA_DIR
from automated_pattern_discovery import start_automated_discovery_worker
from cloud_worker import start_backtest_refresh_worker, start_data_integrity_worker
from double_dip_analysis import start_double_dip_history_worker
from historical_tournament_replay import start_historical_tournament_replay_worker
from payload_archive import start_payload_archive_worker
from predictive_player_profile import start_player_analytics_snapshot_worker
from season_platform import db as season_platform_db, normalize_match_stats_to_rounds
from walker_repair import start_walker_repair_worker

running = True


def stop_worker(*_: object) -> None:
    global running
    running = False


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    delay = max(0, int(os.getenv("ANALYTICS_STARTUP_DELAY_SECONDS", "60")))
    deadline = time.monotonic() + delay
    while running and time.monotonic() < deadline:
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    if running:
        start_payload_archive_worker(season_platform_db)
        start_player_analytics_snapshot_worker(season_platform_db)
        start_double_dip_history_worker(season_platform_db, data_dir=DATA_DIR)
        start_historical_tournament_replay_worker(season_platform_db, data_dir=DATA_DIR)
        start_backtest_refresh_worker()
        start_data_integrity_worker()
        start_automated_discovery_worker(season_platform_db)
        start_walker_repair_worker(season_platform_db, DATA_DIR, normalize_match_stats_to_rounds)
        print("Analytics and research worker started", flush=True)
    while running:
        time.sleep(1)
