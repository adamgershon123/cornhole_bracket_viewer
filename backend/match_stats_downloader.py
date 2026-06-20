import os
import json
import requests

def should_update_match_stats(filepath, force=False):
    """
    Returns True if the match stats file does not exist or the match is not marked as completed.
    If force is True, always return True.
    """
    if force:
        print(f"🔁 Force update enabled: {filepath}")
        return True

    if not os.path.exists(filepath):
        print(f"📂 Match file does not exist: {filepath}")
        return True

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("matchStatusDesc", "").lower() != "match completed":
            print(f"🔄 Match file exists but status is not completed: {filepath}")
            return True
        else:
            print(f"✅ Match file is completed and cached: {filepath}")
            return False
    except Exception as e:
        print(f"⚠️ Error reading {filepath}: {e}")
        return True

def fetch_and_save_match_stats(event_id, match_ids, game_id=1, session_cookie=None, force=False, only_in_progress=False):
    saved = 0
    failed = 0
    skipped = 0

    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0",
        "referer": "https://app.iplayacl.com/",
        "origin": "https://app.iplayacl.com",
    }

    if session_cookie:
        headers["cookie"] = session_cookie

    os.makedirs("data", exist_ok=True)

    for match_id in match_ids:
        filename = f"event_{event_id}_match_{match_id}_game_{game_id}_stats.json"
        filepath = os.path.join("data", filename)

        if not should_update_match_stats(filepath, force=force):
            skipped += 1
            continue

        url = f"https://api.iplayacl.com/api/v1/match-stats/eventid/{event_id}/matchid/{match_id}/gameid/{game_id}"
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()

                if only_in_progress and data.get("matchStatusDesc", "").lower() == "match completed":
                    print(f"⏩ Skipped completed match {match_id} due to --only-in-progress flag")
                    skipped += 1
                    continue

                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                saved += 1
                print(f"✅ Saved: {filename}")
            else:
                print(f"❌ Failed to fetch match {match_id}: {response.status_code}")
                failed += 1
        except Exception as e:
            print(f"❌ Error fetching match {match_id}: {e}")
            failed += 1

    print("\n📊 Summary:")
    print(f"  Matches saved:   {saved}")
    print(f"  Matches skipped: {skipped}")
    print(f"  Matches failed:  {failed}")

    return {"saved": saved, "skipped": skipped, "failed": failed}
