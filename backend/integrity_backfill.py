from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from data_integrity import INTEGRITY_VERSION, inspect_match_payload


MATCH_FILE = re.compile(r"event_(\d+)_match_(.+)_game_(\d+)_stats\.json$")


def _payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("payload"), dict):
        return value["payload"]
    return value if isinstance(value, dict) else {}


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def cached_match_files(data_dir: str | Path) -> dict[tuple[int, str, int], Path]:
    selected: dict[tuple[int, str, int], Path] = {}
    for path in Path(data_dir).rglob("event_*_match_*_game_*_stats.json"):
        match = MATCH_FILE.match(path.name)
        if not match:
            continue
        key = (int(match.group(1)), match.group(2), int(match.group(3)))
        current = selected.get(key)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            selected[key] = path
    return selected


def audit_cached_match_stats(
    conn: sqlite3.Connection,
    data_dir: str | Path,
    *,
    apply: bool = False,
    limit: int | None = None,
    event_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    # Delayed import avoids the season_platform -> data_integrity dependency
    # becoming a circular import at module initialization.
    from season_platform import match_stats_completed, normalize_match_stats_to_rounds

    conn.row_factory = sqlite3.Row
    files = cached_match_files(data_dir)
    result: dict[str, Any] = {
        "integrityVersion": INTEGRITY_VERSION,
        "mode": "APPLY" if apply else "DRY_RUN",
        "filesDiscovered": len(files),
        "eligibleFinalGames": 0,
        "partialGames": 0,
        "alreadyCurrent": 0,
        "validated": 0,
        "quarantined": 0,
        "remaining": 0,
        "games": [],
    }
    pending: list[tuple[tuple[int, str, int], Path, dict[str, Any], str]] = []
    for key, path in sorted(files.items()):
        if event_id is not None and key[0] != int(event_id):
            continue
        try:
            payload = _payload(path)
        except Exception as exc:
            result["quarantined"] += 1
            result["games"].append({"eventId": key[0], "matchId": key[1], "gameId": key[2], "status": "UNREADABLE", "error": str(exc)})
            continue
        completed = match_stats_completed(payload)
        if completed:
            result["eligibleFinalGames"] += 1
        else:
            result["partialGames"] += 1
        fingerprint = _hash(payload)
        existing = conn.execute(
            """SELECT integrity_version,source_payload_hash FROM game_data_integrity
               WHERE event_id=? AND match_id=? AND game_id=?""",
            key,
        ).fetchone()
        if existing and existing["integrity_version"] == INTEGRITY_VERSION and existing["source_payload_hash"] == fingerprint and not force:
            result["alreadyCurrent"] += 1
            continue
        pending.append((key, path, payload, fingerprint))

    selected = pending[: max(0, int(limit))] if limit is not None else pending
    result["remaining"] = max(0, len(pending) - len(selected))
    for key, path, payload, fingerprint in selected:
        completed = match_stats_completed(payload)
        inspection = inspect_match_payload(payload, completed=completed)
        status = ("WOULD_VERIFY" if inspection["passed"] else "WOULD_QUARANTINE") if completed else "WOULD_RETAIN_RAW_ONLY"
        if apply:
            normalize_match_stats_to_rounds(conn, key[0], key[1], key[2], payload)
            row = conn.execute(
                """SELECT integrity_status FROM game_data_integrity
                   WHERE event_id=? AND match_id=? AND game_id=?""",
                key,
            ).fetchone()
            status = str(row[0]) if row else "MISSING"
        if status in {"VERIFIED", "WOULD_VERIFY"}:
            result["validated"] += 1
        elif status in {"PARTIAL", "WOULD_RETAIN_RAW_ONLY"}:
            pass
        else:
            result["quarantined"] += 1
        result["games"].append({
            "eventId": key[0], "matchId": key[1], "gameId": key[2],
            "status": status, "source": str(path), "checks": inspection,
            "sourcePayloadHash": fingerprint,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit or migrate cached ACL match-stat files into Data Integrity v2.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--event-id", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.database, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        from season_platform import init_db
        init_db(conn)
        result = audit_cached_match_stats(
            conn, args.data_dir, apply=args.apply, limit=args.limit,
            event_id=args.event_id, force=args.force,
        )
        print(json.dumps(result, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
