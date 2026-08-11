"""Print a compact inventory of normalized games and v2 certification state."""
from __future__ import annotations

import argparse
import json
import sqlite3


def scalar(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    args = parser.parse_args()
    conn = sqlite3.connect(args.database, timeout=60)
    try:
        has_integrity = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='game_data_integrity'"
        ).fetchone())
        result = {
            "playerRoundRows": scalar(conn, "SELECT COUNT(*) FROM player_rounds"),
            "normalizedGames": scalar(conn, "SELECT COUNT(*) FROM (SELECT DISTINCT event_id,match_id,game_id FROM player_rounds)"),
            "normalizedEvents": scalar(conn, "SELECT COUNT(DISTINCT event_id) FROM player_rounds"),
            "verifiedGames": scalar(conn, "SELECT COUNT(*) FROM game_data_integrity WHERE analytics_ready=1") if has_integrity else 0,
            "quarantinedGames": scalar(conn, "SELECT COUNT(*) FROM game_data_integrity WHERE integrity_status='QUARANTINED'") if has_integrity else 0,
        }
        has_payloads = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_payloads'"
        ).fetchone())
        if has_payloads:
            payload_rows = conn.execute(
                """
                SELECT source_endpoint, COUNT(*) AS count,
                       SUM(CASE WHEN archive_verified_at IS NOT NULL THEN 1 ELSE 0 END) AS archived,
                       SUM(CASE WHEN COALESCE(payload_json,'') != '' THEN 1 ELSE 0 END) AS inline
                FROM source_payloads
                GROUP BY source_endpoint
                ORDER BY count DESC
                """
            ).fetchall()
            result["sourcePayloads"] = [
                {"endpoint": row[0], "count": int(row[1]), "archived": int(row[2] or 0), "inline": int(row[3] or 0)}
                for row in payload_rows
            ]
            result["matchStatsExamples"] = [
                {"id": int(row[0]), "entityKey": row[1], "archivePath": row[2]}
                for row in conn.execute(
                    """SELECT source_payload_id,entity_key,archive_path
                       FROM source_payloads WHERE source_endpoint='match-stats'
                       ORDER BY source_payload_id LIMIT 5"""
                ).fetchall()
            ]
        result["legacyUnverifiedGames"] = result["normalizedGames"] - result["verifiedGames"]
        print(json.dumps(result, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
