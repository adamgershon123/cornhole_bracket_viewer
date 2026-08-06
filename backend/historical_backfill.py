from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from season_platform import (
    DATA_DIR,
    db,
    fetch_bracket,
    fetch_event_player_classifications,
    fetch_match_stats,
    fetch_player_events,
    fetch_swap_standings,
    fetch_swap_up_next,
    index_relevant_matches,
    normalize_match_stats_to_rounds,
)


WORKER_LOCK = threading.Lock()
WORKER_STARTED = False
DEFAULT_BUCKET_ID = int(os.environ.get("HISTORICAL_BACKFILL_BUCKET_ID", "11"))
MIN_INTERVAL_SECONDS = max(
    8.0, float(os.environ.get("HISTORICAL_BACKFILL_MIN_INTERVAL_SECONDS", "10"))
)
MAX_INTERVAL_SECONDS = max(
    MIN_INTERVAL_SECONDS,
    float(os.environ.get("HISTORICAL_BACKFILL_MAX_INTERVAL_SECONDS", "20")),
)
MAX_ATTEMPTS = max(
    1, int(os.environ.get("HISTORICAL_BACKFILL_MAX_ATTEMPTS", "5"))
)
PRIORITY_THRESHOLD = int(
    os.environ.get("HISTORICAL_BACKFILL_PRIORITY_THRESHOLD", "900")
)
PREDICTION_LANE = "PREDICTION"
CLASSIFIED_LANE = "ACL_CLASSIFIED"
CONTACT_LANE = "CONTACT_ENRICHMENT"
COLLECTION_LANES = (PREDICTION_LANE, CLASSIFIED_LANE, CONTACT_LANE)
# Completed games produce the training rows that make the crawl useful. Keep
# discovery moving, but reserve most worker turns for converting known events
# into brackets and known games into round data.
WORK_SCHEDULE = ("GAME", "GAME", "GAME", "GAME", "EVENT", "PLAYER")
US_REGIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}
CANADIAN_REGIONS = {
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK",
    "ALBERTA", "BRITISH COLUMBIA", "MANITOBA", "NEW BRUNSWICK",
    "NEWFOUNDLAND AND LABRADOR", "NOVA SCOTIA", "ONTARIO",
    "PRINCE EDWARD ISLAND", "QUEBEC", "SASKATCHEWAN",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS historical_backfill_state (
            state_id INTEGER PRIMARY KEY CHECK(state_id=1),
            paused INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_started_at TEXT,
            last_activity_at TEXT,
            last_success_at TEXT,
            last_error_at TEXT,
            last_error TEXT,
            current_item_type TEXT,
            current_item_key TEXT,
            tasks_completed INTEGER NOT NULL DEFAULT 0,
            tasks_failed INTEGER NOT NULL DEFAULT 0,
            events_discovered INTEGER NOT NULL DEFAULT 0,
            players_discovered INTEGER NOT NULL DEFAULT 0,
            games_downloaded INTEGER NOT NULL DEFAULT 0,
            rounds_added INTEGER NOT NULL DEFAULT 0,
            auth_blocked INTEGER NOT NULL DEFAULT 0,
            baseline_events INTEGER NOT NULL DEFAULT 0,
            baseline_players INTEGER NOT NULL DEFAULT 0,
            baseline_games INTEGER NOT NULL DEFAULT 0,
            baseline_rounds INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS historical_backfill_queue (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            player_id INTEGER,
            event_id INTEGER,
            match_id TEXT,
            game_id INTEGER,
            bucket_id INTEGER,
            priority INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            discovered_from TEXT,
            not_before TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            collection_lane TEXT NOT NULL DEFAULT 'PREDICTION',
            UNIQUE(item_type, item_key)
        );

        CREATE TABLE IF NOT EXISTS historical_backfill_lane_state (
            lane TEXT PRIMARY KEY,
            paused INTEGER NOT NULL DEFAULT 0,
            current_item_type TEXT,
            current_item_key TEXT,
            tasks_completed INTEGER NOT NULL DEFAULT 0,
            tasks_failed INTEGER NOT NULL DEFAULT 0,
            last_activity_at TEXT,
            last_success_at TEXT,
            last_error_at TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS historical_backfill_activity (
            activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_id INTEGER,
            collection_lane TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            outcome TEXT NOT NULL,
            productive INTEGER NOT NULL DEFAULT 0,
            terminal INTEGER NOT NULL DEFAULT 0,
            events_discovered INTEGER NOT NULL DEFAULT 0,
            players_discovered INTEGER NOT NULL DEFAULT 0,
            games_downloaded INTEGER NOT NULL DEFAULT 0,
            rounds_added INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            occurred_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_historical_backfill_next
            ON historical_backfill_queue(status, not_before, priority DESC, queue_id);
        CREATE INDEX IF NOT EXISTS idx_historical_backfill_activity_time
            ON historical_backfill_activity(occurred_at, collection_lane);
        """
    )
    now = utc_now()
    counts = _ledger_counts(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO historical_backfill_state(
            state_id, paused, created_at, updated_at,
            baseline_events, baseline_players, baseline_games, baseline_rounds
        ) VALUES (1, 0, ?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            now,
            counts["events"],
            counts["players"],
            counts["games"],
            counts["rounds"],
        ),
    )
    queue_columns = {
        row[1] for row in conn.execute(
            "PRAGMA table_info(historical_backfill_queue)"
        ).fetchall()
    }
    if "collection_lane" not in queue_columns:
        conn.execute(
            """
            ALTER TABLE historical_backfill_queue
            ADD COLUMN collection_lane TEXT NOT NULL DEFAULT 'PREDICTION'
            """
        )
    conn.execute(
        """
        UPDATE historical_backfill_queue
        SET collection_lane='ACL_CLASSIFIED'
        WHERE collection_lane!='ACL_CLASSIFIED'
          AND (
              discovered_from LIKE 'pro-roster:%'
              OR discovered_from='acl-pro-stat-build'
          )
        """
    )
    for lane in COLLECTION_LANES:
        conn.execute(
            """
            INSERT OR IGNORE INTO historical_backfill_lane_state(lane, updated_at)
            VALUES (?, ?)
            """,
            (lane, now),
        )
    conn.commit()


def promote_cached_event_geography(conn: sqlite3.Connection) -> int:
    """Promote already-downloaded bracket coordinates without another API call."""
    from payload_archive import load_source_payload

    rows = conn.execute(
        """
        SELECT e.event_id, e.location_lat, e.location_lng, e.location_country,
               (
                   SELECT s.source_payload_id
                   FROM source_payloads s
                   WHERE s.source_endpoint='bracket-data'
                     AND s.entity_key='bracket:' || e.event_id
                   ORDER BY s.source_payload_id DESC
                   LIMIT 1
               ) AS source_payload_id
        FROM events e
        WHERE e.location_lat IS NULL OR e.location_lng IS NULL
           OR e.location_country IS NULL
        """
    ).fetchall()
    promoted = 0
    for row in rows:
        if row["source_payload_id"] is None:
            continue
        try:
            payload = load_source_payload(conn, int(row["source_payload_id"]))
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            continue
        event_info = payload.get("eventInfo") if isinstance(payload, dict) else {}
        event_info = event_info if isinstance(event_info, dict) else {}
        latitude = row["location_lat"]
        longitude = row["location_lng"]
        country = row["location_country"]
        latitude = latitude if latitude is not None else event_info.get("locationLat")
        longitude = longitude if longitude is not None else event_info.get("locationLng")
        country = country or event_info.get("countryCode")
        if latitude is None and longitude is None and not country:
            continue
        conn.execute(
            """
            UPDATE events
            SET location_lat=?, location_lng=?, location_country=?
            WHERE event_id=?
            """,
            (latitude, longitude, country, row["event_id"]),
        )
        promoted += 1
    conn.commit()
    return promoted


def seed_known_players(conn: sqlite3.Connection) -> int:
    initialize_schema(conn)
    rows = conn.execute(
        """
        SELECT player_id,
               COUNT(*) AS rounds,
               COUNT(DISTINCT location_id) AS venues
        FROM player_rounds
        WHERE player_id IS NOT NULL
        GROUP BY player_id
        ORDER BY venues DESC, rounds DESC
        """
    ).fetchall()
    inserted = 0
    for row in rows:
        priority = 100 + min(int(row["venues"] or 0) * 10, 100)
        inserted += _enqueue_player(
            conn,
            int(row["player_id"]),
            DEFAULT_BUCKET_ID,
            priority=priority,
            source="existing-ledger",
        )
    conn.commit()
    return inserted


def status_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_schema(conn)
    state = dict(conn.execute(
        "SELECT * FROM historical_backfill_state WHERE state_id=1"
    ).fetchone())
    queue = {
        row["status"]: int(row["count"])
        for row in conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM historical_backfill_queue GROUP BY status
            """
        ).fetchall()
    }
    by_type = [
        dict(row) for row in conn.execute(
            """
            SELECT item_type, status, COUNT(*) AS count
            FROM historical_backfill_queue
            GROUP BY item_type, status
            ORDER BY item_type, status
            """
        ).fetchall()
    ]
    ledger = _ledger_counts(conn)
    geography = _geography_summary(conn)
    priority_pending = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM historical_backfill_queue
            WHERE status IN ('PENDING', 'PROCESSING') AND priority >= ?
            """,
            (PRIORITY_THRESHOLD,),
        ).fetchone()[0]
    )
    lane_states = {
        row["lane"]: dict(row)
        for row in conn.execute(
            "SELECT * FROM historical_backfill_lane_state ORDER BY lane"
        ).fetchall()
    }
    lane_counts = {
        lane: {
            row["status"]: int(row["count"])
            for row in conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM historical_backfill_queue
                WHERE collection_lane=?
                GROUP BY status
                """,
                (lane,),
            ).fetchall()
        }
        for lane in COLLECTION_LANES
    }
    from payload_archive import payload_archive_health

    throughput = {
        label: _throughput_since(conn, datetime.now(timezone.utc) - delta)
        for label, delta in (
            ("lastHour", timedelta(hours=1)),
            ("last24Hours", timedelta(hours=24)),
        )
    }

    return {
        "enabled": True,
        "paused": bool(state["paused"]),
        "status": (
            "PAUSED" if state["paused"]
            else "WORKING" if state.get("current_item_type")
            else "RUNNING"
        ),
        "intervalSeconds": round(
            (MIN_INTERVAL_SECONDS + MAX_INTERVAL_SECONDS) / 2,
            1,
        ),
        "pacing": {
            "mode": "CONSERVATIVE_JITTER",
            "minimumSeconds": MIN_INTERVAL_SECONDS,
            "maximumSeconds": MAX_INTERVAL_SECONDS,
            "cachedTaskDelaySeconds": "0.05-0.25",
            "cacheFirst": True,
            "concurrentRequests": 1,
            "priorityFastLane": {
                "enabled": True,
                "threshold": PRIORITY_THRESHOLD,
                "artificialDelaySeconds": 0,
                "retryBackoffSeconds": 0,
                "pending": priority_pending,
            },
        },
        "stateRetainedAtStartup": True,
        "payloadArchive": payload_archive_health(conn),
        "throughput": throughput,
        "lanes": {
            lane: {
                "lane": lane,
                "label": (
                    "Prediction history"
                    if lane == PREDICTION_LANE
                    else "ACL-classified players"
                    if lane == CLASSIFIED_LANE
                    else "Contact enrichment"
                ),
                "paused": bool(lane_states[lane]["paused"]),
                "status": (
                    "PAUSED"
                    if lane_states[lane]["paused"]
                    else "WORKING"
                    if lane_states[lane].get("current_item_type")
                    else "RUNNING"
                ),
                "current": {
                    "type": lane_states[lane].get("current_item_type"),
                    "key": lane_states[lane].get("current_item_key"),
                },
                "queue": {
                    "pending": lane_counts[lane].get("PENDING", 0),
                    "processing": lane_counts[lane].get("PROCESSING", 0),
                    "complete": lane_counts[lane].get("COMPLETE", 0),
                    "failed": lane_counts[lane].get("FAILED", 0),
                },
                "tasksCompleted": int(lane_states[lane]["tasks_completed"]),
                "tasksFailed": int(lane_states[lane]["tasks_failed"]),
                "lastActivityAt": lane_states[lane].get("last_activity_at"),
                "lastSuccessAt": lane_states[lane].get("last_success_at"),
                "lastErrorAt": lane_states[lane].get("last_error_at"),
                "lastError": lane_states[lane].get("last_error"),
            }
            for lane in COLLECTION_LANES
        },
        "current": {
            "type": state.get("current_item_type"),
            "key": state.get("current_item_key"),
        },
        "timestamps": {
            "createdAt": state.get("created_at"),
            "lastStartedAt": state.get("last_started_at"),
            "lastActivityAt": state.get("last_activity_at"),
            "lastSuccessAt": state.get("last_success_at"),
            "lastErrorAt": state.get("last_error_at"),
        },
        "lastError": state.get("last_error"),
        "queue": {
            "pending": queue.get("PENDING", 0),
            "processing": queue.get("PROCESSING", 0),
            "complete": queue.get("COMPLETE", 0),
            "failed": queue.get("FAILED", 0),
            "priorityPending": priority_pending,
            "byType": by_type,
        },
        "session": {
            "tasksCompleted": int(state["tasks_completed"]),
            "tasksFailed": int(state["tasks_failed"]),
            "eventsDiscovered": int(state["events_discovered"]),
            "playersDiscovered": int(state["players_discovered"]),
            "gamesDownloaded": int(state["games_downloaded"]),
            "roundsAdded": int(state["rounds_added"]),
            "authBlocked": int(state["auth_blocked"]),
        },
        "ledger": ledger,
        "geography": geography,
        "gatheredSinceActivation": {
            key: ledger[key] - int(state[f"baseline_{key}"])
            for key in ("events", "players", "games", "rounds")
        },
        "policy": {
            "mode": "PLAYER_EVENT_GRAPH",
            "sequentialIdScan": False,
            "completedResponsesCached": True,
            "contactDataRetainedInPrivateSourceCache": True,
            "contactDataPublishedInPublicStats": False,
            "cookieFallback": False,
            "maximumAttempts": MAX_ATTEMPTS,
        },
    }


def set_paused(conn: sqlite3.Connection, paused: bool) -> dict[str, Any]:
    initialize_schema(conn)
    conn.execute(
        """
        UPDATE historical_backfill_state
        SET paused=?, updated_at=?, current_item_type=NULL, current_item_key=NULL
        WHERE state_id=1
        """,
        (1 if paused else 0, utc_now()),
    )
    if not paused:
        conn.execute(
            """
            UPDATE historical_backfill_queue
            SET status='PENDING', updated_at=?
            WHERE status='PROCESSING'
            """,
            (utc_now(),),
        )
    conn.commit()
    return status_snapshot(conn)


def set_lane_paused(
    conn: sqlite3.Connection,
    lane: str,
    paused: bool,
) -> dict[str, Any]:
    initialize_schema(conn)
    normalized = str(lane or "").strip().upper()
    if normalized not in COLLECTION_LANES:
        raise ValueError("Unknown collection lane")
    conn.execute(
        """
        UPDATE historical_backfill_lane_state
        SET paused=?, current_item_type=NULL, current_item_key=NULL, updated_at=?
        WHERE lane=?
        """,
        (1 if paused else 0, utc_now(), normalized),
    )
    if not paused:
        conn.execute(
            """
            UPDATE historical_backfill_queue
            SET status='PENDING', updated_at=?
            WHERE status='PROCESSING' AND collection_lane=?
            """,
            (utc_now(), normalized),
        )
    conn.commit()
    return status_snapshot(conn)


def prioritize_events(
    conn: sqlite3.Connection,
    event_ids: list[int],
    *,
    source: str,
    priority: int = 1000,
    requeue_completed: bool = True,
) -> dict[str, Any]:
    initialize_schema(conn)
    prioritized = 0
    skipped_complete = 0
    for event_id in sorted({int(value) for value in event_ids}):
        event = conn.execute(
            """
            SELECT bracket_downloaded, bracket_completed,
                   match_stats_targets, match_stats_downloaded
            FROM events WHERE event_id=?
            """,
            (event_id,),
        ).fetchone()
        if event is not None:
            targets = int(event["match_stats_targets"] or 0)
            downloaded = int(event["match_stats_downloaded"] or 0)
            if (
                bool(event["bracket_downloaded"])
                and bool(event["bracket_completed"])
                and targets > 0
                and downloaded >= targets
            ):
                skipped_complete += 1
                continue
        _enqueue_event(
            conn,
            event_id,
            priority=priority,
            source=source,
        )
        conn.execute(
            """
            UPDATE historical_backfill_queue
            SET priority=?, status='PENDING', attempts=0, not_before=NULL,
                last_error=NULL, completed_at=NULL, discovered_from=?,
                updated_at=?
            WHERE item_type='EVENT' AND item_key=?
              AND status != 'PROCESSING'
              AND (? OR status != 'COMPLETE')
            """,
            (
                priority,
                source,
                utc_now(),
                str(event_id),
                1 if requeue_completed else 0,
            ),
        )
        prioritized += 1
    conn.commit()
    return {
        "requested": len(set(event_ids)),
        "prioritized": prioritized,
        "skippedFullyDownloaded": skipped_complete,
        "priority": priority,
    }


def start_worker() -> None:
    global WORKER_STARTED
    with WORKER_LOCK:
        if WORKER_STARTED:
            return
        WORKER_STARTED = True

    def worker(lane: str) -> None:
        time.sleep(10)
        try:
            with db() as conn:
                initialize_schema(conn)
                if lane == PREDICTION_LANE:
                    promote_cached_event_geography(conn)
                    seed_known_players(conn)
                elif lane == CONTACT_LANE:
                    seed_contact_backfill(conn)
                    from director_directory import refresh_director_index
                    refresh_director_index(conn, limit=250)
                conn.execute(
                    """
                    UPDATE historical_backfill_state
                    SET last_started_at=?, updated_at=?
                    WHERE state_id=1
                    """,
                    (utc_now(), utc_now()),
                )
                conn.commit()
        except Exception as exc:
            print(f"Historical backfill initialization failed: {exc}")
        while True:
            result: dict[str, Any] = {"status": "IDLE", "networkRequests": 0}
            try:
                with db() as conn:
                    result = run_one(conn, lane=lane, initialize=False)
            except Exception as exc:
                print(f"Historical backfill {lane} cycle failed: {exc}")
                result = {"status": "FAILED", "networkRequests": 1}
            is_priority = int(result.get("queuePriority") or 0) >= PRIORITY_THRESHOLD
            if is_priority:
                # Explicitly prioritized work is the fast lane. It runs
                # continuously and sequentially, with no artificial pacing
                # between requests.
                delay = 0
            elif int(result.get("networkRequests") or 0) > 0:
                # A single worker plus a conservative, variable delay prevents
                # request bursts and spreads load without attempting to bypass
                # ACL access controls.
                delay = random.uniform(
                    MIN_INTERVAL_SECONDS,
                    MAX_INTERVAL_SECONDS,
                )
            else:
                delay = random.uniform(0.05, 0.25)
            time.sleep(delay)

    for lane in COLLECTION_LANES:
        threading.Thread(
            target=worker,
            args=(lane,),
            daemon=True,
            name=f"historical-backfill-{lane.lower()}",
        ).start()


def run_one(
    conn: sqlite3.Connection,
    lane: str = PREDICTION_LANE,
    *,
    initialize: bool = True,
) -> dict[str, Any]:
    if initialize:
        initialize_schema(conn)
    lane = str(lane or PREDICTION_LANE).strip().upper()
    if lane not in COLLECTION_LANES:
        raise ValueError("Unknown collection lane")
    state = conn.execute(
        """
        SELECT paused, tasks_completed, tasks_failed
        FROM historical_backfill_state WHERE state_id=1
        """
    ).fetchone()
    lane_state = conn.execute(
        """
        SELECT paused, tasks_completed, tasks_failed
        FROM historical_backfill_lane_state WHERE lane=?
        """,
        (lane,),
    ).fetchone()
    if (
        not state
        or bool(state["paused"])
        or not lane_state
        or bool(lane_state["paused"])
    ):
        return {"status": "PAUSED"}
    _recover_stale_processing(conn)
    schedule_state = state if lane == PREDICTION_LANE else lane_state
    preferred_type = WORK_SCHEDULE[
        (
            int(schedule_state["tasks_completed"])
            + int(schedule_state["tasks_failed"])
        )
        % len(WORK_SCHEDULE)
    ]
    item = conn.execute(
        """
        SELECT * FROM historical_backfill_queue
        WHERE status='PENDING'
          AND collection_lane=?
          AND (not_before IS NULL OR not_before <= ?)
        ORDER BY
          CASE WHEN priority >= ? THEN 0 ELSE 1 END,
          CASE WHEN priority >= ? THEN priority ELSE NULL END DESC,
          CASE WHEN item_type=? THEN 0 ELSE 1 END,
          attempts ASC,
          CASE WHEN item_type IN ('GAME', 'EVENT') THEN event_id END DESC,
          priority DESC,
          queue_id
        LIMIT 1
        """,
        (
            lane,
            utc_now(),
            PRIORITY_THRESHOLD,
            PRIORITY_THRESHOLD,
            preferred_type,
        ),
    ).fetchone()
    if item is None:
        if lane == PREDICTION_LANE:
            seed_known_players(conn)
        elif lane == CONTACT_LANE:
            seed_contact_backfill(conn)
            from director_directory import refresh_director_index
            refresh_director_index(conn, limit=250)
        return {"status": "IDLE"}
    item = dict(item)
    now = utc_now()
    conn.execute(
        """
        UPDATE historical_backfill_queue
        SET status='PROCESSING', attempts=attempts+1, updated_at=?
        WHERE queue_id=?
        """,
        (now, item["queue_id"]),
    )
    conn.execute(
        """
        UPDATE historical_backfill_state
        SET current_item_type=?, current_item_key=?,
            last_activity_at=?, updated_at=?
        WHERE state_id=1
        """,
        (item["item_type"], item["item_key"], now, now),
    )
    conn.execute(
        """
        UPDATE historical_backfill_lane_state
        SET current_item_type=?, current_item_key=?,
            last_activity_at=?, updated_at=?
        WHERE lane=?
        """,
        (item["item_type"], item["item_key"], now, now, lane),
    )
    conn.commit()
    try:
        result = _process_item(conn, item)
        _finish_item(conn, item, result)
        return {
            "status": "COMPLETE",
            "queuePriority": int(item.get("priority") or 0),
            **result,
        }
    except Exception as exc:
        _fail_item(conn, item, exc)
        return {
            "status": "FAILED",
            "queuePriority": int(item.get("priority") or 0),
            "networkRequests": 1,
            "error": str(exc),
        }


def _process_item(
    conn: sqlite3.Connection,
    item: dict[str, Any],
) -> dict[str, Any]:
    if item["item_type"] == "CONTACT_EVENT":
        from player_contact_directory import refresh_player_contact_index
        from director_directory import refresh_director_index

        event_id = int(item["event_id"])
        before = int(conn.execute("SELECT COUNT(*) FROM player_contacts").fetchone()[0])
        fetch_swap_standings(conn, event_id)
        fetch_swap_up_next(conn, event_id)
        refresh = refresh_player_contact_index(conn, DATA_DIR)
        director_refresh = refresh_director_index(conn, limit=5)
        after = int(conn.execute("SELECT COUNT(*) FROM player_contacts").fetchone()[0])
        return {
            **_empty_result(),
            "contactsIndexed": max(0, after - before),
            "contactRecordsSeen": int(refresh.get("contactRecordsSeen") or 0),
            "directorEventsIndexed": int(director_refresh.get("indexed") or 0),
            "networkRequests": 2,
        }
    if item["item_type"] == "PLAYER":
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        events, metadata = fetch_player_events(
            conn,
            int(item["player_id"]),
            int(item["bucket_id"] or DEFAULT_BUCKET_ID),
            statuses=("COMPLETED",),
            include_metadata=True,
        )
        for event in events:
            _enqueue_event(
                conn,
                int(event["eventId"]),
                priority=80,
                source=f"player:{item['player_id']}",
                lane=item.get("collection_lane") or PREDICTION_LANE,
            )
            _enqueue_contact_event(
                conn,
                int(event["eventId"]),
                priority=25,
                source=f"player:{item['player_id']}",
            )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {
            "eventsDiscovered": max(0, after - before),
            "playersDiscovered": 0,
            "gamesDownloaded": 0,
            "roundsAdded": 0,
            "authBlocked": 0,
            "networkRequests": sum(
                1 for meta in metadata if meta.get("source") != "cache"
            ),
        }
    if item["item_type"] == "EVENT":
        before_players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        bracket, meta = fetch_bracket(
            conn,
            int(item["event_id"]),
            preserve_contact_data=True,
        )
        _enqueue_contact_event(
            conn,
            int(item["event_id"]),
            priority=800,
            source=f"event-roster:{item['event_id']}",
        )
        classification = (
            fetch_event_player_classifications(
                conn,
                int(item["event_id"]),
            )
            if int(item.get("priority") or 0) >= PRIORITY_THRESHOLD
            else {
                "classified": 0,
                "proPlayers": 0,
                "proPlayerIds": [],
                "networkRequests": 0,
            }
        )
        event = {
            "eventId": int(item["event_id"]),
        }
        targets = index_relevant_matches(
            conn, event, bracket, set(), full_event=True
        )
        child_game_priority = max(60, int(item.get("priority") or 0) - 1)
        for target in targets:
            _enqueue_game(
                conn,
                target["eventId"],
                target["matchId"],
                target["gameId"],
                priority=child_game_priority,
                source=f"event:{item['event_id']}",
                lane=item.get("collection_lane") or PREDICTION_LANE,
            )
        player_rows = conn.execute(
            """
            SELECT DISTINCT tm.player_id
            FROM team_members tm
            WHERE tm.event_id=?
            """,
            (item["event_id"],),
        ).fetchall()
        for row in player_rows:
            _enqueue_player(
                conn,
                int(row["player_id"]),
                DEFAULT_BUCKET_ID,
                priority=40,
                source=f"event:{item['event_id']}",
                lane=item.get("collection_lane") or PREDICTION_LANE,
            )
        for player_id in classification["proPlayerIds"]:
            _enqueue_player(
                conn,
                int(player_id),
                DEFAULT_BUCKET_ID,
                priority=1100,
                source=f"pro-roster:event:{item['event_id']}",
                lane=CLASSIFIED_LANE,
            )
        conn.commit()
        after_players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        return {
            "eventsDiscovered": 0,
            "playersDiscovered": max(0, after_players - before_players),
            "gamesDownloaded": 0,
            "roundsAdded": 0,
            "authBlocked": 0,
            "classifiedPlayers": classification["classified"],
            "proPlayers": classification["proPlayers"],
            "networkRequests": (
                (0 if meta.get("source") == "cache" else 1)
                + int(classification["networkRequests"])
            ),
        }
    if item["item_type"] == "GAME":
        existing = conn.execute(
            """
            SELECT completed, stats_downloaded FROM games
            WHERE event_id=? AND match_id=? AND game_id=?
            """,
            (item["event_id"], item["match_id"], item["game_id"]),
        ).fetchone()
        if existing and existing["completed"] and existing["stats_downloaded"]:
            return _empty_result()
        stats, meta = fetch_match_stats(
            conn,
            int(item["event_id"]),
            str(item["match_id"]),
            int(item["game_id"]),
        )
        if meta.get("authRequired"):
            return {
                **_empty_result(),
                "authBlocked": 1,
                "networkRequests": 0 if meta.get("source") == "cache" else 1,
            }
        if not stats:
            raise RuntimeError(meta.get("error") or "Match statistics unavailable")
        before_rounds = conn.execute(
            "SELECT COUNT(*) FROM player_rounds"
        ).fetchone()[0]
        normalize_match_stats_to_rounds(
            conn,
            int(item["event_id"]),
            str(item["match_id"]),
            int(item["game_id"]),
            stats,
        )
        after_rounds = conn.execute(
            "SELECT COUNT(*) FROM player_rounds"
        ).fetchone()[0]
        for row in conn.execute(
            """
            SELECT DISTINCT player_id FROM player_rounds
            WHERE event_id=? AND match_id=? AND game_id=?
            """,
            (item["event_id"], item["match_id"], item["game_id"]),
        ).fetchall():
            _enqueue_player(
                conn,
                int(row["player_id"]),
                DEFAULT_BUCKET_ID,
                priority=30,
                source=f"game:{item['item_key']}",
                lane=item.get("collection_lane") or PREDICTION_LANE,
            )
        conn.commit()
        return {
            "eventsDiscovered": 0,
            "playersDiscovered": 0,
            "gamesDownloaded": 1,
            "roundsAdded": max(0, after_rounds - before_rounds),
            "authBlocked": 0,
            "networkRequests": 0 if meta.get("source") == "cache" else 1,
        }
    raise ValueError(f"Unknown backfill item type: {item['item_type']}")


def _enqueue_player(
    conn: sqlite3.Connection,
    player_id: int,
    bucket_id: int,
    *,
    priority: int,
    source: str,
    lane: str = PREDICTION_LANE,
) -> int:
    return _enqueue(
        conn,
        "PLAYER",
        f"{player_id}:{bucket_id}",
        priority=priority,
        source=source,
        player_id=player_id,
        bucket_id=bucket_id,
        lane=lane,
    )


def _enqueue_event(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    priority: int,
    source: str,
    lane: str = PREDICTION_LANE,
) -> int:
    return _enqueue(
        conn, "EVENT", str(event_id), priority=priority, source=source,
        event_id=event_id, lane=lane,
    )


def _enqueue_contact_event(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    priority: int,
    source: str,
) -> int:
    return _enqueue(
        conn, "CONTACT_EVENT", str(event_id), priority=priority, source=source,
        event_id=event_id, lane=CONTACT_LANE,
    )


def seed_contact_backfill(conn: sqlite3.Connection, limit: int = 250) -> int:
    """Queue historical events where known participants still lack contacts."""
    initialize_schema(conn)
    from player_contact_directory import initialize_player_contact_schema

    initialize_player_contact_schema(conn)
    rows = conn.execute(
        """
        WITH event_players AS (
            SELECT event_id, player_id FROM team_members
            UNION SELECT event_id, player_id FROM player_rounds
            UNION SELECT event_id, player_id FROM event_results
            UNION SELECT event_id, player_id FROM swap_standings
            UNION SELECT event_id, player_id FROM swap_up_next
        )
        SELECT ep.event_id,
               SUM(CASE WHEN pc.player_id IS NULL THEN 1 ELSE 0 END) AS missing,
               MAX(COALESCE(e.event_date,'')) AS event_date,
               MAX(COALESCE(e.blind_draw,0)) AS blind_draw
        FROM event_players ep
        LEFT JOIN player_contacts pc ON pc.player_id=ep.player_id
        LEFT JOIN events e ON e.event_id=ep.event_id
        LEFT JOIN historical_backfill_queue q
          ON q.item_type='CONTACT_EVENT' AND q.item_key=CAST(ep.event_id AS TEXT)
        WHERE pc.player_id IS NULL AND q.queue_id IS NULL
        GROUP BY ep.event_id
        HAVING missing > 0
        ORDER BY blind_draw DESC, event_date DESC, missing DESC
        LIMIT ?
        """,
        (max(1, min(int(limit), 1000)),),
    ).fetchall()
    queued = 0
    for row in rows:
        queued += _enqueue_contact_event(
            conn,
            int(row["event_id"]),
            priority=300 + min(int(row["missing"] or 0), 100),
            source="historical-contact-gap",
        )
    conn.commit()
    return queued


def _enqueue_game(
    conn: sqlite3.Connection,
    event_id: int,
    match_id: str,
    game_id: int,
    *,
    priority: int,
    source: str,
    lane: str = PREDICTION_LANE,
) -> int:
    return _enqueue(
        conn,
        "GAME",
        f"{event_id}:{match_id}:{game_id}",
        priority=priority,
        source=source,
        event_id=event_id,
        match_id=str(match_id),
        game_id=game_id,
        lane=lane,
    )


def _enqueue(
    conn: sqlite3.Connection,
    item_type: str,
    item_key: str,
    *,
    priority: int,
    source: str,
    player_id: int | None = None,
    event_id: int | None = None,
    match_id: str | None = None,
    game_id: int | None = None,
    bucket_id: int | None = None,
    lane: str = PREDICTION_LANE,
) -> int:
    lane = str(lane or PREDICTION_LANE).strip().upper()
    if lane not in COLLECTION_LANES:
        raise ValueError("Unknown collection lane")
    existed = conn.execute(
        """
        SELECT 1 FROM historical_backfill_queue
        WHERE item_type=? AND item_key=?
        """,
        (item_type, item_key),
    ).fetchone() is not None
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO historical_backfill_queue(
            item_type, item_key, player_id, event_id, match_id, game_id,
            bucket_id, priority, status, discovered_from, created_at, updated_at,
            collection_lane
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
        ON CONFLICT(item_type, item_key) DO UPDATE SET
            priority=MAX(historical_backfill_queue.priority, excluded.priority),
            collection_lane=CASE
                WHEN excluded.collection_lane='ACL_CLASSIFIED'
                THEN excluded.collection_lane
                ELSE historical_backfill_queue.collection_lane
            END,
            status=CASE
                WHEN historical_backfill_queue.status='FAILED'
                 AND excluded.priority >= 900 THEN 'PENDING'
                ELSE historical_backfill_queue.status
            END,
            not_before=CASE
                WHEN historical_backfill_queue.status='FAILED'
                 AND excluded.priority >= 900 THEN NULL
                ELSE historical_backfill_queue.not_before
            END,
            updated_at=excluded.updated_at
        """,
        (
            item_type, item_key, player_id, event_id, match_id, game_id,
            bucket_id, priority, source, utc_now(), utc_now(), lane,
        ),
    )
    return int(not existed and cursor.rowcount > 0)


def _finish_item(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    result: dict[str, Any],
) -> None:
    now = utc_now()
    productive = any(
        int(result.get(key) or 0) > 0
        for key in (
            "eventsDiscovered", "playersDiscovered", "gamesDownloaded",
            "roundsAdded", "contactsIndexed", "directorEventsIndexed",
        )
    )
    conn.execute(
        """
        UPDATE historical_backfill_queue
        SET status='COMPLETE', completed_at=?, updated_at=?, last_error=NULL
        WHERE queue_id=?
        """,
        (now, now, item["queue_id"]),
    )
    conn.execute(
        """
        UPDATE historical_backfill_state
        SET current_item_type=NULL, current_item_key=NULL,
            tasks_completed=tasks_completed+1,
            events_discovered=events_discovered+?,
            players_discovered=players_discovered+?,
            games_downloaded=games_downloaded+?,
            rounds_added=rounds_added+?,
            auth_blocked=auth_blocked+?,
            last_success_at=?, last_activity_at=?, updated_at=?,
            last_error=NULL
        WHERE state_id=1
        """,
        (
            result.get("eventsDiscovered", 0),
            result.get("playersDiscovered", 0),
            result.get("gamesDownloaded", 0),
            result.get("roundsAdded", 0),
            result.get("authBlocked", 0),
            now, now, now,
        ),
    )
    conn.execute(
        """
        UPDATE historical_backfill_lane_state
        SET current_item_type=NULL, current_item_key=NULL,
            tasks_completed=tasks_completed+1,
            last_success_at=?, last_activity_at=?, updated_at=?,
            last_error=NULL
        WHERE lane=?
        """,
        (
            now,
            now,
            now,
            item.get("collection_lane") or PREDICTION_LANE,
        ),
    )
    conn.execute(
        """
        INSERT INTO historical_backfill_activity(
            queue_id, collection_lane, item_type, item_key, outcome,
            productive, terminal, events_discovered, players_discovered,
            games_downloaded, rounds_added, occurred_at
        ) VALUES (?, ?, ?, ?, 'COMPLETE', ?, 1, ?, ?, ?, ?, ?)
        """,
        (
            item["queue_id"],
            item.get("collection_lane") or PREDICTION_LANE,
            item["item_type"], item["item_key"], 1 if productive else 0,
            int(result.get("eventsDiscovered") or 0),
            int(result.get("playersDiscovered") or 0),
            int(result.get("gamesDownloaded") or 0),
            int(result.get("roundsAdded") or 0), now,
        ),
    )
    conn.commit()


def _fail_item(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    exc: Exception,
) -> None:
    attempts = int(item["attempts"] or 0) + 1
    status_code = _http_status_code(exc)
    permanent_http_failure = status_code in {400, 401, 403, 404, 409, 410, 422}
    server_retry_limit = 2 if status_code and status_code >= 500 else MAX_ATTEMPTS
    terminal = permanent_http_failure or attempts >= server_retry_limit
    priority_item = int(item.get("priority") or 0) >= PRIORITY_THRESHOLD
    delay_minutes = 0 if priority_item else min(2 ** attempts, 24 * 60)
    not_before = (
        None
        if priority_item
        else (datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)).isoformat()
    )
    message = str(exc)[:1000]
    now = utc_now()
    conn.execute(
        """
        UPDATE historical_backfill_queue
        SET status=?, not_before=?, last_error=?, updated_at=?
        WHERE queue_id=?
        """,
        (
            "FAILED" if terminal else "PENDING",
            None if terminal else not_before,
            message,
            now,
            item["queue_id"],
        ),
    )
    conn.execute(
        """
        UPDATE historical_backfill_state
        SET current_item_type=NULL, current_item_key=NULL,
            tasks_failed=tasks_failed+1, last_error_at=?,
            last_activity_at=?, updated_at=?, last_error=?
        WHERE state_id=1
        """,
        (now, now, now, message),
    )
    conn.execute(
        """
        UPDATE historical_backfill_lane_state
        SET current_item_type=NULL, current_item_key=NULL,
            tasks_failed=tasks_failed+1, last_error_at=?,
            last_activity_at=?, updated_at=?, last_error=?
        WHERE lane=?
        """,
        (
            now,
            now,
            now,
            message,
            item.get("collection_lane") or PREDICTION_LANE,
        ),
    )
    conn.execute(
        """
        INSERT INTO historical_backfill_activity(
            queue_id, collection_lane, item_type, item_key, outcome,
            productive, terminal, error, occurred_at
        ) VALUES (?, ?, ?, ?, 'FAILED_ATTEMPT', 0, ?, ?, ?)
        """,
        (
            item["queue_id"],
            item.get("collection_lane") or PREDICTION_LANE,
            item["item_type"], item["item_key"], 1 if terminal else 0,
            message, now,
        ),
    )
    conn.commit()


def _http_status_code(exc: Exception) -> int | None:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return int(exc.response.status_code)
    return None


def _throughput_since(
    conn: sqlite3.Connection,
    cutoff: datetime,
) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS attempts,
          SUM(CASE WHEN outcome='COMPLETE' THEN 1 ELSE 0 END) AS completed,
          SUM(CASE WHEN productive=1 THEN 1 ELSE 0 END) AS productive,
          SUM(CASE WHEN outcome='FAILED_ATTEMPT' THEN 1 ELSE 0 END) AS failed_attempts,
          SUM(CASE WHEN terminal=1 AND outcome='FAILED_ATTEMPT' THEN 1 ELSE 0 END) AS terminal_failures,
          SUM(events_discovered) AS events_discovered,
          SUM(players_discovered) AS players_discovered,
          SUM(games_downloaded) AS games_downloaded,
          SUM(rounds_added) AS rounds_added
        FROM historical_backfill_activity
        WHERE occurred_at >= ?
        """,
        (cutoff.isoformat(),),
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def _recover_stale_processing(conn: sqlite3.Connection) -> None:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    ).isoformat()
    conn.execute(
        """
        UPDATE historical_backfill_queue
        SET status='PENDING', updated_at=?
        WHERE status='PROCESSING' AND updated_at < ?
        """,
        (utc_now(), cutoff),
    )
    conn.commit()


def _ledger_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "events": int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
        "players": int(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]),
        "games": int(conn.execute(
            "SELECT COUNT(*) FROM games WHERE completed=1 AND stats_downloaded=1"
        ).fetchone()[0]),
        "rounds": int(conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0]),
        "venues": int(conn.execute(
            """
            SELECT COUNT(DISTINCT COALESCE(location_id, location_name))
            FROM events
            WHERE COALESCE(location_id, location_name) IS NOT NULL
            """
        ).fetchone()[0]),
    }


def _geography_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT location_state,
               UPPER(TRIM(location_country)) AS location_country,
               COUNT(*) AS events,
               COUNT(DISTINCT COALESCE(location_id, location_name)) AS venues
        FROM events
        WHERE COALESCE(location_id, location_name) IS NOT NULL
        GROUP BY location_state, UPPER(TRIM(location_country))
        """
    ).fetchall()
    regions: dict[tuple[str, str], dict[str, Any]] = {}
    countries: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_region = str(row["location_state"] or "").strip()
        if not raw_region or raw_region.lower() in {"null", "undefined", "n/a"}:
            raw_region = "Unknown region"
        region_key = raw_region.upper()
        country = str(row["location_country"] or "").strip().upper()
        if not country:
            if region_key in US_REGIONS:
                country = "US"
            elif region_key in CANADIAN_REGIONS:
                country = "CA"
            else:
                country = "UNKNOWN"
        key = (country, region_key)
        entry = regions.setdefault(
            key,
            {
                "countryCode": country,
                "region": raw_region,
                "events": 0,
                "venues": 0,
            },
        )
        entry["events"] += int(row["events"] or 0)
        entry["venues"] += int(row["venues"] or 0)
        country_entry = countries.setdefault(
            country,
            {"countryCode": country, "events": 0, "venues": 0},
        )
        country_entry["events"] += int(row["events"] or 0)
        country_entry["venues"] += int(row["venues"] or 0)
    return {
        "countries": sorted(
            countries.values(),
            key=lambda item: (-item["venues"], item["countryCode"]),
        ),
        "regions": sorted(
            regions.values(),
            key=lambda item: (-item["venues"], item["countryCode"], item["region"]),
        ),
        "countryCount": len([key for key in countries if key != "UNKNOWN"]),
        "regionCount": len(regions),
    }


def venue_export_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return one Google My Maps-ready row per known venue coordinate."""
    rows = conn.execute(
        """
        WITH game_totals AS (
            SELECT event_id, COUNT(*) AS complete_games
            FROM games
            WHERE completed=1 AND stats_downloaded=1
            GROUP BY event_id
        ),
        round_totals AS (
            SELECT event_id, COUNT(*) AS player_rounds
            FROM player_rounds
            GROUP BY event_id
        ),
        coordinate_events AS (
            SELECT
                e.event_id,
                COALESCE(e.location_name, d.location_name) AS location_name,
                COALESCE(e.location_city, d.location_city) AS location_city,
                COALESCE(e.location_state, d.location_state) AS location_state,
                COALESCE(e.location_country, d.location_country) AS location_country,
                COALESCE(e.location_lat, d.location_lat) AS location_lat,
                COALESCE(e.location_lng, d.location_lng) AS location_lng,
                COALESCE(e.event_date, d.event_date) AS event_date
            FROM events e
            LEFT JOIN discovered_events d ON d.event_id=e.event_id
            UNION ALL
            SELECT
                d.event_id, d.location_name, d.location_city, d.location_state,
                d.location_country, d.location_lat, d.location_lng, d.event_date
            FROM discovered_events d
            WHERE NOT EXISTS (
                SELECT 1 FROM events e WHERE e.event_id=d.event_id
            )
        )
        SELECT
            COALESCE(NULLIF(TRIM(d.location_name), ''), 'Unknown venue') AS venue,
            ROUND(d.location_lat, 6) AS latitude,
            ROUND(d.location_lng, 6) AS longitude,
            COALESCE(d.location_city, '') AS city,
            COALESCE(d.location_state, '') AS state_province,
            COALESCE(NULLIF(UPPER(TRIM(d.location_country)), ''), 'UNKNOWN') AS country,
            COUNT(DISTINCT d.event_id) AS event_count,
            MIN(d.event_date) AS first_event_date,
            MAX(d.event_date) AS latest_event_date,
            SUM(COALESCE(g.complete_games, 0)) AS complete_games,
            SUM(COALESCE(r.player_rounds, 0)) AS player_rounds,
            GROUP_CONCAT(DISTINCT d.event_id) AS event_ids
        FROM coordinate_events d
        LEFT JOIN game_totals g ON g.event_id=d.event_id
        LEFT JOIN round_totals r ON r.event_id=d.event_id
        WHERE d.location_lat IS NOT NULL
          AND d.location_lng IS NOT NULL
          AND d.location_lat BETWEEN -90 AND 90
          AND d.location_lng BETWEEN -180 AND 180
          AND NOT (d.location_lat=0 AND d.location_lng=0)
        GROUP BY
            COALESCE(NULLIF(TRIM(d.location_name), ''), 'Unknown venue'),
            ROUND(d.location_lat, 6),
            ROUND(d.location_lng, 6),
            COALESCE(d.location_city, ''),
            COALESCE(d.location_state, ''),
            COALESCE(NULLIF(UPPER(TRIM(d.location_country)), ''), 'UNKNOWN')
        ORDER BY country, state_province, city, venue
        """
    ).fetchall()
    return [
        {
            "Venue": row["venue"],
            "Latitude": row["latitude"],
            "Longitude": row["longitude"],
            "City": row["city"],
            "State_Province": row["state_province"],
            "Country": row["country"],
            "Event_Count": int(row["event_count"] or 0),
            "First_Event_Date": row["first_event_date"] or "",
            "Latest_Event_Date": row["latest_event_date"] or "",
            "Complete_Games": int(row["complete_games"] or 0),
            "Player_Rounds": int(row["player_rounds"] or 0),
            "Event_IDs": row["event_ids"] or "",
        }
        for row in rows
    ]


def _empty_result() -> dict[str, int]:
    return {
        "eventsDiscovered": 0,
        "playersDiscovered": 0,
        "gamesDownloaded": 0,
        "roundsAdded": 0,
        "authBlocked": 0,
        "networkRequests": 0,
    }
