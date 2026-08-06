from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if not text or text.lower() in {"null", "none", "undefined", "n/a", "-"} else text


def initialize_director_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS directors (
            director_key TEXT PRIMARY KEY,
            acl_player_id INTEGER,
            first_name TEXT,
            last_name TEXT,
            display_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS director_events (
            event_id INTEGER PRIMARY KEY,
            director_key TEXT NOT NULL,
            event_name TEXT,
            event_date TEXT,
            event_time TEXT,
            event_status TEXT,
            venue_key TEXT NOT NULL,
            venue_id TEXT,
            venue_name TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            country TEXT,
            latitude REAL,
            longitude REAL,
            player_count INTEGER,
            team_count INTEGER,
            source_payload_id INTEGER,
            observed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(director_key) REFERENCES directors(director_key)
        );
        CREATE TABLE IF NOT EXISTS director_source_payloads (
            source_payload_id INTEGER PRIMARY KEY,
            indexed INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            processed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_director_events_director ON director_events(director_key,event_date);
        CREATE INDEX IF NOT EXISTS idx_director_events_venue ON director_events(venue_key,event_date);
        CREATE INDEX IF NOT EXISTS idx_director_events_location ON director_events(state,city,event_date);
        """
    )
    conn.commit()


def index_director_event_payload(
    conn: sqlite3.Connection,
    payload: Any,
    *,
    source_payload_id: int | None = None,
    fallback_event_id: int | None = None,
) -> dict[str, Any]:
    initialize_director_schema(conn)
    if not isinstance(payload, dict):
        return {"indexed": False, "reason": "INVALID_PAYLOAD"}
    info = payload.get("eventInfo") or payload.get("data") or payload
    if isinstance(info, list):
        info = info[0] if info else {}
    if not isinstance(info, dict):
        return {"indexed": False, "reason": "EVENT_INFO_MISSING"}

    event_id = info.get("eventID") or info.get("leagueID") or fallback_event_id
    director_id = info.get("eventAdminID") or info.get("adminID") or info.get("fldPlayerID")
    first = _clean(info.get("adminFirstName") or info.get("playerFirstName"))
    last = _clean(info.get("adminLastName") or info.get("playerLastName"))
    email = _clean(info.get("adminEmail") or info.get("playerEmail"))
    phone = _clean(info.get("adminPhone") or info.get("playerPhoneNo") or info.get("playerPhone"))
    if event_id in (None, "") or not (director_id or email or first or last):
        return {"indexed": False, "reason": "DIRECTOR_NOT_IDENTIFIED"}
    display = " ".join(value for value in (first, last) if value) or email or f"Director {director_id}"
    director_key = f"acl:{int(director_id)}" if director_id not in (None, "") else f"email:{email.lower()}"

    venue_id = _clean(info.get("leagueLocationID"))
    venue_name = _clean(info.get("leagueLocationName") or info.get("locationName")) or "Unknown venue"
    address = _clean(info.get("leagueAddress") or info.get("locationAddress"))
    city = _clean(info.get("locationCity"))
    state = _clean(info.get("locationState"))
    postal = _clean(info.get("locationZip"))
    country = _clean(info.get("countryCode"))
    venue_key = f"acl:{venue_id}" if venue_id else "text:" + "|".join(
        (venue_name, city or "", state or "", postal or "")
    ).lower()

    details = payload.get("bracketDetails") or []
    player_ids: set[int] = set()
    for row in details if isinstance(details, list) else []:
        if not isinstance(row, dict):
            continue
        for player in row.get("player_info") or []:
            try:
                player_id = int(player.get("playerid") or 0)
            except (TypeError, ValueError):
                player_id = 0
            name = str((player or {}).get("firstname") or "") + " " + str((player or {}).get("lastname") or "")
            if player_id > 0 and "bye user" not in name.lower():
                player_ids.add(player_id)
    team_count = int(info.get("teamCount") or 0)
    match_type = str(info.get("matchType") or info.get("matchtype") or "").upper()
    estimated_players = team_count * (1 if match_type == "S" else 2 if match_type == "D" else 1)
    player_count = len(player_ids) or estimated_players or None
    now = utc_now()
    conn.execute(
        """
        INSERT INTO directors(director_key,acl_player_id,first_name,last_name,display_name,email,phone,updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(director_key) DO UPDATE SET
          first_name=COALESCE(excluded.first_name,directors.first_name),
          last_name=COALESCE(excluded.last_name,directors.last_name),
          display_name=excluded.display_name,
          email=COALESCE(excluded.email,directors.email),
          phone=COALESCE(excluded.phone,directors.phone),updated_at=excluded.updated_at
        """,
        (director_key, int(director_id) if director_id not in (None, "") else None, first, last, display, email, phone, now),
    )
    conn.execute(
        """
        INSERT INTO director_events(
          event_id,director_key,event_name,event_date,event_time,event_status,venue_key,venue_id,
          venue_name,address,city,state,postal_code,country,latitude,longitude,player_count,
          team_count,source_payload_id,observed_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(event_id) DO UPDATE SET
          director_key=excluded.director_key,event_name=excluded.event_name,event_date=excluded.event_date,
          event_time=excluded.event_time,event_status=excluded.event_status,venue_key=excluded.venue_key,
          venue_id=excluded.venue_id,venue_name=excluded.venue_name,address=excluded.address,
          city=excluded.city,state=excluded.state,postal_code=excluded.postal_code,country=excluded.country,
          latitude=excluded.latitude,longitude=excluded.longitude,
          player_count=COALESCE(excluded.player_count,director_events.player_count),
          team_count=COALESCE(excluded.team_count,director_events.team_count),
          source_payload_id=COALESCE(excluded.source_payload_id,director_events.source_payload_id),
          observed_at=excluded.observed_at,updated_at=excluded.updated_at
        """,
        (
            int(event_id), director_key, _clean(info.get("eventName") or info.get("leagueName") or info.get("leaguename")),
            _clean(info.get("startdate") or info.get("leagueStartDate") or info.get("leaguestartdate")),
            _clean(info.get("starttime") or info.get("leagueTime")), _clean(info.get("leagueStatus")),
            venue_key, venue_id, venue_name, address, city, state, postal, country,
            info.get("locationLat"), info.get("locationLng"), player_count, team_count or None,
            source_payload_id, now, now,
        ),
    )
    conn.commit()
    return {"indexed": True, "eventId": int(event_id), "directorKey": director_key, "playerCount": player_count}


def refresh_director_index(conn: sqlite3.Connection, *, limit: int = 1000) -> dict[str, Any]:
    initialize_director_schema(conn)
    from payload_archive import load_source_payload

    rows = conn.execute(
        """
        SELECT s.source_payload_id,s.entity_key
        FROM source_payloads s
        LEFT JOIN director_source_payloads dsp ON dsp.source_payload_id=s.source_payload_id
        WHERE s.source_endpoint='bracket-data' AND dsp.source_payload_id IS NULL
        ORDER BY s.source_payload_id DESC LIMIT ?
        """,
        (max(1, min(int(limit), 5000)),),
    ).fetchall()
    indexed = 0
    skipped = 0
    for row in rows:
        try:
            fallback = int(str(row["entity_key"]).split(":")[-1])
            result = index_director_event_payload(
                conn, load_source_payload(conn, row["source_payload_id"]),
                source_payload_id=row["source_payload_id"], fallback_event_id=fallback,
            )
            indexed += int(bool(result.get("indexed")))
            skipped += int(not result.get("indexed"))
            conn.execute(
                "INSERT OR REPLACE INTO director_source_payloads(source_payload_id,indexed,reason,processed_at) VALUES (?,?,?,?)",
                (row["source_payload_id"], int(bool(result.get("indexed"))), result.get("reason"), utc_now()),
            )
            conn.commit()
        except Exception as exc:
            skipped += 1
            conn.execute(
                "INSERT OR REPLACE INTO director_source_payloads(source_payload_id,indexed,reason,processed_at) VALUES (?,?,?,?)",
                (row["source_payload_id"], 0, str(exc)[:500], utc_now()),
            )
            conn.commit()
    remaining = int(conn.execute(
        "SELECT COUNT(*) FROM source_payloads s LEFT JOIN director_source_payloads dsp ON dsp.source_payload_id=s.source_payload_id WHERE s.source_endpoint='bracket-data' AND dsp.source_payload_id IS NULL"
    ).fetchone()[0])
    return {"processed": len(rows), "indexed": indexed, "skipped": skipped, "remaining": remaining}


def director_directory(
    conn: sqlite3.Connection, *, view: str = "DIRECTORS", search: str = "",
    state: str = "ALL", date_from: str = "", date_to: str = "", limit: int = 100,
) -> dict[str, Any]:
    initialize_director_schema(conn)
    clauses = ["1=1"]
    params: list[Any] = []
    if search.strip():
        term = f"%{search.strip()}%"
        clauses.append("(d.display_name LIKE ? OR d.email LIKE ? OR de.venue_name LIKE ? OR de.event_name LIKE ? OR de.city LIKE ?)")
        params.extend([term] * 5)
    if state != "ALL":
        clauses.append("UPPER(COALESCE(de.state,''))=?")
        params.append(state.upper())
    if date_from:
        clauses.append("de.event_date>=?"); params.append(date_from)
    if date_to:
        clauses.append("de.event_date<=?"); params.append(date_to)
    where = " AND ".join(clauses)
    max_rows = max(1, min(int(limit), 50000))

    if view == "VENUES":
        rows = conn.execute(f"""
          SELECT de.venue_key,de.venue_id,de.venue_name,de.address,de.city,de.state,de.postal_code,de.country,
                 COUNT(DISTINCT de.event_id) event_count,COUNT(DISTINCT de.director_key) director_count,
                 ROUND(AVG(de.player_count),1) average_players,MAX(de.event_date) latest_event_date,
                 GROUP_CONCAT(DISTINCT d.display_name) director_names
          FROM director_events de JOIN directors d ON d.director_key=de.director_key
          WHERE {where} GROUP BY de.venue_key ORDER BY event_count DESC,de.venue_name COLLATE NOCASE LIMIT ?
        """, (*params, max_rows)).fetchall()
    elif view == "EVENTS":
        rows = conn.execute(f"""
          SELECT de.*,d.display_name director_name,d.email director_email,d.phone director_phone
          FROM director_events de JOIN directors d ON d.director_key=de.director_key
          WHERE {where} ORDER BY de.event_date DESC,de.event_time DESC LIMIT ?
        """, (*params, max_rows)).fetchall()
    else:
        rows = conn.execute(f"""
          SELECT d.director_key,d.acl_player_id,d.display_name,d.email,d.phone,
                 COUNT(DISTINCT de.event_id) event_count,COUNT(DISTINCT de.venue_key) venue_count,
                 ROUND(AVG(de.player_count),1) average_players,COALESCE(SUM(de.player_count),0) total_players,
                 MAX(de.event_date) latest_event_date,GROUP_CONCAT(DISTINCT de.venue_name) venue_names
          FROM directors d JOIN director_events de ON de.director_key=d.director_key
          WHERE {where} GROUP BY d.director_key ORDER BY event_count DESC,d.display_name COLLATE NOCASE LIMIT ?
        """, (*params, max_rows)).fetchall()
    states = [r[0] for r in conn.execute("SELECT DISTINCT state FROM director_events WHERE NULLIF(TRIM(state),'') IS NOT NULL ORDER BY state").fetchall()]
    summary = dict(conn.execute("""
      SELECT COUNT(DISTINCT director_key) directors,COUNT(DISTINCT venue_key) venues,COUNT(*) events,
             ROUND(AVG(player_count),1) average_players,COALESCE(SUM(player_count),0) total_players
      FROM director_events
    """).fetchone())
    return {"view": view, "rows": [dict(row) for row in rows], "states": states, "summary": summary, "generatedAt": utc_now()}
