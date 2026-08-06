from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests

from provenance import record_source_payload
from statistic_observations import extract_statistic_observations


PLAYER_COMPARE_URL = "https://api.iplayacl.com/api/v1/player-compare-stats"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _players_with_fresh_ppr(
    conn: sqlite3.Connection,
    *,
    player_ids: list[int],
    max_age_hours: int,
) -> set[int]:
    if not player_ids:
        return set()
    placeholders = ",".join("?" for _ in player_ids)
    fresh_after = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    rows = conn.execute(
        f"""
        SELECT DISTINCT player_id
        FROM statistic_observations
        WHERE statistic_type='ACL_REPORTED_SEASON_PPR'
          AND availability_status='AVAILABLE'
          AND retrieved_at >= ?
          AND player_id IN ({placeholders})
        """,
        [fresh_after, *player_ids],
    ).fetchall()
    return {int(row[0]) for row in rows}


def hydrate_acl_prediction_assistance(
    conn: sqlite3.Connection,
    *,
    player_ids: Iterable[int],
    bucket_id: int = 11,
    max_age_hours: int = 6,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Fetch one lightweight ACL season-stat batch for players lacking fresh PPR.

    This is the rapid prediction path. Full round history remains a separate
    background operation and is never awaited here.
    """
    requested = sorted({int(player_id) for player_id in player_ids if player_id})
    fresh = _players_with_fresh_ppr(
        conn,
        player_ids=requested,
        max_age_hours=max_age_hours,
    )
    missing = [player_id for player_id in requested if player_id not in fresh]
    summary: dict[str, Any] = {
        "requestedPlayers": len(requested),
        "freshPlayers": len(fresh),
        "fetchedPlayers": 0,
        "assistedPlayers": 0,
        "requestCount": 0,
        "status": "READY" if not missing else "PENDING",
    }
    if not missing:
        return summary

    retrieved_at = utc_now()
    payload = {"playerIDs": missing, "bucketID": int(bucket_id)}
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://app.iplayacl.com",
        "referer": "https://app.iplayacl.com/",
        "user-agent": "Mozilla/5.0",
        "x-app-version": "14.1.0",
    }
    summary["requestCount"] = 1
    try:
        response = requests.post(
            PLAYER_COMPARE_URL,
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        rows = body.get("data", []) if isinstance(body, dict) else []
        returned_ids = {
            int(row["playerID"])
            for row in rows
            if isinstance(row, dict)
            and row.get("playerID") not in (None, "")
            and row.get("ptsPerRnd") not in (None, "")
        }
        batch_key = hashlib.sha256(
            ",".join(str(player_id) for player_id in missing).encode("utf-8")
        ).hexdigest()[:16]
        source_payload_id = record_source_payload(
            conn,
            source_endpoint="player-compare-stats",
            entity_key=f"bucket:{bucket_id}:prediction-batch:{batch_key}",
            request_url=PLAYER_COMPARE_URL,
            payload=body,
            retrieved_at=retrieved_at,
            http_status=response.status_code,
        )
        extract_statistic_observations(
            conn,
            source_payload_id=source_payload_id,
            source_endpoint="player-compare-stats",
            entity_key=f"bucket:{bucket_id}",
            payload=body,
            retrieved_at=retrieved_at,
        )
        summary.update(
            {
                "fetchedPlayers": len(missing),
                "assistedPlayers": len(returned_ids),
                "status": "READY" if len(returned_ids) == len(missing) else "PARTIAL",
                "missingPlayerIds": sorted(set(missing) - returned_ids),
                "retrievedAt": retrieved_at,
            }
        )
    except Exception as exc:
        summary.update({"status": "FAILED", "error": str(exc)})
    return summary
