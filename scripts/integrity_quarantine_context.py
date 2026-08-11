"""Join dry-run quarantine examples to event format metadata."""
from __future__ import annotations

import argparse
import json
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("audit_json")
    args = parser.parse_args()
    audit = json.loads(open(args.audit_json, encoding="utf-8").read())
    conn = sqlite3.connect(args.database, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        examples = []
        for game in audit.get("games", []):
            if game.get("status") != "WOULD_QUARANTINE":
                continue
            event = conn.execute(
                """SELECT event_id,event_name,match_type,bracket_type,blind_draw
                   FROM events WHERE event_id=?""",
                (int(game["eventId"]),),
            ).fetchone()
            examples.append({
                "event": dict(event) if event else {"event_id": game["eventId"]},
                "matchId": game["matchId"],
                "gameId": game["gameId"],
                "codes": sorted({error["code"] for error in game.get("checks", {}).get("errors", [])}),
            })
        print(json.dumps(examples, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
