"""Inspect whether quarantined team-id conflicts retain usable H/A sides."""
from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("audit_json")
    parser.add_argument("archive_root")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8"))
    database_uri = f"file:{Path(args.database).resolve().as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(database_uri, timeout=60, uri=True)
    conn.row_factory = sqlite3.Row
    results = []
    try:
        for game in audit.get("games", []):
            codes = {error["code"] for error in game.get("checks", {}).get("errors", [])}
            if game.get("status") != "WOULD_QUARANTINE" or "ROUND_SAME_TEAM" not in codes:
                continue
            entity = f"match-stats:{game['eventId']}:{game['matchId']}:{game['gameId']}"
            source = conn.execute(
                """SELECT archive_path FROM source_payloads
                   WHERE source_endpoint='match-stats' AND entity_key=?
                   ORDER BY retrieved_at DESC,source_payload_id DESC LIMIT 1""",
                (entity,),
            ).fetchone()
            if not source or not source["archive_path"]:
                continue
            with gzip.open(Path(args.archive_root) / source["archive_path"], "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload.get("payload"), dict):
                payload = payload["payload"]
            rows = payload.get("event_match_inning_history", []) or []
            side_pairs = {}
            player_sides = {}
            for row in rows:
                round_no = str(row.get("inningno"))
                side = str(row.get("teamhomeaway") or "").upper()
                side_pairs.setdefault(round_no, []).append(side)
                player_sides.setdefault(str(row.get("playerid")), set()).add(side)
            distinct_sides_per_round = all(
                len(values) == 2 and set(values) == {"H", "A"}
                for values in side_pairs.values()
            )
            stable_player_sides = all(len(values) == 1 and "" not in values for values in player_sides.values())
            results.append({
                "eventId": game["eventId"], "matchId": game["matchId"],
                "distinctSidesEveryRound": distinct_sides_per_round,
                "stablePlayerSides": stable_player_sides,
                "rounds": len(side_pairs), "players": len(player_sides),
            })
    finally:
        conn.close()
    summary = {
        "games": len(results),
        "fullyRecoverable": sum(
            item["distinctSidesEveryRound"] and item["stablePlayerSides"] for item in results
        ),
        "notRecoverable": [
            item for item in results
            if not (item["distinctSidesEveryRound"] and item["stablePlayerSides"])
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
