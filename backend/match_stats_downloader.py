import json
import os
from datetime import datetime, timezone

import requests


AUTH_RETRY_STATUSES = {401, 403}


def configured_data_dir():
    """Return the shared data directory used by the web and worker services."""
    return os.environ.get("DATA_DIR", "data")


def load_cached_match_stats(filepath):
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def is_completed_match_stats(data):
    if not isinstance(data, dict):
        return False

    status = str(data.get("matchStatusDesc") or "").strip().lower()
    return data.get("matchStatus") == 5 or status in {"match completed", "completed", "complete"}


def should_update_match_stats(filepath, force=False):
    """
    Returns True when the stats file is missing, still live/incomplete, or explicitly forced.
    Completed saved files are treated as final and are not downloaded again.
    """
    if force:
        print(f"Force update enabled: {filepath}")
        return True

    data = load_cached_match_stats(filepath)
    if data is None:
        print(f"Match file does not exist: {filepath}")
        return True

    if not is_completed_match_stats(data):
        print(f"Match file exists but status is not completed: {filepath}")
        return True

    print(f"Match file is completed and cached: {filepath}")
    return False


def build_fanzone_headers(cached=None):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "origin": "https://fanzone.iplayacl.com",
        "referer": "https://fanzone.iplayacl.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari/537.36"
        ),
    }

    etag = (cached or {}).get("_aclEtag")
    if etag:
        headers["if-none-match"] = etag

    return headers


def fetch_match_stats_response(url, headers):
    return requests.get(url, headers=headers, timeout=10)


def fetch_and_save_match_stats(
    event_id,
    match_ids,
    game_id=1,
    force=False,
    only_in_progress=False,
    data_dir=None,
):
    saved = 0
    failed = 0
    skipped = 0
    auth_required = 0
    notifications = []

    data_dir = data_dir or configured_data_dir()
    os.makedirs(data_dir, exist_ok=True)

    for match_id in match_ids:
        filename = f"event_{event_id}_match_{match_id}_game_{game_id}_stats.json"
        filepath = os.path.join(data_dir, filename)

        if not should_update_match_stats(filepath, force=force):
            skipped += 1
            continue

        cached = load_cached_match_stats(filepath)
        # A forced request represents an actively viewed/live game. Do not
        # send the cached ETag in that case: ACL can return 304 for a payload
        # captured before the first score even while the game is advancing,
        # which leaves the UI permanently showing 0-0.
        headers = build_fanzone_headers(None if force else cached)
        url = f"https://api.iplayacl.com/api/v1/match-stats/eventid/{event_id}/matchid/{match_id}/gameid/{game_id}"

        try:
            response = fetch_match_stats_response(url, headers)

            if response.status_code == 304:
                skipped += 1
                print(f"Not modified: {filename}")
                continue

            if response.status_code in AUTH_RETRY_STATUSES:
                auth_required += 1
                failed += 1
                message = (
                    "ACL blocked this match-stat file without authentication. "
                    "Cookie fallback is disabled, so this game was skipped and "
                    "round-level stats may show partial coverage."
                )
                notifications.append({
                    "type": "auth_required",
                    "severity": "warning",
                    "eventId": str(event_id),
                    "matchId": str(match_id),
                    "gameId": int(game_id),
                    "statusCode": response.status_code,
                    "message": message,
                })
                print(f"Auth required for match {match_id}: {response.status_code}")
                continue

            if response.status_code != 200:
                print(f"Failed to fetch match {match_id}: {response.status_code}")
                failed += 1
                notifications.append({
                    "type": "match_stats_failed",
                    "severity": "warning",
                    "eventId": str(event_id),
                    "matchId": str(match_id),
                    "gameId": int(game_id),
                    "statusCode": response.status_code,
                    "message": "This match-stat file could not be downloaded, so round-level stats for this game are missing.",
                })
                continue

            data = response.json()
            data["_fetchedAt"] = datetime.now(timezone.utc).isoformat()
            data["_aclResponseDate"] = response.headers.get("date")
            data["_aclEtag"] = response.headers.get("etag")

            if only_in_progress and is_completed_match_stats(data):
                print(f"Skipped completed match {match_id} due to --only-in-progress flag")
                skipped += 1
                continue

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            saved += 1
            print(f"Saved: {filename}")
        except Exception as e:
            print(f"Error fetching match {match_id}: {e}")
            failed += 1

    print("\nSummary:")
    print(f"  Matches saved:   {saved}")
    print(f"  Matches skipped: {skipped}")
    print(f"  Matches failed:  {failed}")
    print(f"  Auth blocked:    {auth_required}")

    return {
        "saved": saved,
        "skipped": skipped,
        "failed": failed,
        "authRequired": auth_required,
        "notifications": notifications,
    }
