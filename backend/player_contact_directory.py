from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONTACT_SOURCE_DIRS = ("schedules", "swap_standings", "swap_up_next")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_player_contact_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS player_contacts (
            player_id INTEGER PRIMARY KEY,
            email TEXT,
            phone TEXT,
            source_endpoint TEXT NOT NULL,
            source_event_id TEXT,
            source_file TEXT NOT NULL,
            source_modified_at TEXT,
            observed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(player_id) REFERENCES players(player_id)
        );
        CREATE INDEX IF NOT EXISTS idx_player_contacts_email ON player_contacts(email);
        CREATE INDEX IF NOT EXISTS idx_player_contacts_phone ON player_contacts(phone);

        CREATE TABLE IF NOT EXISTS player_contact_source_files (
            source_file TEXT PRIMARY KEY,
            source_endpoint TEXT NOT NULL,
            modified_ns INTEGER NOT NULL,
            size_bytes INTEGER NOT NULL,
            processed_at TEXT NOT NULL,
            contacts_found INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "undefined", "n/a", "na", "-"}:
        return None
    return text


def _player_contact_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        player_id = value.get("playerID") or value.get("playerId") or value.get("playerid")
        email = _clean(value.get("playerEmail") or value.get("playeremail"))
        phone = _clean(
            value.get("playerPhoneNo")
            or value.get("playerPhone")
            or value.get("playerphone")
        )
        if player_id and (email or phone):
            try:
                parsed_id = int(player_id)
            except (TypeError, ValueError):
                parsed_id = 0
            if parsed_id > 0:
                yield {
                    "player_id": parsed_id,
                    "email": email,
                    "phone": phone,
                    "event_id": value.get("leagueID") or value.get("eventID"),
                }
        for child in value.values():
            yield from _player_contact_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _player_contact_records(child)


def refresh_player_contact_index(
    conn: sqlite3.Connection,
    raw_root: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    initialize_player_contact_schema(conn)
    root = Path(raw_root)
    processed_files = 0
    skipped_files = 0
    contact_records = 0
    changed_players: set[int] = set()
    errors: list[dict[str, str]] = []

    for source in CONTACT_SOURCE_DIRS:
        directory = root / source
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            try:
                stat = path.stat()
                relative = str(path.relative_to(root)).replace("\\", "/")
                previous = conn.execute(
                    "SELECT modified_ns,size_bytes FROM player_contact_source_files WHERE source_file=?",
                    (relative,),
                ).fetchone()
                if (
                    not force
                    and previous
                    and int(previous["modified_ns"]) == int(stat.st_mtime_ns)
                    and int(previous["size_bytes"]) == int(stat.st_size)
                ):
                    skipped_files += 1
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                records = list(_player_contact_records(payload))
                modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                now = utc_now()
                for record in records:
                    contact_records += 1
                    changed_players.add(record["player_id"])
                    conn.execute(
                        """
                        INSERT INTO player_contacts(
                            player_id,email,phone,source_endpoint,source_event_id,
                            source_file,source_modified_at,observed_at,updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(player_id) DO UPDATE SET
                            email=COALESCE(excluded.email,player_contacts.email),
                            phone=COALESCE(excluded.phone,player_contacts.phone),
                            source_endpoint=excluded.source_endpoint,
                            source_event_id=COALESCE(excluded.source_event_id,player_contacts.source_event_id),
                            source_file=excluded.source_file,
                            source_modified_at=excluded.source_modified_at,
                            observed_at=excluded.observed_at,
                            updated_at=excluded.updated_at
                        """,
                        (
                            record["player_id"], record["email"], record["phone"], source,
                            _clean(record.get("event_id")), relative, modified_at, modified_at, now,
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO player_contact_source_files(
                        source_file,source_endpoint,modified_ns,size_bytes,processed_at,contacts_found
                    ) VALUES (?,?,?,?,?,?)
                    ON CONFLICT(source_file) DO UPDATE SET
                        source_endpoint=excluded.source_endpoint,
                        modified_ns=excluded.modified_ns,
                        size_bytes=excluded.size_bytes,
                        processed_at=excluded.processed_at,
                        contacts_found=excluded.contacts_found
                    """,
                    (relative, source, stat.st_mtime_ns, stat.st_size, now, len(records)),
                )
                processed_files += 1
            except Exception as exc:
                errors.append({"file": str(path.name), "error": str(exc)})
                if len(errors) >= 20:
                    break
        conn.commit()

    indexed = int(conn.execute("SELECT COUNT(*) FROM player_contacts").fetchone()[0])
    return {
        "generatedAt": utc_now(),
        "processedFiles": processed_files,
        "skippedFiles": skipped_files,
        "contactRecordsSeen": contact_records,
        "changedPlayers": len(changed_players),
        "indexedPlayers": indexed,
        "errors": errors,
    }


def player_contact_directory(
    conn: sqlite3.Connection,
    *,
    search: str = "",
    classification: str = "ALL",
    membership: str = "ALL",
    contact: str = "ALL",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    initialize_player_contact_schema(conn)
    clauses = ["1=1"]
    params: list[Any] = []
    query = search.strip()
    if query:
        clauses.append("(p.display_name LIKE ? OR CAST(p.player_id AS TEXT) LIKE ?)")
        params.extend((f"%{query}%", f"%{query}%"))
    if classification == "PRO":
        clauses.append("COALESCE(p.is_pro,0)=1")
    elif classification == "NON_PRO":
        clauses.append("COALESCE(p.is_pro,0)=0")
    if membership == "UNKNOWN":
        clauses.append("NULLIF(TRIM(p.membership_name),'') IS NULL")
    elif membership != "ALL":
        clauses.append("UPPER(TRIM(COALESCE(p.membership_name,'')))=?")
        params.append(membership.upper())
    if contact == "EMAIL":
        clauses.append("NULLIF(TRIM(c.email),'') IS NOT NULL")
    elif contact == "PHONE":
        clauses.append("NULLIF(TRIM(c.phone),'') IS NOT NULL")
    elif contact == "BOTH":
        clauses.append("NULLIF(TRIM(c.email),'') IS NOT NULL AND NULLIF(TRIM(c.phone),'') IS NOT NULL")
    elif contact == "MISSING":
        clauses.append("NULLIF(TRIM(c.email),'') IS NULL AND NULLIF(TRIM(c.phone),'') IS NULL")

    where = " AND ".join(clauses)
    total = int(conn.execute(
        f"SELECT COUNT(*) FROM players p LEFT JOIN player_contacts c ON c.player_id=p.player_id WHERE {where}",
        params,
    ).fetchone()[0])
    rows = conn.execute(
        f"""
        SELECT p.player_id,p.display_name,p.first_name,p.last_name,p.city,p.state,
               p.profile_image,p.skill_level,p.is_pro,p.membership_name,p.membership_type,
               c.email,c.phone,c.source_endpoint,c.source_event_id,c.source_file,c.observed_at,
               s.snapshot_json
        FROM players p
        LEFT JOIN player_contacts c ON c.player_id=p.player_id
        LEFT JOIN player_analytics_snapshots s ON s.player_id=p.player_id
        WHERE {where}
        ORDER BY CASE WHEN c.email IS NOT NULL OR c.phone IS NOT NULL THEN 0 ELSE 1 END,
                 p.display_name COLLATE NOCASE,p.player_id
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    players = []
    for raw in rows:
        row = dict(raw)
        snapshot_raw = row.pop("snapshot_json", None)
        try:
            snapshot = json.loads(snapshot_raw) if snapshot_raw else {}
        except Exception:
            snapshot = {}
        players.append({
            "playerId": row["player_id"],
            "playerName": row["display_name"] or f"Player {row['player_id']}",
            "firstName": row["first_name"],
            "lastName": row["last_name"],
            "city": row["city"],
            "state": row["state"],
            "profileImage": row["profile_image"],
            "skillLevel": row["skill_level"],
            "isPro": bool(row["is_pro"]),
            "membershipName": row["membership_name"],
            "membershipType": row["membership_type"],
            "email": row["email"],
            "phone": row["phone"],
            "contactSource": row["source_endpoint"],
            "contactSourceEventId": row["source_event_id"],
            "contactObservedAt": row["observed_at"],
            "calculatedPpr": snapshot.get("calculatedPpr"),
            "currentFormRating": snapshot.get("currentFormRating"),
            "rounds": snapshot.get("rounds"),
            "sampleConfidence": snapshot.get("reliability"),
        })
    membership_options = [row[0] for row in conn.execute(
        "SELECT DISTINCT membership_name FROM players WHERE NULLIF(TRIM(membership_name),'') IS NOT NULL ORDER BY membership_name COLLATE NOCASE"
    ).fetchall()]
    coverage = dict(conn.execute(
        """
        SELECT COUNT(*) AS players,
               SUM(CASE WHEN NULLIF(TRIM(email),'') IS NOT NULL THEN 1 ELSE 0 END) AS with_email,
               SUM(CASE WHEN NULLIF(TRIM(phone),'') IS NOT NULL THEN 1 ELSE 0 END) AS with_phone,
               SUM(CASE WHEN NULLIF(TRIM(email),'') IS NOT NULL OR NULLIF(TRIM(phone),'') IS NOT NULL THEN 1 ELSE 0 END) AS with_contact
        FROM player_contacts
        """
    ).fetchone())
    return {
        "generatedAt": utc_now(),
        "total": total,
        "limit": limit,
        "offset": offset,
        "players": players,
        "membershipOptions": membership_options,
        "contactCoverage": coverage,
        "privacy": {
            "access": "PRIVATE_ADMIN",
            "publicProfileExposure": False,
            "shareImageExposure": False,
        },
    }
