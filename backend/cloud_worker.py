"""Production background-worker entry point.

The web process is intentionally kept separate so collection and model work
cannot make the public interface unresponsive under concurrent traffic.
"""
from __future__ import annotations

import os
import signal
import threading
import time

from app import DATA_DIR, start_prediction_lifecycle_worker
from double_dip_analysis import start_double_dip_history_worker
from historical_backfill import start_worker as start_historical_backfill_worker
from historical_archive_backtest import auto_refresh_backtest
from historical_tournament_replay import start_historical_tournament_replay_worker
from lifecycle_runner import start_prediction_operations_snapshot_worker
from payload_archive import start_payload_archive_worker
from predictive_player_profile import start_player_analytics_snapshot_worker
from season_platform import db as season_platform_db
from integrity_backfill import audit_cached_match_stats
from automated_pattern_discovery import start_automated_discovery_worker


running = True


def stop_worker(*_: object) -> None:
    global running
    running = False


def start_backtest_refresh_worker() -> None:
    def worker() -> None:
        time.sleep(45)
        while running:
            try:
                with season_platform_db() as conn:
                    result = auto_refresh_backtest(conn)
                if result.get("status") == "REFRESHED":
                    print(
                        "Historical backtest refreshed: "
                        f"{result.get('eligibleMatchups', 0)} eligible matchups",
                        flush=True,
                    )
            except Exception as exc:
                print(f"Historical backtest refresh failed: {exc}", flush=True)
            for _ in range(60):
                if not running:
                    return
                time.sleep(5)

    threading.Thread(
        target=worker,
        daemon=True,
        name="historical-backtest-refresh",
    ).start()


def start_data_integrity_worker() -> None:
    apply_migration = os.getenv("DATA_INTEGRITY_V2_APPLY", "0").strip().lower() in {"1", "true", "yes", "on"}

    def worker() -> None:
        time.sleep(30)
        while running:
            try:
                with season_platform_db() as conn:
                    result = audit_cached_match_stats(conn, DATA_DIR, apply=apply_migration, limit=25)
                if result.get("validated") or result.get("quarantined"):
                    print(
                        f"Data Integrity v2 ({result.get('mode')}): "
                        f"{result.get('validated', 0)} verified, "
                        f"{result.get('quarantined', 0)} quarantined, "
                        f"{result.get('remaining', 0)} awaiting migration",
                        flush=True,
                    )
            except Exception as exc:
                print(f"Data Integrity v2 cycle failed: {exc}", flush=True)
            for _ in range(12):
                if not running:
                    return
                time.sleep(5)

    threading.Thread(target=worker, daemon=True, name="data-integrity-v2").start()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    start_prediction_lifecycle_worker()
    start_historical_backfill_worker()
    start_payload_archive_worker(season_platform_db)
    start_player_analytics_snapshot_worker(season_platform_db)
    start_double_dip_history_worker(season_platform_db, data_dir=DATA_DIR)
    start_historical_tournament_replay_worker(season_platform_db, data_dir=DATA_DIR)
    start_backtest_refresh_worker()
    start_data_integrity_worker()
    start_automated_discovery_worker(season_platform_db)
    start_prediction_operations_snapshot_worker(season_platform_db)
    while running:
        time.sleep(5)
