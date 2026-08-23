"""Dedicated historical collection worker.

Collection intentionally runs in its own process so archival analytics cannot
starve the collection queue through the process-wide SQLite background lane.
"""
from __future__ import annotations

import os
import signal
import time

from historical_backfill import start_worker as start_historical_backfill_worker

running = True


def stop_worker(*_: object) -> None:
    global running
    running = False


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    delay = max(0, int(os.getenv("COLLECTION_STARTUP_DELAY_SECONDS", "20")))
    deadline = time.monotonic() + delay
    while running and time.monotonic() < deadline:
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    if running:
        start_historical_backfill_worker()
        print("Dedicated historical collection worker started", flush=True)
    while running:
        time.sleep(1)
