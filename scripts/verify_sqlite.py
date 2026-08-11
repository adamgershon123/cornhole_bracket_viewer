"""Verify a SQLite backup without modifying it."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    args = parser.parse_args()
    database = Path(args.database).resolve().as_posix()
    connection = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True)
    try:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        # Emit and flush the safety-critical result before optional inventory
        # queries, so a schema-version mismatch cannot hide it.
        print(json.dumps({"quickCheck": quick_check}), flush=True)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        result = {"quickCheck": quick_check}
        if "games" in tables:
            result["games"] = connection.execute(
                "SELECT COUNT(*) FROM games"
            ).fetchone()[0]
        if "player_rounds" in tables:
            result["playerRounds"] = connection.execute(
                "SELECT COUNT(*) FROM player_rounds"
            ).fetchone()[0]
    finally:
        connection.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
