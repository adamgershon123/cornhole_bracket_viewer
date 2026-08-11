"""Create a consistent SQLite backup while the source database remains online."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    destination = Path(args.destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(args.source, timeout=60)
    destination_conn = sqlite3.connect(destination, timeout=60)
    try:
        source_conn.backup(destination_conn)
    finally:
        destination_conn.close()
        source_conn.close()
    print(f"SQLite backup complete: {destination} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
