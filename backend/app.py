import json
import csv
import io
import os
import re
import shutil
import sqlite3
import tempfile
import time
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

import requests
from filelock import FileLock
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from consolidate_tournament_stats import consolidate_tournament_stats
from match_stats_downloader import fetch_and_save_match_stats
from season_platform import DB_PATH as SEASON_PLATFORM_DB_PATH
from season_platform import gather_player_focused_season, leaderboard_from_db, parse_player_ids, player_season_options
from season_platform import db as season_platform_db
from lifecycle_runner import (
    monitor_event,
    prediction_operations_snapshot,
    run_lifecycle_cycle,
)
from game_state_reconstruction import reconstruct_game_states
from live_win_probability import calculate_probability_series
from live_probability_evaluation import evaluate_live_probability
from first_throw_analysis import analyze_first_throw
from predictive_player_profile import (
    player_analytics_leaderboard,
    player_analytics_snapshot_status,
    predictive_player_profile,
    start_player_analytics_snapshot_worker,
)
from clutch_rating import validate_clutch_rating
from profile_rating_validation import validate_profile_ratings
from profile_feature_model_validation import validate_profile_features_in_matchup_model
from performance_projections import matchup_expected_performance
from expected_ppr_validation import validate_expected_ppr
from carry_performance import validate_carry_performance
from strength_of_competition import event_strength_of_schedule
from swing_performance import validate_swing_performance
from opponent_adjusted_performance import validate_opponent_adjustment
from prediction_weighting import prediction_weighting_policy
from bracket_simulation import simulate_bracket
from bracket_prediction_snapshots import (
    bracket_player_ids,
    bracket_roster_ready,
    bracket_prediction_timeline,
    has_valid_pregame_snapshot,
)
from player_history_queue import enqueue_players
from bracket_templates import repository_bracket_templates, select_template
from stage_a_features import build_matchup_features
from baseline_predictions import score_matchup
from scoring_distribution_challenger import (
    score_scoring_distribution_challenger,
)
from match_profile_trajectory import match_profile_trajectories
from standings import compute_standings
from season_standings import SeasonConfig, build_consolidated_standings
from historical_backfill import (
    prioritize_events,
    set_lane_paused as set_historical_backfill_lane_paused,
    set_paused as set_historical_backfill_paused,
    start_worker as start_historical_backfill_worker,
    status_snapshot as historical_backfill_status,
    venue_export_rows,
)
from payload_archive import (
    archive_pending_payloads,
    payload_archive_health,
    start_payload_archive_worker,
)
from venue_analytics import (
    acl_season_range,
    default_season_start_year,
    venue_catalog,
    venue_court_ppr,
    venue_event_schedule,
)


# Keep Flask's automatic static route away from the application root.  The
# explicit ``serve_frontend`` fallback below serves built assets and returns
# index.html for client-side routes such as /status/<event>/team/<team>.
app = Flask(__name__, static_folder="../frontend/dist", static_url_path="/__frontend_static")
CORS(app)

DATA_DIR = os.environ.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

SEASON_GATHER_PROGRESS: dict[str, dict[str, Any]] = {}
SEASON_GATHER_RESULTS: dict[str, dict[str, Any]] = {}
SEASON_GATHER_LOCK = threading.Lock()
PREDICTION_LIFECYCLE_LOCK = threading.Lock()
BRACKET_PREDICTION_BUILD_LOCK = threading.Lock()
BRACKET_PREDICTION_BUILDS: set[int] = set()
BRACKET_PREDICTION_BUILD_RESPONSES: dict[int, dict[str, Any]] = {}


@app.route("/api/health")
def api_health():
    try:
        with season_platform_db() as conn:
            conn.execute("SELECT 1").fetchone()
        return jsonify({
            "status": "OK",
            "database": "READY",
            "dataDir": os.path.abspath(DATA_DIR),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        return jsonify({"status": "ERROR", "database": "UNAVAILABLE", "message": str(exc)}), 503


def prediction_lifecycle_search_params() -> dict[str, Any]:
    return {
        "bucket_id": 11,
        "origin_lat": 26.781990538225305,
        "origin_lng": -80.32006282856948,
        "event_range": 10000,
        "selected_time": "WEEK",
        "time_range": 1,
        "event_country_code": "US",
    }


def start_prediction_lifecycle_worker() -> None:
    if os.environ.get("PREDICTION_LIFECYCLE_ENABLED", "1").lower() in {"0", "false", "no"}:
        return
    interval = max(120, int(os.environ.get("PREDICTION_LIFECYCLE_INTERVAL_SECONDS", "120")))

    def worker() -> None:
        # Let the web server become available before the first background pass.
        time.sleep(15)
        while True:
            if PREDICTION_LIFECYCLE_LOCK.acquire(blocking=False):
                try:
                    with season_platform_db() as conn:
                        run_lifecycle_cycle(
                            conn,
                            search_params=prediction_lifecycle_search_params(),
                            lookahead_minutes=1440,
                        )
                except Exception as exc:
                    print(f"Prediction lifecycle background cycle failed: {exc}")
                finally:
                    PREDICTION_LIFECYCLE_LOCK.release()
            time.sleep(interval)

    threading.Thread(
        target=worker,
        daemon=True,
        name="prediction-lifecycle",
    ).start()


def start_bracket_prediction_build(
    event_id: int,
    bracket: dict[str, Any],
    simulations: int,
) -> None:
    with BRACKET_PREDICTION_BUILD_LOCK:
        if event_id in BRACKET_PREDICTION_BUILDS:
            return
        BRACKET_PREDICTION_BUILDS.add(event_id)

    def worker() -> None:
        try:
            with season_platform_db() as conn:
                player_ids = bracket_player_ids(bracket)
                event_info = bracket.get("eventInfo") or {}
                event_date = (
                    event_info.get("startdate")
                    or event_info.get("leagueStartDate")
                    or event_info.get("leaguestartdate")
                )
                enqueue_players(
                    conn,
                    player_ids=player_ids,
                    reason={
                        "source": "bracket-roster",
                        "eventId": str(event_id),
                        "purpose": "frozen-bracket-prediction",
                    },
                    priority=0,
                )
                # Freeze against the information that actually existed when
                # the final roster became known. Deep history gathering stays
                # queued independently and must never hold the first forecast
                # open or retrospectively rewrite it.
                bracket_prediction_timeline(
                    conn,
                    bracket,
                    simulations=simulations,
                    data_dir=DATA_DIR,
                )
        except Exception as exc:
            print(f"Bracket prediction initialization failed for {event_id}: {exc}")
        finally:
            with BRACKET_PREDICTION_BUILD_LOCK:
                BRACKET_PREDICTION_BUILDS.discard(event_id)
                BRACKET_PREDICTION_BUILD_RESPONSES.pop(event_id, None)

    threading.Thread(
        target=worker,
        daemon=True,
        name=f"bracket-prediction-{event_id}",
    ).start()


def bracket_prediction_pending(event_id: int, data: dict[str, Any]) -> Response:
    event_info = data.get("eventInfo") or {}
    return jsonify({
        "status": "PREGAME_PENDING",
        "eventId": event_id,
        "eventName": (
            event_info.get("eventName")
            or event_info.get("leagueName")
            or event_info.get("leaguename")
        ),
        "timelineBuildStatus": "BUILDING",
        "completedMatchesApplied": 0,
        "completedMatchesAvailable": 0,
    })


def season_progress_key(
    player_ids: list[int],
    bucket_id: int | str,
    start_date: str | None,
    end_date: str | None,
) -> str:
    return ":".join([
        ",".join(map(str, player_ids)),
        str(bucket_id),
        start_date or "",
        end_date or "",
    ])


def set_season_progress(key: str, payload: dict[str, Any]) -> None:
    with SEASON_GATHER_LOCK:
        SEASON_GATHER_PROGRESS[key] = {
            **payload,
            "key": key,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }


def swap_cache_path(event_id: str, name: str) -> str:
    folder = os.path.join(DATA_DIR, "swap_live")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"event_{event_id}_{name}.json")


def swap_public_get(event_id: str, name: str, endpoint: str, refresh: bool = True) -> Dict[str, Any]:
    path = swap_cache_path(event_id, name)
    cached = read_json(path)
    if cached is not None and not refresh:
        return cached

    endpoint_path, _, query = endpoint.partition("?")
    url = f"https://api.iplayacl.com/api/v1/{endpoint_path}/{event_id}"
    if query:
        url = f"{url}?{query}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "cache-control": "no-cache",
        "origin": "https://app.iplayacl.com",
        "pragma": "no-cache",
        "referer": "https://app.iplayacl.com/",
        "user-agent": "Mozilla/5.0",
    }
    timeout = 60 if endpoint == "event-player-stats" else 30
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException:
        if endpoint != "event-player-stats":
            raise
        response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    payload["_fetchedAt"] = datetime.now(timezone.utc).isoformat()
    payload["_aclResponseDate"] = response.headers.get("date")
    payload["_aclEtag"] = response.headers.get("etag")
    with tempfile.NamedTemporaryFile("w", delete=False, dir=os.path.dirname(path), encoding="utf-8") as tmp_file:
        json.dump(payload, tmp_file, indent=2)
        temp_path = tmp_file.name
    shutil.move(temp_path, path)
    return payload


def safe_player(row: Dict[str, Any]) -> Dict[str, Any]:
    player_id = row.get("playerID") or row.get("fldPlayerID")
    first = row.get("playerFirstName") or row.get("firstName")
    last = row.get("playerLastName") or row.get("lastName")
    normalized_match = {
        "playerId": player_id,
        "name": f"{first or ''} {last or ''}".strip() or f"Player {player_id}",
        "firstName": first,
        "lastName": last,
        "city": row.get("playerCity"),
        "state": row.get("playerState"),
        "skillLevel": row.get("playerSkillLevel"),
        "group": row.get("playerGroup"),
        "checkedIn": row.get("playerCheckedIn"),
        "photo": row.get("playerPhoto"),
        "ppr": row.get("playerPPR"),
        "pprInfo": row.get("playerPPRPlayerInfo"),
        "cpi": row.get("playerCPI"),
        "membership": row.get("playerMembershipName"),
    }
    return normalized_match


def safe_swap_player(row: Dict[str, Any]) -> Dict[str, Any]:
    player = safe_player(row)
    player.update({
        "wins": int(row.get("wins") or 0),
        "losses": int(row.get("losses") or 0),
        "differential": int(row.get("playerDifferentialPoints") or 0),
        "totalPoints": int(row.get("playerTotalPoints") or 0),
        "rank": int(row.get("rank") or 0),
        "finishPoints": row.get("totalfinishpoints"),
        "partnerHistory": row.get("partnerHistory") if isinstance(row.get("partnerHistory"), list) else [],
    })
    return player


def safe_team_standing_players(row: Dict[str, Any]) -> list[Dict[str, Any]]:
    players = row.get("teamPlayerList") if isinstance(row.get("teamPlayerList"), list) else []
    team_names = [
        f"{player.get('playerFirstName') or ''} {player.get('playerLastName') or ''}".strip()
        for player in players
        if isinstance(player, dict)
    ]
    team_name = " / ".join(name for name in team_names if name)
    output = []
    for player_row in players:
        if not isinstance(player_row, dict):
            continue
        player = safe_player(player_row)
        player.update({
            "teamId": row.get("teamID") or row.get("id"),
            "teamName": team_name,
            "wins": int(row.get("wins") or 0),
            "losses": int(row.get("losses") or 0),
            "differential": int(row.get("playerDifferentialPoints") or row.get("teamDifferentialPoints") or 0),
            "totalPoints": int(row.get("playerTotalPoints") or row.get("teamTotalPoints") or 0),
            "rank": int(row.get("rank") or 0),
            "finishPoints": player_row.get("totalfinishpoints") or row.get("totalfinishpoints"),
            "partnerHistory": [],
        })
        output.append(player)
    return output


def safe_swap_match(row: Dict[str, Any]) -> Dict[str, Any]:
    def team(players: list[Dict[str, Any]]) -> Dict[str, Any]:
        safe = [safe_player(player) for player in players or []]
        return {
            "players": safe,
            "name": " / ".join(player["name"] for player in safe),
            "avgPpr": round(sum(float(player.get("ppr") or 0) for player in safe) / len(safe), 2) if safe else None,
        }

    home_score = row.get("homeScore")
    away_score = row.get("awayScore")
    result_status = row.get("resultGameStatus")
    match_status = str(row.get("matchStatus") or "").lower()
    match_status_id = str(row.get("matchStatusID") or "")
    if "progress" in match_status or match_status_id in {"1", "2"}:
        status = "live"
    elif result_status == 5 or match_status_id == "5" or "completed" in match_status or row.get("matchEndTime"):
        status = "completed"
    elif row.get("matchStartTime"):
        status = "live"
    else:
        status = "next"

    return {
        "eventId": row.get("eventID") or row.get("leagueID"),
        "matchId": row.get("matchID"),
        "courtId": row.get("courtID"),
        "status": status,
        "statusText": row.get("matchStatus"),
        "availableToStart": row.get("availableToStart"),
        "homeTeam": team(row.get("homeTeam") or []),
        "awayTeam": team(row.get("awayTeam") or []),
        "homeScore": home_score,
        "awayScore": away_score,
        "startTime": row.get("matchStartTime"),
        "endTime": row.get("matchEndTime"),
        "homeColor": row.get("homeColor"),
        "awayColor": row.get("awayColor"),
    }


def safe_match_player_stat(row: Dict[str, Any]) -> Dict[str, Any]:
    first = row.get("playerfirstname") or ""
    last = row.get("playerlastname") or ""
    rounds = int(row.get("rounds") or row.get("playedinnings") or 0)
    points = int(row.get("totalpts") or 0)
    opponent_points = int(row.get("opponentpts") or 0)
    return {
        "playerId": row.get("playerid"),
        "teamId": row.get("teamid"),
        "name": f"{first} {last}".strip(),
        "side": row.get("teamhomeaway"),
        "rounds": rounds,
        "points": points,
        "ppr": round(points / rounds, 2) if rounds else row.get("ptsperrnd"),
        "oppPpr": row.get("opponentptsperrnd"),
        "dpr": row.get("diffperrnd"),
        "fourBaggers": int(row.get("totalfourbaggers") or 0),
        "fourBaggerPct": row.get("fourbaggerpct"),
        "bagsInPct": row.get("bagsinpct"),
        "bagsOnPct": row.get("bagsonpct"),
        "bagsOffPct": row.get("bagsoffpct"),
        "bagsThrown": int(row.get("totalbagsthrown") or 0),
    }


def safe_swap_match_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    details = [
        safe_match_player_stat(row)
        for row in data.get("event_match_details", []) or []
        if isinstance(row, dict)
    ]
    return {
        "matchId": data.get("matchID"),
        "gameId": data.get("gameID"),
        "status": data.get("matchStatusDesc"),
        "currentRound": data.get("currentRound"),
        "roundLimit": data.get("roundLimit"),
        "homeScore": data.get("homeScore"),
        "awayScore": data.get("awayScore"),
        "players": details,
        "rounds": [
            {
                "round": row.get("inningNo") or row.get("inningno"),
                "homeScore": row.get("homeScore"),
                "awayScore": row.get("awayScore"),
            }
            for row in data.get("event_match_inning_summary", []) or []
            if isinstance(row, dict)
        ],
    }


def safe_swap_event_player_stat(row: Dict[str, Any]) -> Dict[str, Any]:
    rounds = int(row.get("rounds") or 0)
    points = int(row.get("totalPts") or row.get("totalPoints") or 0)
    return {
        "ranking": int(row.get("ranking") or 0),
        "playerId": row.get("playerID") or row.get("playerId") or row.get("playerid"),
        "rounds": rounds,
        "points": points,
        "ppr": row.get("ptsPerRnd"),
        "oppPpr": row.get("opponentPtsPerRnd"),
        "dpr": row.get("diffPerRnd"),
        "fourBaggers": int(row.get("TotalFourBaggers") or row.get("totalFourBaggers") or 0),
        "fourBaggerPct": row.get("fourBaggerPct"),
        "bagsInPct": row.get("bagsInPct"),
        "bagsOnPct": row.get("bagsOnPct"),
        "bagsOffPct": row.get("bagsOffPct"),
        "avgBagsInPerRound": row.get("avgBagsInPerRnd"),
        "bagsThrown": int(row.get("totalBags") or 0),
        "bagsIn": int(row.get("bagsIn") or 0),
    }


def empty_swap_player_totals() -> Dict[str, Any]:
    return {
        "rounds": 0,
        "points": 0,
        "opponentPoints": 0,
        "fourBaggers": 0,
        "bagsThrown": 0,
    }


def as_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def safe_swap_event(data: Dict[str, Any]) -> Dict[str, Any]:
    info = data or {}
    name = info.get("eventName") or info.get("leagueName") or info.get("leaguename")
    bracket_type = info.get("bracketType") or info.get("brackettype")
    is_rounders = str(bracket_type or "").upper() == "W" or "rounders" in str(name or "").lower()
    return {
        "eventId": info.get("eventID") or info.get("leagueID"),
        "name": name,
        "date": info.get("leagueStartDate") or info.get("startdate"),
        "time": info.get("leagueTime") or info.get("starttime"),
        "status": info.get("leagueStatus"),
        "location": {
            "name": info.get("locationName") or info.get("leagueLocationName"),
            "city": info.get("locationCity"),
            "state": info.get("locationState"),
        },
        "courts": [part.strip() for part in str(info.get("courtTotalDetails") or "").split(",") if part.strip()],
        "roundLimit": info.get("roundLimit"),
        "roundLimitBracket": info.get("roundLimitBracket"),
        "playerPoolSize": info.get("playerPoolSize"),
        "matchType": info.get("matchType") or info.get("matchtype"),
        "bracketType": bracket_type,
        "blindDraw": info.get("blindDraw") or info.get("leagueBlindDraw"),
        "eventMode": "swiss" if is_rounders else "swap",
        "formatLabel": "Rounders" if is_rounders else "Swap",
    }


def public_event_metadata(event_id: str, refresh: bool = True) -> Dict[str, Any]:
    try:
        payload = swap_public_get(event_id, "event", "events", refresh=refresh)
        data = payload.get("data") if isinstance(payload, dict) else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        cached = read_json(swap_cache_path(event_id, "event"), {})
        data = cached.get("data") if isinstance(cached, dict) else {}
        return data if isinstance(data, dict) else {}


def fetch_updated_json(event_id: str) -> None:
    """Existing bracket-data pull, preserved and wrapped for API use."""
    url = f"https://api.iplayacl.com/api/v1/bracket-data/{event_id}"
    local_path = os.path.join(DATA_DIR, f"event_{event_id}.json")
    lock_path = f"{local_path}.lock"

    try:
        with FileLock(lock_path, timeout=5):
            response = requests.get(url)
            if response.status_code == 200:
                try:
                    data = response.json()

                    data["_fetchedAt"] = datetime.now(timezone.utc).isoformat()
                    data["_aclResponseDate"] = response.headers.get("date")
                    data["_aclEtag"] = response.headers.get("etag")
                    with tempfile.NamedTemporaryFile("w", delete=False, dir=DATA_DIR, encoding="utf-8") as tmp_file:
                        json.dump(data, tmp_file, indent=2)
                        temp_path = tmp_file.name
                    shutil.move(temp_path, local_path)
                    print(f"JSON updated safely for event {event_id}")
                except ValueError as e:
                    print(f"Invalid JSON received: {e}")
            else:
                print(f"Failed to fetch JSON: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching JSON for event {event_id}: {e}")


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def is_complete_status(value: Any) -> bool:
    status = str(value or "").strip().upper()
    return status in {"C", "COMPLETE", "COMPLETED"} or "COMPLETE" in status


def bracket_data_is_completed(data: Any) -> bool:
    if not isinstance(data, dict):
        return False

    event_info = data.get("eventInfo") or {}
    if is_complete_status(event_info.get("leagueStatus")):
        return True
    if is_complete_status(event_info.get("leagueStatusDesc")):
        return True
    if is_complete_status(event_info.get("status")):
        return True

    details = data.get("bracketDetails") or []
    match_statuses = [
        item.get("matchStatusID")
        for item in details
        if isinstance(item, dict) and item.get("matchID") not in (None, "")
    ]
    return bool(match_statuses) and all(str(status) == "5" for status in match_statuses)


def game_stats_is_completed(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return data.get("matchStatus") == 5 or is_complete_status(data.get("matchStatusDesc"))


def load_bracket(event_id: str, refresh: bool = True) -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, f"event_{event_id}.json")
    cached = read_json(path)

    if refresh and not bracket_data_is_completed(cached):
        fetch_updated_json(event_id)
    elif refresh:
        print(f"Event {event_id} is completed and cached; bracket refresh skipped")

    data = read_json(path)
    if not isinstance(data, dict):
        raise FileNotFoundError(f"No bracket data available for event {event_id}")
    return data


def team_from_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    players = []
    for p in entry.get("player_info", []) or []:
        first = (p.get("firstname") or "").strip()
        last = (p.get("lastname") or "").strip()
        name = f"{first} {last}".strip()
        if name:
            players.append({
                "id": p.get("playerid") or p.get("id"),
                "firstName": first,
                "lastName": last,
                "displayName": name,
            })
    name = " & ".join(p["displayName"] for p in players) or f"Team {entry.get('bracketteamid', 'TBD')}"
    return {"id": str(entry.get("bracketteamid")) if entry.get("bracketteamid") is not None else None, "name": name, "players": players}


def is_bye_entry(entry: Dict[str, Any]) -> bool:
    names = [
        entry.get("bracketteamname"),
        entry.get("teamname"),
        *[
            " ".join(filter(None, [player.get("firstname"), player.get("lastname")]))
            for player in (entry.get("player_info") or [])
        ],
    ]
    return any(
        str(name or "").strip().lower() == "bye"
        or str(name or "").strip().lower().startswith("bye user")
        for name in names
    )


def score_from_entry(top: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    scores = top.get("scores") or []
    if not scores or not isinstance(scores[0], dict):
        return None, None
    def to_int(v):
        try:
            return int(v)
        except Exception:
            return None
    return to_int(scores[0].get("scorehome")), to_int(scores[0].get("scoreaway"))


def get_match_groups(bracket_details: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in bracket_details:
        match_id = entry.get("bracketmatchid")
        if match_id is not None:
            groups[str(match_id)].append(entry)
    return groups


def split_top_bottom(pair: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    top = bottom = None
    for item in pair:
        pos = item.get("bracketpos", "")
        if "T" in pos:
            top = item
        elif "B" in pos:
            bottom = item
    if not top and len(pair) > 0:
        top = pair[0]
    if not bottom and len(pair) > 1:
        bottom = pair[1]
    return top, bottom


def bracket_round_sort(label: Any) -> int:
    text = str(label or "").lower()
    match = re.search(r"(\d+)", text)
    number = int(match.group(1)) if match else 0
    if "champion" in text:
        return 1000
    if "quarter" in text:
        return 700 + number
    if "semi" in text:
        return 800 + number
    if "final" in text:
        return 900 + number
    if "loser" in text:
        return 500 + number
    return number or 100


def bracket_match_order(match: Dict[str, Any]) -> int:
    return bracket_round_sort(match.get("rounddesc")) * 10000 + int(match.get("bracketmatchid") or 0)


def derive_tournament_match_results(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    groups = get_match_groups(data.get("bracketDetails", []) or [])
    player_results: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "match_wins": 0,
        "match_losses": 0,
        "match_ties": 0,
        "match_record": "0-0",
        "finish_place": None,
    })
    team_results: Dict[str, Dict[str, Any]] = {}

    def ensure_team(team: Dict[str, Any], match: Dict[str, Any]) -> Dict[str, Any]:
        team_id = str(team.get("id") or "")
        if not team_id:
            return {}
        if team_id not in team_results:
            team_results[team_id] = {
                "id": team_id,
                "players": [str(player.get("id")) for player in team.get("players", []) or [] if player.get("id")],
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "last_loss_order": -1,
                "last_match_order": -1,
                "champion": False,
            }
        team_results[team_id]["last_match_order"] = max(team_results[team_id]["last_match_order"], bracket_match_order(match))
        return team_results[team_id]

    matches: List[Dict[str, Any]] = []
    for pair in groups.values():
        top, bottom = split_top_bottom(pair)
        if not top or not bottom:
            continue
        if is_bye_entry(top) or is_bye_entry(bottom):
            # A bye is a bracket-routing instruction, not a played match.
            continue
        top_team = team_from_entry(top)
        bottom_team = team_from_entry(bottom)
        if not top_team.get("id") or not bottom_team.get("id"):
            continue
        top_score, bottom_score = score_from_entry(top)
        match = {
            "bracketmatchid": top.get("bracketmatchid"),
            "rounddesc": top.get("rounddesc"),
            "matchStatusID": top.get("matchStatusID"),
            "topTeam": top_team,
            "bottomTeam": bottom_team,
            "topScore": top_score,
            "bottomScore": bottom_score,
        }
        matches.append(match)
        ensure_team(top_team, match)
        ensure_team(bottom_team, match)

    completed_matches = []
    for match in sorted(matches, key=bracket_match_order):
        status_id = match.get("matchStatusID")
        top_score = match.get("topScore")
        bottom_score = match.get("bottomScore")
        if status_id != 5 or top_score is None or bottom_score is None:
            continue

        top_team = ensure_team(match["topTeam"], match)
        bottom_team = ensure_team(match["bottomTeam"], match)
        if not top_team or not bottom_team:
            continue

        if top_score > bottom_score:
            winner, loser = top_team, bottom_team
        elif bottom_score > top_score:
            winner, loser = bottom_team, top_team
        else:
            top_team["ties"] += 1
            bottom_team["ties"] += 1
            for pid in top_team["players"] + bottom_team["players"]:
                player_results[pid]["match_ties"] += 1
            continue

        order = bracket_match_order(match)
        winner["wins"] += 1
        loser["losses"] += 1
        loser["last_loss_order"] = max(loser["last_loss_order"], order)
        completed_matches.append((order, winner["id"], loser["id"]))

        for pid in winner["players"]:
            player_results[pid]["match_wins"] += 1
        for pid in loser["players"]:
            player_results[pid]["match_losses"] += 1

    if completed_matches:
        final_order = max(order for order, _, _ in completed_matches)
        for order, winner_id, _ in completed_matches:
            if order == final_order and winner_id in team_results:
                team_results[winner_id]["champion"] = True

    event_complete = bool(matches) and all(match.get("matchStatusID") == 5 for match in matches if match.get("topTeam", {}).get("id") and match.get("bottomTeam", {}).get("id"))
    ranked_teams = sorted(
        team_results.values(),
        key=lambda team: (
            0 if team.get("champion") else 1,
            -int(team.get("last_loss_order") or -1),
            -int(team.get("wins") or 0),
            str(team.get("id")),
        ),
    )

    for index, team in enumerate(ranked_teams, start=1):
        eliminated = team.get("losses", 0) >= 2 or (event_complete and not team.get("champion"))
        place = 1 if team.get("champion") else index if eliminated or event_complete else None
        for pid in team.get("players", []):
            result = player_results[pid]
            result["match_record"] = f"{result['match_wins']}-{result['match_losses']}"
            result["finish_place"] = place

    for result in player_results.values():
        result["match_record"] = f"{result['match_wins']}-{result['match_losses']}"

    return dict(player_results)


def load_game_stats(event_id: str, match_id: str, game_id: int) -> Optional[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, f"event_{event_id}_match_{match_id}_game_{game_id}_stats.json")
    data = read_json(path)
    return data if isinstance(data, dict) else None


def maybe_fetch_match_stats(
    event_id: str,
    match_id: str,
    game_id: int,
    force: bool = False,
    refresh_completed: bool = False,
) -> Dict[str, Any]:
    existing = load_game_stats(event_id, match_id, game_id)
    if force and game_stats_is_completed(existing) and not refresh_completed:
        force = False
        print(f"Match {match_id} game {game_id} is completed and cached; forced stats refresh skipped")

    return fetch_and_save_match_stats(
        event_id,
        [int(match_id)],
        game_id=game_id,
        force=force,
        data_dir=DATA_DIR,
    )


def played_game_stat_targets(
    data: Dict[str, Any],
    team_id: Optional[str] = None,
) -> List[Tuple[str, int, bool]]:
    targets: Dict[Tuple[str, int], bool] = {}
    groups = get_match_groups(data.get("bracketDetails", []) or [])

    for match_id, pair in groups.items():
        top, bottom = split_top_bottom(pair)
        if not top or not bottom:
            continue

        if team_id is not None:
            team_ids = {
                str(team_from_entry(top).get("id") or ""),
                str(team_from_entry(bottom).get("id") or ""),
            }
            if str(team_id) not in team_ids:
                continue
            # A bye is bracket movement, not a played game, and must not affect
            # the viewed team's tournament performance totals.
            if is_bye_entry(top) or is_bye_entry(bottom):
                continue

        if not team_from_entry(top).get("id") or not team_from_entry(bottom).get("id"):
            continue

        top_score, bottom_score = score_from_entry(top)
        game_results = top.get("gameResults") or []

        if not game_results:
            status_id = top.get("matchStatusID")
            has_score = top_score is not None or bottom_score is not None
            if status_id in (0, 5) or has_score:
                targets[(str(match_id), 1)] = status_id == 0
            continue

        for game in game_results:
            game_id = int(game.get("gameID") or 1)
            status_id = game.get("matchStatusID", top.get("matchStatusID"))
            score_home = game.get("scoreHome", top_score)
            score_away = game.get("scoreAway", bottom_score)
            has_score = score_home is not None or score_away is not None

            if status_id in (0, 5) or has_score:
                targets[(str(match_id), game_id)] = status_id == 0

    return [(match_id, game_id, force) for (match_id, game_id), force in sorted(
        targets.items(),
        key=lambda item: (int(item[0][0]), item[0][1]),
    )]


def ensure_tournament_match_stats(
    event_id: str,
    data: Dict[str, Any],
    refresh_live: bool = True,
    team_id: Optional[str] = None,
) -> Dict[str, int]:
    targets = played_game_stat_targets(data, team_id=team_id)
    fetched = 0
    failed = 0
    auth_required = 0
    notifications = []

    for match_id, game_id, is_live in targets:
        try:
            result = maybe_fetch_match_stats(event_id, match_id, game_id, force=(refresh_live and is_live))
            fetched += 1
            failed += int(result.get("failed", 0) or 0)
            auth_required += int(result.get("authRequired", 0) or 0)
            notifications.extend(result.get("notifications", []) or [])
        except Exception as e:
            failed += 1
            print(f"Stats fetch skipped/failed for tournament stats match {match_id} game {game_id}: {e}")

    return {
        "targets": len(targets),
        "attempted": fetched,
        "failed": failed,
        "authRequired": auth_required,
        "notifications": notifications,
    }


def team_tournament_stat_coverage(
    event_id: str,
    data: Dict[str, Any],
    team_id: Optional[str],
) -> Dict[str, Any]:
    if not team_id:
        return {}

    groups = get_match_groups(data.get("bracketDetails", []) or [])
    targets = played_game_stat_targets(data, team_id=team_id)
    usable = 0
    missing_games: List[Dict[str, Any]] = []

    for match_id, game_id, _ in targets:
        top, bottom = split_top_bottom(groups.get(str(match_id), groups.get(int(match_id), [])))
        subject = next((entry for entry in (top, bottom) if entry and str(team_from_entry(entry).get("id") or "") == str(team_id)), None)
        expected_players = {
            str(player.get("playerid"))
            for player in ((subject or {}).get("player_info") or [])
            if player.get("playerid") is not None
        }
        raw = load_game_stats(event_id, match_id, game_id) or {}
        recorded_players = {
            str(row.get("playerid"))
            for row in (raw.get("event_match_inning_history") or [])
            if row.get("playerid") is not None
        }
        is_usable = bool(expected_players) and expected_players.issubset(recorded_players)
        if is_usable:
            usable += 1
        else:
            missing_games.append({"matchId": str(match_id), "gameId": game_id})

    return {
        "eligibleGames": len(targets),
        "usableGames": usable,
        "missingGames": missing_games,
        "complete": usable == len(targets),
    }


def fetch_player_season_stats(player_ids, bucket_id=11):
    """Pull ACL season/career compare stats for all players in one request."""
    ids = sorted({int(pid) for pid in player_ids if pid})

    if not ids:
        return {}

    url = "https://api.iplayacl.com/api/v1/player-compare-stats"

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://app.iplayacl.com",
        "referer": "https://app.iplayacl.com/",
        "user-agent": "Mozilla/5.0",
        "x-app-version": "14.1.0",
    }

    payload = {
        "playerIDs": ids,
        "bucketID": bucket_id,
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        raw = r.json()

        out = {}

        for p in raw.get("data", []) or []:
            pid = str(p.get("playerID"))
            out[pid] = {
                "seasonBucketId": p.get("bucketID"),
                "seasonYear": p.get("yearDesc"),
                "seasonSkillLevel": p.get("playerSkillLevel"),
                "seasonPpr": p.get("ptsPerRnd"),
                "seasonDpr": p.get("DPR"),
                "seasonOppPpr": p.get("OppPtsPerRnd"),
                "seasonFourBagPct": p.get("fourBagPct"),
                "seasonBagsInPct": p.get("bagsInPct"),
                "seasonRoundWinPct": p.get("roundsWonPct"),
            }

        return out

    except Exception as e:
        print(f"Failed to fetch player season stats: {e}")
        return {}


def enrich_matches_with_season_stats(matches, bucket_id=11):
    """Add season baselines and +/- vs season to each normalized game player."""
    player_ids = set()

    for match in matches:
        for game in match.get("games", []) or []:
            for p in game.get("players", []) or []:
                if p.get("id"):
                    player_ids.add(p.get("id"))

    season_stats = fetch_player_season_stats(player_ids, bucket_id=bucket_id)

    for match in matches:
        for game in match.get("games", []) or []:
            for p in game.get("players", []) or []:
                season = season_stats.get(str(p.get("id")), {})
                p.update(season)

                game_ppr = p.get("ppr")
                season_ppr = p.get("seasonPpr")

                if game_ppr is not None and season_ppr is not None:
                    diff = round(float(game_ppr) - float(season_ppr), 2)
                    p["pprVsSeason"] = diff
                    p["pprTrend"] = "up" if diff > 0 else "down" if diff < 0 else "even"
                else:
                    p["pprVsSeason"] = None
                    p["pprTrend"] = "unknown"

    return matches


def flatten_matches_by_game(matches):
    """
    Return one selectable row per game.
    Game 1 keeps the normal match label.
    Game 2+ gets a gameLabel so finals reset games are visible without showing "Game 1".
    """
    flat = []

    for match in matches:
        games = match.get("games") or []

        if not games:
            row = dict(match)
            row["id"] = f"{match.get('matchId')}:1"
            row["gameId"] = 1
            row["gameLabel"] = None
            flat.append(row)
            continue

        for game in games:
            gid = int(game.get("gameId") or 1)
            row = dict(match)
            row["id"] = f"{match.get('matchId')}:{gid}"
            row["gameId"] = gid
            row["gameLabel"] = f"Game {gid}" if gid > 1 else None
            row["games"] = [game]
            row["activeGame"] = game
            row["score"] = game.get("score", match.get("score"))

            game_status_id = game.get("statusId")
            if game_status_id == 0:
                row["status"] = "live"
            elif game_status_id == 5:
                row["status"] = "completed"
            else:
                row["status"] = "upcoming"

            flat.append(row)

    return flat


def normalize_player_totals(details: List[Dict[str, Any]], inning_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    totals: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "id": None, "name": "", "teamId": None, "points": 0, "opponentPoints": 0,
        "rounds": 0, "bagsIn": 0, "bagsOn": 0, "bagsOff": 0, "fourBaggers": 0,
        "roundsWon": 0, "roundsLost": 0, "roundsTied": 0,
    })

    for p in details or []:
        pid = str(p.get("playerid"))
        item = totals[pid]
        item["id"] = pid
        item["teamId"] = str(p.get("teamid")) if p.get("teamid") is not None else item["teamId"]
        first = p.get("playerfirstname", "")
        last = p.get("playerlastname", "")
        item["name"] = f"{first} {last[:1]}.".strip()
        item["points"] += p.get("totalpts", 0) or 0
        item["opponentPoints"] += p.get("opponentpts", 0) or 0
        item["rounds"] += p.get("rounds", 0) or 0
        item["bagsIn"] += p.get("totalbagsin", 0) or 0
        item["bagsOn"] += p.get("totalbagson", 0) or 0
        item["bagsOff"] += p.get("totalbagsoff", 0) or 0
        item["fourBaggers"] += p.get("totalfourbaggers", 0) or 0

    inning_map: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for inning in inning_history or []:
        inning_map[inning.get("inningno")].append(inning)

    for rows in inning_map.values():
        if len(rows) != 2:
            continue

        a, b = rows[0], rows[1]
        aid, bid = str(a.get("playerid")), str(b.get("playerid"))
        ap, bp = a.get("totalpoints", 0) or 0, b.get("totalpoints", 0) or 0

        # Do not count unfinished 0-0 rounds as ties.
        if ap == 0 and bp == 0:
            continue

        if ap > bp:
            totals[aid]["roundsWon"] += 1
            totals[bid]["roundsLost"] += 1
        elif bp > ap:
            totals[bid]["roundsWon"] += 1
            totals[aid]["roundsLost"] += 1
        else:
            totals[aid]["roundsTied"] += 1
            totals[bid]["roundsTied"] += 1

    out = []

    for item in totals.values():
        rounds = item["rounds"] or (item["roundsWon"] + item["roundsLost"] + item["roundsTied"])
        outcomes = item["roundsWon"] + item["roundsLost"] + item["roundsTied"]
        thrown = rounds * 4

        item.update({
            "ppr": round(item["points"] / rounds, 2) if rounds else 0,
            "dpr": round((item["points"] - item["opponentPoints"]) / rounds, 2) if rounds else 0,
            "roundWinPct": round(item["roundsWon"] * 100 / outcomes, 1) if outcomes else 0,
            "roundLossPct": round(item["roundsLost"] * 100 / outcomes, 1) if outcomes else 0,
            "roundTiePct": round(item["roundsTied"] * 100 / outcomes, 1) if outcomes else 0,
            "fourBaggerPct": round(item["fourBaggers"] * 100 / rounds, 1) if rounds else 0,
            "bagsInPct": round(item["bagsIn"] * 100 / thrown, 1) if thrown else 0,
        })

        out.append(item)

    return sorted(out, key=lambda x: (x["ppr"], x["dpr"]), reverse=True)

def normalize_rounds(inning_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    inning_map: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for inning in inning_history or []:
        inning_map[inning.get("inningno")].append(inning)
    rounds = []
    cumulative: Dict[str, int] = defaultdict(int)
    for no in sorted([k for k in inning_map.keys() if k is not None]):
        rows = inning_map[no]
        round_players = []
        for r in rows:
            tid = str(r.get("teamid"))
            pts = r.get("totalpoints", 0) or 0
            cumulative[tid] += pts
            round_players.append({
                "playerId": str(r.get("playerid")),
                "teamId": tid,
                "name": f"{r.get('playerfirstname', '')} {(r.get('playerlastname', '') or '')[:1]}.".strip(),
                "grossPoints": pts,
                "teamScoreAfter": cumulative[tid],
                "bagsIn": int(r.get("bagsin") or 0),
                "bagsOn": int(r.get("bagson") or 0),
                "bagsOff": int(r.get("bagsoff") or 0),
                "fourBagger": int(r.get("bagsin") or 0) == 4,
            })
        net = 0
        scoring_team_id = None
        if len(round_players) == 2:
            diff = round_players[0]["grossPoints"] - round_players[1]["grossPoints"]
            if diff > 0:
                net = diff; scoring_team_id = round_players[0]["teamId"]
            elif diff < 0:
                net = abs(diff); scoring_team_id = round_players[1]["teamId"]
        rounds.append({"round": no, "players": round_players, "netPoints": net, "scoringTeamId": scoring_team_id})
    states = reconstruct_game_states(rounds)
    for round_row, state in zip(rounds, states):
        round_row["gameState"] = state
    return rounds


def normalize_match(
    event_id: str,
    match_id: str,
    pair: List[Dict[str, Any]],
    include_stats: bool = True,
    event_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    top, bottom = split_top_bottom(pair)
    if not top or not bottom:
        return None
    top_score, bottom_score = score_from_entry(top)
    games = []
    game_results = top.get("gameResults") or []
    if not game_results:
        game_results = [{"gameID": 1, "scoreHome": top_score, "scoreAway": bottom_score, "matchStatusID": top.get("matchStatusID")}]
    for g in game_results:
        gid = int(g.get("gameID") or 1)
        stats = load_game_stats(event_id, match_id, gid) if include_stats else None
        stats_fetch_result: Dict[str, Any] = {}
        if include_stats and (g.get("matchStatusID") == 0 or not stats):
            try:
                stats_fetch_result = maybe_fetch_match_stats(event_id, match_id, gid, force=(g.get("matchStatusID") == 0))
                stats = load_game_stats(event_id, match_id, gid)
            except Exception as e:
                print(f"Stats fetch skipped/failed for match {match_id} game {gid}: {e}")
        game_home = (stats or {}).get("homeScore", g.get("scoreHome", top_score))
        game_away = (stats or {}).get("awayScore", g.get("scoreAway", bottom_score))
        inning_history = (stats or {}).get("event_match_inning_history", [])
        details = (stats or {}).get("event_match_details", [])
        games.append({
            "gameId": gid,
            "statusId": (stats or {}).get("matchStatus", g.get("matchStatusID", top.get("matchStatusID"))),
            "status": (stats or {}).get("matchStatusDesc"),
            "currentRound": (stats or {}).get("currentRound", top.get("currentRound")),
            "score": {"top": game_home, "bottom": game_away},
            "players": normalize_player_totals(details, inning_history),
            "rounds": normalize_rounds(inning_history),
            "coverageNotifications": stats_fetch_result.get("notifications", []),
        })
    status_id = top.get("matchStatusID")
    active_game = next((g for g in games if g.get("statusId") == 0), games[-1] if games else None)
    normalized_match = {
        "eventId": event_id,
        "matchId": match_id,
        "courtId": str(top.get("courtid", "")),
        "roundDescription": top.get("rounddesc", "Match"),
        "bracketSide": top.get("bracketside", ""),
        "statusId": status_id,
        "status": "live" if status_id == 0 else "completed" if status_id == 5 else "upcoming",
        "currentRound": top.get("currentRound"),
        "teams": {"top": team_from_entry(top), "bottom": team_from_entry(bottom)},
        "score": {"top": top_score, "bottom": bottom_score},
        "games": games,
        "activeGame": active_game,
        "raw": {"top": top, "bottom": bottom},
    }
    attach_live_win_probability(normalized_match, event_date=event_date)
    return normalized_match


def attach_match_profile_trajectories(match: Dict[str, Any]) -> None:
    """Attach lightweight round-by-round season effects to detailed match data."""
    try:
        conn = season_platform_db()
        try:
            for game in match.get("games") or []:
                game["profileTrajectories"] = match_profile_trajectories(
                    conn,
                    event_id=int(match["eventId"]),
                    rounds=game.get("rounds") or [],
                )
            active = match.get("activeGame")
            if active:
                active_game_id = int(active.get("gameId") or 1)
                attached = next(
                    (
                        game for game in match.get("games") or []
                        if int(game.get("gameId") or 1) == active_game_id
                    ),
                    None,
                )
                if attached:
                    match["activeGame"] = attached
        finally:
            conn.close()
    except Exception as exc:
        match["profileTrajectoryError"] = str(exc)


def attach_live_win_probability(match: Dict[str, Any], event_date: Optional[str] = None) -> None:
    teams = match.get("teams") or {}
    top_team = teams.get("top") or {}
    bottom_team = teams.get("bottom") or {}
    top_team_id = str(top_team.get("id") or "")
    bottom_team_id = str(bottom_team.get("id") or "")
    if not top_team_id or not bottom_team_id:
        return
    top_ids = [str(p.get("id")) for p in top_team.get("players") or [] if p.get("id")]
    bottom_ids = [str(p.get("id")) for p in bottom_team.get("players") or [] if p.get("id")]
    pregame, top_samples, bottom_samples = 0.5, [], []
    pregame_evidence = None
    if os.path.exists(SEASON_PLATFORM_DB_PATH):
        try:
            conn = sqlite3.connect(SEASON_PLATFORM_DB_PATH)
            conn.row_factory = sqlite3.Row
            prediction = conn.execute(
                """
                SELECT side_a_player_ids_json, side_a_probability, side_b_probability
                FROM prediction_records
                WHERE event_id=? AND match_id=? AND prediction_status='PREDICTED'
                ORDER BY prediction_id DESC LIMIT 1
                """,
                (str(match.get("eventId")), str(match.get("matchId"))),
            ).fetchone()
            if prediction:
                side_a = {str(value) for value in json.loads(prediction["side_a_player_ids_json"])}
                if side_a == set(top_ids):
                    pregame = float(prediction["side_a_probability"])
                elif side_a == set(bottom_ids):
                    pregame = float(prediction["side_b_probability"])
            event_row = conn.execute(
                "SELECT event_date FROM events WHERE event_id=?",
                (int(match.get("eventId")),),
            ).fetchone()
            cutoff_date = (
                event_row["event_date"]
                if event_row and event_row["event_date"]
                else event_date
            )
            if cutoff_date:
                matchup = build_matchup_features(
                    conn,
                    side_a_player_ids=[int(value) for value in top_ids],
                    side_b_player_ids=[int(value) for value in bottom_ids],
                    cutoff_at=f"{str(cutoff_date)[:10]}T00:00:00+00:00",
                    window_days=365,
                    include_acl_snapshots=True,
                )
                player_names = {
                    int(player["id"]): player.get("displayName") or f"Player {player['id']}"
                    for team in (top_team, bottom_team)
                    for player in team.get("players") or []
                    if player.get("id")
                }
                for side in ("sideA", "sideB"):
                    for player in matchup[side]["players"]:
                        player["displayName"] = player_names.get(
                            int(player["playerId"]),
                            f"Player {player['playerId']}",
                        )
                current_prediction = score_matchup(
                    matchup,
                    model_version="fitted-ppr-logistic-v1",
                )
                challenger_prediction = score_scoring_distribution_challenger(
                    matchup
                )
                # The scoring-distribution model remains a prospective shadow
                # challenger. Public game and bracket forecasts must use the
                # active validated PPR control until a promotion gate is passed.
                primary_prediction = current_prediction
                if current_prediction["status"] == "PREDICTED":
                    pregame = float(current_prediction["sideAProbability"])
                pregame_evidence = {
                    "modelVersion": primary_prediction["modelVersion"],
                    "featureVersion": current_prediction["featureVersion"],
                    "dataCutoffAt": current_prediction["dataCutoffAt"],
                    "evidenceTier": current_prediction["evidenceTier"],
                    "status": primary_prediction["status"],
                    "topProbability": primary_prediction.get("sideAProbability"),
                    "bottomProbability": primary_prediction.get("sideBProbability"),
                    "rawTopProbability": primary_prediction.get("sideAProbability"),
                    "shrinkageFactor": current_prediction.get("shrinkageFactor"),
                    "activeFeature": "predictivePprDelta",
                    "presentationStatus": "ACTIVE_CONTROL",
                    "top": matchup["sideA"],
                    "bottom": matchup["sideB"],
                    "profileRatingWeights": prediction_weighting_policy()["profileRatings"],
                    "control": current_prediction,
                    "challenger": challenger_prediction,
                }
            top_samples = historical_gross_samples(conn, top_ids)
            bottom_samples = historical_gross_samples(conn, bottom_ids)
            conn.close()
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(
                f"Pregame history unavailable for event {match.get('eventId')} "
                f"match {match.get('matchId')}: {exc}"
            )
            pregame, top_samples, bottom_samples = 0.5, [], []
    for game in match.get("games") or []:
        if not game.get("rounds"):
            continue
        game["liveWinProbability"] = calculate_probability_series(
            game["rounds"],
            top_team_id=top_team_id,
            bottom_team_id=bottom_team_id,
            pregame_top_probability=pregame,
            top_gross_samples=top_samples,
            bottom_gross_samples=bottom_samples,
            simulations=10_000,
            seed_key=f"{match.get('eventId')}:{match.get('matchId')}:{game.get('gameId')}",
        )
        game["liveWinProbability"]["pregameEvidence"] = pregame_evidence


def historical_gross_samples(conn: sqlite3.Connection, player_ids: List[str]) -> List[int]:
    ids = [int(value) for value in player_ids if str(value).isdigit()]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT gross_points FROM player_rounds
        WHERE player_id IN ({placeholders}) AND gross_points BETWEEN 0 AND 12
        ORDER BY event_date DESC, event_id DESC, match_id DESC, round_no DESC
        LIMIT 5000
        """,
        ids,
    ).fetchall()
    return [int(row[0]) for row in rows]


def season_event_metadata(event_id: str) -> Dict[str, Any]:
    if not os.path.exists(SEASON_PLATFORM_DB_PATH):
        return {}
    try:
        conn = sqlite3.connect(SEASON_PLATFORM_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT event_id, event_name, event_date, status, location_name, location_city, location_state,
                   match_type, bracket_type, blind_draw, event_type, event_sub_type
            FROM events
            WHERE event_id = ?
            """,
            (int(event_id),),
        ).fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception:
        return {}


def prediction_event_date(event_id: str, data: Dict[str, Any]) -> Optional[str]:
    event_info = data.get("eventInfo", {}) or {}
    saved_event = season_event_metadata(event_id)
    event_date = (
        event_info.get("eventDate")
        or event_info.get("leagueDate")
        or event_info.get("startdate")
        or event_info.get("leagueStartDate")
        or saved_event.get("event_date")
    )
    if event_date:
        return str(event_date)[:10]
    public_event = public_event_metadata(event_id, refresh=False)
    value = public_event.get("startdate") or public_event.get("leagueStartDate")
    return str(value)[:10] if value else None


def normalize_tournament(event_id: str, data: Dict[str, Any], include_stats: bool = False) -> Dict[str, Any]:
    matches_raw = data.get("bracketDetails", []) or []
    groups = get_match_groups(matches_raw)

    event_info = data.get("eventInfo", {}) or {}
    saved_event = season_event_metadata(event_id)
    event_date = prediction_event_date(event_id, data)
    public_event = {}

    matches = []

    for mid, pair in groups.items():
        item = normalize_match(
            event_id,
            mid,
            pair,
            include_stats=include_stats,
            event_date=event_date,
        )
        if item:
            matches.append(item)

    if include_stats:
        bucket_id = int(request.args.get("bucket_id", 11))
        matches = enrich_matches_with_season_stats(matches, bucket_id=bucket_id)

    notifications = [
        notification
        for match in matches
        for game in match.get("games", []) or []
        for notification in game.get("coverageNotifications", []) or []
    ]
    if not matches and str(data.get("message") or "").strip():
        notifications.append({
            "type": "event_data_unavailable",
            "message": data.get("message"),
            "source": "bracket-data",
        })

    matches = flatten_matches_by_game(matches)

    if not matches and not event_info:
        public_event = public_event_metadata(event_id, refresh=True)
    court_order = event_info.get("courtTotalDetails", "")
    if not court_order:
        court_order = public_event.get("courtTotalDetails", "")
    courts = [c.strip() for c in str(court_order).split(",") if c.strip()]

    return {
        "event": {
            "id": event_id,
            "name": event_info.get("leagueName") or event_info.get("eventName") or event_info.get("leaguename") or public_event.get("leagueName") or public_event.get("eventName") or public_event.get("leaguename") or saved_event.get("event_name") or f"Event {event_id}",
            "date": event_info.get("eventDate") or event_info.get("leagueDate") or public_event.get("startdate") or public_event.get("leagueStartDate") or saved_event.get("event_date"),
            "venue": saved_event.get("location_name") or public_event.get("leagueLocationName") or public_event.get("locationName"),
            "location": {
                "name": saved_event.get("location_name") or public_event.get("leagueLocationName") or public_event.get("locationName"),
                "city": saved_event.get("location_city") or public_event.get("locationCity"),
                "state": saved_event.get("location_state") or public_event.get("locationState"),
            },
            "status": event_info.get("leagueStatus") or event_info.get("leagueStatusDesc") or event_info.get("status") or public_event.get("leagueStatus") or saved_event.get("status"),
            "leagueStatus": event_info.get("leagueStatus") or public_event.get("leagueStatus"),
            "matchType": saved_event.get("match_type") or event_info.get("matchType") or event_info.get("matchtype") or public_event.get("matchType") or public_event.get("matchtype"),
            "bracketType": saved_event.get("bracket_type") or event_info.get("bracketType") or event_info.get("brackettype") or public_event.get("bracketType") or public_event.get("brackettype"),
            "blindDraw": saved_event.get("blind_draw") if saved_event.get("blind_draw") is not None else (event_info.get("blindDraw") or event_info.get("leagueBlindDraw") or public_event.get("blindDraw") or public_event.get("leagueBlindDraw")),
            "eventType": saved_event.get("event_type") or event_info.get("eventType") or event_info.get("eventtype") or public_event.get("eventType") or public_event.get("eventtype"),
            "eventSubType": saved_event.get("event_sub_type") or event_info.get("eventSubType") or event_info.get("eventsubtype") or public_event.get("eventSubType") or public_event.get("eventsubtype"),
            "roundLimit": event_info.get("roundLimit") or public_event.get("roundLimit"),
            "roundLimitBracket": event_info.get("roundLimitBracket") or public_event.get("roundLimitBracket"),
            "playerPoolSize": event_info.get("playerPoolSize") or public_event.get("playerPoolSize"),
            "courts": courts,
            "lastUpdated": int(time.time()),
        },
        "meta": {
                    "serverTime": datetime.now(timezone.utc).isoformat(),
                    "dataFetchedAt": data.get("_fetchedAt"),
                    "aclResponseDate": data.get("_aclResponseDate"),
                    "aclEtag": data.get("_aclEtag"),
                    "eventId": event_id,
                    "notifications": notifications,
                },
        "notifications": notifications,
        "matches": sorted(
            matches,
            key=lambda m: (
                int(m.get("matchId", 0)),
                int(m.get("gameId", 1) or 1),
            )
        )
    }

@app.route("/api/events/<event_id>/bracket")
def api_bracket(event_id: str):
    refresh = request.args.get("refresh", "1") == "1"
    data = load_bracket(event_id, refresh=refresh)
    return jsonify(normalize_tournament(event_id, data, include_stats=False))


@app.route("/api/events/<event_id>/bracket-probabilities")
def api_bracket_probabilities(event_id: str):
    refresh = request.args.get("refresh", "0") == "1"
    simulations = min(max(int(request.args.get("simulations", 10000)), 100), 50000)
    data = load_bracket(event_id, refresh=refresh)
    numeric_event_id = int(event_id)
    if not bracket_roster_ready(data):
        event_info = data.get("eventInfo") or {}
        return jsonify({
            "status": "ROSTER_PENDING",
            "eventId": numeric_event_id,
            "eventName": (
                event_info.get("eventName")
                or event_info.get("leagueName")
                or event_info.get("leaguename")
            ),
            "timelineBuildStatus": "WAITING_FOR_ROSTER",
        })
    with BRACKET_PREDICTION_BUILD_LOCK:
        if numeric_event_id in BRACKET_PREDICTION_BUILDS:
            saved_response = BRACKET_PREDICTION_BUILD_RESPONSES.get(numeric_event_id)
            if saved_response is not None:
                return jsonify(saved_response)
            return bracket_prediction_pending(numeric_event_id, data)
    with season_platform_db() as conn:
        if not has_valid_pregame_snapshot(conn, numeric_event_id):
            start_bracket_prediction_build(numeric_event_id, data, simulations)
            return bracket_prediction_pending(numeric_event_id, data)
        result = bracket_prediction_timeline(
            conn,
            data,
            simulations=simulations,
            data_dir=DATA_DIR,
            max_new_snapshots=0,
        )
    repository = repository_bracket_templates(
        DATA_DIR,
        exclude_event_id=numeric_event_id,
    )
    navigation_template = select_template(repository, data)
    result["liveBracketStructure"] = {
        "status": (
            "VALIDATED_TEMPLATE"
            if navigation_template else "UNAVAILABLE"
        ),
        "templateKey": (
            navigation_template.get("templateKey")
            if navigation_template else None
        ),
        "eventCount": (
            navigation_template.get("eventCount")
            if navigation_template else 0
        ),
        "edgeCoverageRate": (
            navigation_template.get("edgeCoverageRate")
            if navigation_template else None
        ),
        "edges": navigation_template.get("edges", {}) if navigation_template else {},
        "matches": navigation_template.get("matches", {}) if navigation_template else {},
    }
    if result.get("timelineBuildStatus") == "BUILDING":
        with BRACKET_PREDICTION_BUILD_LOCK:
            BRACKET_PREDICTION_BUILD_RESPONSES[numeric_event_id] = result
        start_bracket_prediction_build(numeric_event_id, data, simulations)
    return jsonify(result)


@app.route("/api/prediction-operations/bracket-layouts")
def api_bracket_layouts():
    return jsonify(repository_bracket_templates(DATA_DIR))


@app.route("/api/events/<event_id>/matches")
def api_matches(event_id: str):
    refresh = request.args.get("refresh", "1") == "1"
    include_stats = request.args.get("stats", "0") == "1"
    data = load_bracket(event_id, refresh=refresh)
    return jsonify(normalize_tournament(event_id, data, include_stats=include_stats))


@app.route("/api/events/<event_id>/matches/<match_id>")
def api_match(event_id: str, match_id: str):
    refresh = request.args.get("refresh", "1") == "1"
    game_id = request.args.get("game_id", type=int)
    data = load_bracket(event_id, refresh=refresh)
    pair = get_match_groups(data.get("bracketDetails", [])).get(str(match_id), [])
    item = normalize_match(
        event_id,
        str(match_id),
        pair,
        include_stats=True,
        event_date=prediction_event_date(event_id, data),
    )
    if not item:
        return jsonify({"error": "match not found"}), 404
    if game_id:
        item["games"] = [g for g in item["games"] if g["gameId"] == game_id]
        item["activeGame"] = item["games"][0] if item["games"] else None
    attach_match_profile_trajectories(item)
    return jsonify(item)


@app.route("/api/events/<event_id>/matches/<match_id>/games/<int:game_id>/stats")
def api_match_game_stats(event_id: str, match_id: str, game_id: int):
    refresh = request.args.get("refresh", "1") == "1"
    if refresh:
        maybe_fetch_match_stats(event_id, match_id, game_id, force=True)

    data = load_bracket(event_id, refresh=False)
    pair = get_match_groups(data.get("bracketDetails", [])).get(str(match_id), [])
    item = normalize_match(
        event_id,
        str(match_id),
        pair,
        include_stats=True,
        event_date=prediction_event_date(event_id, data),
    )
    if not item:
        return jsonify({"error": "match not found"}), 404

    item["games"] = [g for g in item["games"] if g["gameId"] == game_id]
    item["activeGame"] = item["games"][0] if item["games"] else None
    if item["activeGame"]:
        item["score"] = item["activeGame"].get("score", item.get("score"))
    attach_match_profile_trajectories(item)

    return jsonify(item)


@app.route("/api/events/<event_id>/live")
def api_live(event_id: str):
    refresh = request.args.get("refresh", "1") == "1"
    data = load_bracket(event_id, refresh=refresh)
    normalized = normalize_tournament(event_id, data, include_stats=True)
    normalized["matches"] = [m for m in normalized["matches"] if m["status"] == "live" or (m.get("courtId") not in ["", "-1", "N/A"] and m.get("activeGame"))]
    return jsonify(normalized)


@app.route("/api/events/<event_id>/standings")
def api_standings(event_id: str):
    data = load_bracket(event_id, refresh=request.args.get("refresh", "1") == "1")
    standings = compute_standings(data.get("bracketDetails", []) or [])
    return jsonify({"eventId": event_id, "standings": standings})


@app.route("/api/events/<event_id>/tournament-stats")
def api_tournament_stats(event_id: str):
    data = load_bracket(event_id, refresh=request.args.get("refresh", "1") == "1")
    cached_only = request.args.get("cached_only", "0") == "1"
    team_id = request.args.get("team_id") or None
    fetch_summary = (
        {
            "targets": len(played_game_stat_targets(data, team_id=team_id)),
            "attempted": 0,
            "failed": 0,
            "authRequired": 0,
            "notifications": [],
            "cachedOnly": True,
        }
        if cached_only else
        ensure_tournament_match_stats(
            event_id,
            data,
            refresh_live=request.args.get("refresh_live", "1") == "1",
            team_id=team_id,
        )
    )
    fetch_summary.update(team_tournament_stat_coverage(event_id, data, team_id))
    consolidate_tournament_stats(event_id, data_dir=DATA_DIR)
    totals_path = os.path.join(DATA_DIR, f"event_{event_id}_player_totals.json")
    highlights_path = os.path.join(DATA_DIR, f"event_{event_id}_highlights.json")
    players = read_json(totals_path, [])
    match_results = derive_tournament_match_results(data)
    if isinstance(players, dict):
        for player_id, stats in players.items():
            stats.update(match_results.get(str(player_id), {
                "match_wins": 0,
                "match_losses": 0,
                "match_ties": 0,
                "match_record": "0-0",
                "finish_place": None,
            }))
    return jsonify({
        "eventId": event_id,
        "players": players,
        "highlights": read_json(highlights_path, {}),
        "matchStats": fetch_summary,
    })

def consolidated_standings_response():
    player_id = int(request.args.get("playerId", "0"))
    seed_event_id = int(request.args.get("seedEventId", "0"))
    start_date = request.args.get("startDate")
    end_date = request.args.get("endDate")
    bucket_id = int(request.args.get("bucketId", "11"))
    exclude_raw = request.args.get("exclude", "")

    if not player_id or not seed_event_id or not start_date or not end_date:
        return {
            "error": "playerId, seedEventId, startDate, and endDate are required"
        }, 400

    excluded_event_ids = {
        int(x)
        for x in exclude_raw.split(",")
        if x.strip().isdigit()
    }

    return build_consolidated_standings(
        SeasonConfig(
            player_id=player_id,
            seed_event_id=seed_event_id,
            start_date=start_date,
            end_date=end_date,
            excluded_event_ids=excluded_event_ids,
            bucket_id=bucket_id,
        )
    )


@app.route("/api/standings/consolidated")
@app.route("/api/season-stats")
def api_consolidated_standings():
    return consolidated_standings_response()


@app.route("/api/season-platform/gather")
def api_season_platform_gather():
    player_ids = parse_player_ids(request.args.get("playerIds") or request.args.get("playerId") or "")
    start_date = request.args.get("startDate")
    end_date = request.args.get("endDate")
    if start_date == "auto":
        start_date = None
    if end_date == "auto":
        end_date = None
    raw_bucket_id = request.args.get("bucketId", "11")
    raw_bucket_ids = request.args.get("bucketIds", "")
    bucket_ids = [
        int(part.strip())
        for part in raw_bucket_ids.split(",")
        if part.strip().isdigit()
    ] or None
    bucket_id = "career" if raw_bucket_id in {"career", "all"} else int(raw_bucket_id)
    mode = request.args.get("mode", "player").lower()

    if not player_ids:
        return jsonify({"error": "playerId/playerIds is required"}), 400
    progress_key = request.args.get("progressKey") or season_progress_key(player_ids, bucket_id, start_date, end_date)
    set_season_progress(progress_key, {
        "stage": "queued",
        "message": "Season stats request started.",
        "coverage": {},
        "done": False,
    })

    def gather() -> dict[str, Any]:
        try:
            result = gather_player_focused_season(
                player_ids=player_ids,
                start_date=start_date,
                end_date=end_date,
                bucket_id=bucket_id,
                bucket_ids=bucket_ids,
                force=request.args.get("force", "0") == "1",
                refresh_index=request.args.get("refreshIndex", "0") == "1",
                include_profiles=request.args.get("profiles", "0") == "1",
                full_event=mode in {"full", "full_event", "tournament"},
                progress_callback=lambda update: set_season_progress(progress_key, {**update, "done": False}),
            )
        except Exception as error:
            set_season_progress(progress_key, {
                "stage": "error",
                "message": str(error),
                "coverage": {},
                "done": True,
                "error": True,
            })
            raise

        with SEASON_GATHER_LOCK:
            SEASON_GATHER_RESULTS[progress_key] = result
        set_season_progress(progress_key, {
            "stage": "complete",
            "message": "Season stats are ready.",
            "coverage": result.get("manifest", {}).get("coverage", {}),
            "done": True,
            "resultReady": True,
        })
        return result

    if request.args.get("background", "0") == "1":
        # Copy request-bound values before the Flask request context ends.
        force = request.args.get("force", "0") == "1"
        refresh_index = request.args.get("refreshIndex", "0") == "1"
        include_profiles = request.args.get("profiles", "0") == "1"
        full_event = mode in {"full", "full_event", "tournament"}

        def background_gather() -> None:
            try:
                result = gather_player_focused_season(
                    player_ids=player_ids,
                    start_date=start_date,
                    end_date=end_date,
                    bucket_id=bucket_id,
                    bucket_ids=bucket_ids,
                    force=force,
                    refresh_index=refresh_index,
                    include_profiles=include_profiles,
                    full_event=full_event,
                    progress_callback=lambda update: set_season_progress(progress_key, {**update, "done": False}),
                )
                with SEASON_GATHER_LOCK:
                    SEASON_GATHER_RESULTS[progress_key] = result
                set_season_progress(progress_key, {
                    "stage": "complete",
                    "message": "Season stats are ready.",
                    "coverage": result.get("manifest", {}).get("coverage", {}),
                    "done": True,
                    "resultReady": True,
                })
            except Exception as error:
                set_season_progress(progress_key, {
                    "stage": "error",
                    "message": str(error),
                    "coverage": {},
                    "done": True,
                    "error": True,
                })

        threading.Thread(target=background_gather, daemon=True, name=f"season-{progress_key}").start()
        return jsonify({"accepted": True, "progressKey": progress_key}), 202

    return jsonify(gather())


@app.route("/api/season-platform/progress")
def api_season_platform_progress():
    key = request.args.get("key", "")
    with SEASON_GATHER_LOCK:
        payload = SEASON_GATHER_PROGRESS.get(key)
        result = SEASON_GATHER_RESULTS.get(key) if payload and payload.get("done") else None
    response = payload or {
        "key": key,
        "stage": "idle",
        "message": "No season load is active for this selection.",
        "coverage": {},
        "done": True,
    }
    if result is not None:
        response = {**response, "result": result}
    return jsonify(response)


@app.route("/api/season-platform/seasons")
def api_season_platform_seasons():
    raw_player_id = request.args.get("playerId")
    if not raw_player_id or not raw_player_id.isdigit():
        return jsonify({"error": "playerId is required"}), 400

    raw_buckets = request.args.get("bucketIds", "")
    bucket_ids = [
        int(part.strip())
        for part in raw_buckets.split(",")
        if part.strip().isdigit()
    ] or None
    result = player_season_options(
        player_id=int(raw_player_id),
        bucket_ids=bucket_ids,
        refresh_index=request.args.get("refreshIndex", "0") == "1",
    )
    return jsonify(result)


@app.route("/api/season-platform/leaderboard")
def api_season_platform_leaderboard():
    filters = {
        "player_ids": parse_player_ids(request.args.get("playerIds") or request.args.get("playerId") or ""),
        "start_date": request.args.get("startDate"),
        "end_date": request.args.get("endDate"),
        "location_id": request.args.get("locationId"),
        "partner_id": request.args.get("partnerId"),
        "opponent_id": request.args.get("opponentId"),
        "court_id": request.args.get("courtId"),
    }
    filters = {key: value for key, value in filters.items() if value not in (None, "", [])}
    return jsonify(leaderboard_from_db(filters))


@app.route("/api/prediction-operations")
def api_prediction_operations():
    with season_platform_db() as conn:
        return jsonify(prediction_operations_snapshot(conn))


@app.route("/api/prediction-operations/live-validation")
def api_live_probability_validation():
    max_games = min(max(int(request.args.get("maxGames", 50)), 1), 250)
    simulations = min(max(int(request.args.get("simulations", 1000)), 100), 5000)
    with season_platform_db() as conn:
        return jsonify(evaluate_live_probability(
            conn,
            max_games=max_games,
            simulations_per_state=simulations,
        ))


@app.route("/api/prediction-operations/first-throw-analysis")
def api_first_throw_analysis():
    max_games = min(max(int(request.args.get("maxGames", 1000)), 1), 5000)
    minimum_player_rounds = min(max(int(request.args.get("minimumPlayerRounds", 20)), 1), 500)
    with season_platform_db() as conn:
        return jsonify(analyze_first_throw(
            conn,
            max_games=max_games,
            minimum_player_rounds=minimum_player_rounds,
        ))


@app.route("/api/predictive-player-profile/<int:player_id>")
def api_predictive_player_profile(player_id: int):
    with season_platform_db() as conn:
        return jsonify(predictive_player_profile(conn, player_id))


@app.route("/api/player-analytics-leaderboard")
def api_player_analytics_leaderboard():
    with season_platform_db() as conn:
        rows = player_analytics_leaderboard(conn)
        snapshot_status = player_analytics_snapshot_status(conn)
    membership_options = sorted({
        str(row.get("membershipName")).strip()
        for row in rows
        if row.get("membershipName")
    })
    classification = request.args.get("classification", "ALL").strip().upper()
    if classification == "PRO":
        rows = [row for row in rows if row.get("isPro")]
    elif classification == "NON_PRO":
        rows = [row for row in rows if not row.get("isPro")]
    membership = request.args.get("membership", "ALL").strip().upper()
    if membership == "UNKNOWN":
        rows = [row for row in rows if not row.get("membershipName")]
    elif membership != "ALL":
        rows = [
            row for row in rows
            if str(row.get("membershipName") or "").strip().upper() == membership
        ]
    sort_key = request.args.get("sort", "currentFormRating")
    allowed = {"currentFormRating", "consistencyRating", "clutchRating", "carryRating", "competitionStrengthRating", "calculatedPpr", "calculatedDpr", "rounds"}
    if sort_key not in allowed:
        sort_key = "currentFormRating"
    rows.sort(key=lambda row: (row.get(sort_key) is not None, row.get(sort_key) or -999), reverse=True)
    limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    return jsonify({
        "sort": sort_key,
        "classification": classification,
        "membership": membership,
        "membershipOptions": membership_options,
        "players": rows[:limit],
        "eligiblePlayers": len(rows),
        "proPlayers": sum(1 for row in rows if row.get("isPro")),
        "snapshot": snapshot_status,
    })


@app.route("/api/prediction-operations/clutch-validation")
def api_clutch_validation():
    with season_platform_db() as conn:
        return jsonify(validate_clutch_rating(conn))


@app.route("/api/prediction-operations/profile-rating-validation")
def api_profile_rating_validation():
    with season_platform_db() as conn:
        return jsonify(validate_profile_ratings(conn))


@app.route("/api/prediction-operations/swing-performance-validation")
def api_swing_performance_validation():
    with season_platform_db() as conn:
        return jsonify(validate_swing_performance(conn))


@app.route("/api/prediction-operations/profile-feature-model-validation")
def api_profile_feature_model_validation():
    with season_platform_db() as conn:
        return jsonify(validate_profile_features_in_matchup_model(conn))


@app.route("/api/matchup-expected-performance", methods=["POST"])
def api_matchup_expected_performance():
    body = request.get_json(silent=True) or {}
    with season_platform_db() as conn:
        return jsonify(matchup_expected_performance(
            conn,
            body.get("sideAPlayerIds") or [],
            body.get("sideBPlayerIds") or [],
            cutoff_at=body.get("cutoffAt"),
        ))


@app.route("/api/prediction-operations/expected-ppr-validation")
def api_expected_ppr_validation():
    with season_platform_db() as conn:
        return jsonify(validate_expected_ppr(conn))


@app.route("/api/prediction-operations/carry-performance-validation")
def api_carry_performance_validation():
    with season_platform_db() as conn:
        return jsonify(validate_carry_performance(conn))


@app.route("/api/events/<int:event_id>/strength-of-schedule")
def api_event_strength_of_schedule(event_id: int):
    with season_platform_db() as conn:
        return jsonify(event_strength_of_schedule(conn, event_id))


@app.route("/api/prediction-operations/opponent-adjustment-validation")
def api_opponent_adjustment_validation():
    with season_platform_db() as conn:
        return jsonify(validate_opponent_adjustment(conn))


@app.route("/api/prediction-weighting-policy")
def api_prediction_weighting_policy():
    return jsonify(prediction_weighting_policy())


@app.route("/api/historical-backfill")
def api_historical_backfill():
    with season_platform_db() as conn:
        return jsonify(historical_backfill_status(conn))


@app.route("/api/payload-archive")
def api_payload_archive():
    with season_platform_db() as conn:
        return jsonify(payload_archive_health(conn))


@app.route("/api/payload-archive/run", methods=["POST"])
def api_payload_archive_run():
    body = request.get_json(silent=True) or {}
    limit = min(max(int(body.get("limit") or 100), 1), 1000)
    with season_platform_db() as conn:
        result = archive_pending_payloads(conn, limit=limit)
        result["health"] = payload_archive_health(conn)
        return jsonify(result)


@app.route("/api/historical-backfill/control", methods=["POST"])
def api_historical_backfill_control():
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip().lower()
    if action not in {"pause", "resume"}:
        return jsonify({"error": "action must be pause or resume"}), 400
    with season_platform_db() as conn:
        lane = str(body.get("lane") or "").strip().upper()
        if lane:
            try:
                return jsonify(set_historical_backfill_lane_paused(
                    conn,
                    lane=lane,
                    paused=action == "pause",
                ))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        return jsonify(set_historical_backfill_paused(
            conn,
            paused=action == "pause",
        ))


@app.route("/api/historical-backfill/venues.csv")
def api_historical_backfill_venue_export():
    with season_platform_db() as conn:
        rows = venue_export_rows(conn)
    output = io.StringIO(newline="")
    fieldnames = [
        "Venue", "Latitude", "Longitude", "City", "State_Province", "Country",
        "Event_Count", "First_Event_Date", "Latest_Event_Date",
        "Complete_Games", "Player_Rounds", "Event_IDs",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                "attachment; filename=cheesebaggers-google-my-maps-venues.csv"
            ),
            "Cache-Control": "no-store",
        },
    )


@app.route("/api/venues")
def api_venues():
    with season_platform_db() as conn:
        venues = venue_catalog(conn)
    return jsonify({"venues": venues})


@app.route("/api/venues/<path:venue_key>/events")
def api_venue_events(venue_key: str):
    season_start = request.args.get("season_start", type=int)
    if season_start is not None:
        start_date, end_date = acl_season_range(season_start)
    else:
        default_year = default_season_start_year()
        default_start, default_end = acl_season_range(default_year)
        start_date = request.args.get("start_date") or default_start
        end_date = request.args.get("end_date") or default_end
    with season_platform_db() as conn:
        try:
            result = venue_event_schedule(
                conn,
                venue_key=venue_key,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
    return jsonify(result)


@app.route("/api/venues/<path:venue_key>/court-ppr")
def api_venue_court_ppr(venue_key: str):
    default_start, default_end = acl_season_range(default_season_start_year())
    start_date = request.args.get("start_date") or default_start
    end_date = request.args.get("end_date") or default_end
    raw_player_ids = request.args.get("player_ids", "")
    try:
        player_ids = [
            int(value)
            for value in raw_player_ids.split(",")
            if value.strip()
        ]
    except ValueError:
        return jsonify({"error": "player_ids must be comma-separated numbers"}), 400
    with season_platform_db() as conn:
        try:
            result = venue_court_ppr(
                conn,
                venue_key=venue_key,
                start_date=start_date,
                end_date=end_date,
                player_ids=player_ids or None,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
    return jsonify(result)


@app.route("/api/venues/<path:venue_key>/priority", methods=["POST"])
def api_prioritize_venue_events(venue_key: str):
    body = request.get_json(silent=True) or {}
    season_start = body.get("seasonStart")
    if season_start is not None:
        start_date, end_date = acl_season_range(int(season_start))
    else:
        default_start, default_end = acl_season_range(default_season_start_year())
        start_date = str(body.get("startDate") or default_start)
        end_date = str(body.get("endDate") or default_end)
    requested_ids = [int(value) for value in body.get("eventIds") or []]
    with season_platform_db() as conn:
        try:
            schedule = venue_event_schedule(
                conn,
                venue_key=venue_key,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        eligible = {
            int(event["eventId"])
            for event in schedule["events"]
            if event["downloadState"] != "FULLY_DOWNLOADED"
        }
        event_ids = (
            [event_id for event_id in requested_ids if event_id in eligible]
            if requested_ids
            else sorted(eligible)
        )
        result = prioritize_events(
            conn,
            event_ids,
            source=f"priority-venue:{venue_key}:{start_date}:{end_date}",
        )
        refreshed = venue_event_schedule(
            conn,
            venue_key=venue_key,
            start_date=start_date,
            end_date=end_date,
        )
    return jsonify({**result, "schedule": refreshed})


@app.route("/api/prediction-operations/run", methods=["POST"])
def api_prediction_operations_run():
    body = request.get_json(silent=True) or {}
    search_params = None
    if body.get("discover", True):
        search_params = {
            "bucket_id": int(body.get("bucketId", 11)),
            "origin_lat": float(body.get("originLat", 26.781990538225305)),
            "origin_lng": float(body.get("originLng", -80.32006282856948)),
            "event_range": float(body.get("eventRange", 10000)),
            "selected_time": str(body.get("selectedTime", "WEEK")),
            "time_range": int(body.get("timeRange", 1)),
            "event_country_code": str(body.get("eventCountryCode", "US")),
        }
    with PREDICTION_LIFECYCLE_LOCK:
        with season_platform_db() as conn:
            result = run_lifecycle_cycle(
                conn,
                search_params=search_params,
                lookahead_minutes=int(body.get("lookaheadMinutes", 1440)),
            )
            return jsonify(result)


@app.route("/api/prediction-operations/monitor", methods=["POST"])
def api_prediction_operations_monitor():
    body = request.get_json(silent=True) or {}
    if not body.get("eventId") or not body.get("format"):
        return jsonify({"error": "eventId and format are required"}), 400
    with season_platform_db() as conn:
        monitor_event(
            conn,
            event_id=body["eventId"],
            schedule_format=body["format"],
            source_timezone=body.get("timezone"),
        )
        return jsonify(prediction_operations_snapshot(conn))


@app.route("/api/swap-live/<event_id>")
def api_swap_live(event_id: str):
    refresh = request.args.get("refresh", "1") == "1"
    errors: list[dict[str, Any]] = []

    def get_part(name: str, endpoint: str) -> Dict[str, Any]:
        try:
            return swap_public_get(event_id, name, endpoint, refresh=refresh)
        except Exception as e:
            errors.append({"endpoint": endpoint, "message": str(e)})
            return read_json(swap_cache_path(event_id, name), {})

    event_payload = get_part("event", "events")
    public_event_data = event_payload.get("data") if isinstance(event_payload.get("data"), dict) else {}
    event_name = str(public_event_data.get("eventName") or public_event_data.get("leagueName") or public_event_data.get("leaguename") or "").lower()
    bracket_type = str(public_event_data.get("bracketType") or public_event_data.get("brackettype") or "").upper()
    use_swiss = bracket_type == "W" or "rounders" in event_name

    if use_swiss:
        schedule_payload = get_part("swiss_schedule", "swiss-pairing-schedule-breakdown")
        standings_payload = get_part("swiss_standings", "swiss-pairing-standings?roundID=0")
        up_next_payload = get_part("swiss_up_next", "swiss-pairing-up-next-players-list?roundID=0")
    else:
        schedule_payload = get_part("schedule", "swap-schedule-breakdown")
        standings_payload = get_part("standings", "swap-standings")
        up_next_payload = get_part("up_next", "swap-up-next-players-list")
    event_stats_payload = get_part("event_stats", "event-player-stats")

    schedule_data = schedule_payload.get("data") or {}
    event_data = schedule_data.get("eventInfo") or event_payload.get("data") or {}
    if use_swiss:
        leaderboard = [
            player
            for row in standings_payload.get("data", []) or []
            if isinstance(row, dict)
            for player in safe_team_standing_players(row)
        ]
        up_next_players = [
            player
            for row in up_next_payload.get("data", []) or []
            if isinstance(row, dict)
            for player in (safe_team_standing_players(row) or [safe_swap_player(row)])
        ]
    else:
        leaderboard = [
            safe_swap_player(row)
            for row in standings_payload.get("data", []) or []
            if isinstance(row, dict)
        ]
        up_next_players = [
            safe_swap_player(row)
            for row in up_next_payload.get("data", []) or []
            if isinstance(row, dict)
        ]
    event_player_stats = {
        int(stat["playerId"]): stat
        for stat in [
            safe_swap_event_player_stat(row)
            for row in event_stats_payload.get("data", []) or []
            if isinstance(row, dict)
        ]
        if str(stat.get("playerId") or "").isdigit()
    }
    schedule_rows = []
    for key in ("overAllSchedule", "inProgressMatchList", "availableMatchList"):
        schedule_rows.extend(row for row in schedule_data.get(key, []) or [] if isinstance(row, dict))
    seen_matches: set[tuple[str, str]] = set()
    matches = []
    for row in schedule_rows:
        match_key = (str(row.get("matchID")), str(row.get("gameID") or 1))
        if match_key in seen_matches:
            continue
        seen_matches.add(match_key)
        matches.append(safe_swap_match(row))

    match_ids = [
        int(match.get("matchId"))
        for match in matches
        if str(match.get("matchId") or "").isdigit()
    ]
    max_match_id = max(match_ids, default=0)
    for match_id in range(1, max_match_id + 1):
        if load_game_stats(event_id, str(match_id), 1):
            continue
        try:
            maybe_fetch_match_stats(event_id, str(match_id), 1, force=False)
        except Exception as e:
            errors.append({"endpoint": "match-stats-backfill", "matchId": match_id, "message": str(e)})

    for match in matches:
        match_id = match.get("matchId")
        if not match_id:
            continue
        try:
            should_refresh_current = match.get("status") == "live" and refresh
            maybe_fetch_match_stats(
                event_id,
                str(match_id),
                1,
                force=should_refresh_current,
                refresh_completed=should_refresh_current,
            )
            stats = load_game_stats(event_id, str(match_id), 1)
            if not isinstance(stats, dict):
                continue
            safe_stats = safe_swap_match_stats(stats)
            match["stats"] = safe_stats
            match["homeScore"] = safe_stats.get("homeScore", match.get("homeScore"))
            match["awayScore"] = safe_stats.get("awayScore", match.get("awayScore"))
        except Exception as e:
            errors.append({"endpoint": "match-stats", "matchId": match_id, "message": str(e)})

    player_totals: dict[int, dict[str, Any]] = defaultdict(empty_swap_player_totals)
    stats_prefix = f"event_{event_id}_match_"
    stats_suffix = "_game_1_stats.json"
    for filename in os.listdir(DATA_DIR):
        if not filename.startswith(stats_prefix) or not filename.endswith(stats_suffix):
            continue
        stats = read_json(os.path.join(DATA_DIR, filename), {})
        if not isinstance(stats, dict):
            continue
        safe_stats = safe_swap_match_stats(stats)
        for player_stat in safe_stats.get("players", []) or []:
            player_id = player_stat.get("playerId")
            if not str(player_id or "").isdigit():
                continue
            totals = player_totals[int(player_id)]
            totals["rounds"] += int(player_stat.get("rounds") or 0)
            totals["points"] += int(player_stat.get("points") or 0)
            totals["opponentPoints"] += as_float(player_stat.get("oppPpr")) * int(player_stat.get("rounds") or 0)
            totals["fourBaggers"] += int(player_stat.get("fourBaggers") or 0)
            totals["bagsThrown"] += int(player_stat.get("bagsThrown") or 0)

    player_ids = sorted({
        int(player["playerId"])
        for player in leaderboard
        if str(player.get("playerId") or "").isdigit()
    })
    if player_ids:
        try:
            season_rows = leaderboard_from_db({"player_ids": player_ids}).get("leaderboard", [])
            season_by_player = {int(row["player_id"]): row for row in season_rows}
            for player in leaderboard:
                if not str(player.get("playerId") or "").isdigit():
                    continue
                season = season_by_player.get(int(player["playerId"]))
                if season:
                    player["season"] = {
                        "events": season.get("events_played"),
                        "games": season.get("games_played"),
                        "rounds": season.get("rounds_thrown"),
                        "ppr": season.get("ppr"),
                        "dpr": season.get("dpr"),
                        "oppPpr": season.get("opp_ppr"),
                        "fourBaggerPct": season.get("four_bagger_pct"),
                    }
        except Exception as e:
            errors.append({"endpoint": "season-comparison", "message": str(e)})

    for player in leaderboard:
        player_id = player.get("playerId")
        if not str(player_id or "").isdigit():
            continue
        totals = player_totals.get(int(player_id))
        official_stats = event_player_stats.get(int(player_id))
        if official_stats:
            player["swapStats"] = official_stats
            continue
        if not totals:
            continue
        rounds = totals["rounds"]
        player["swapStats"] = {
            "rounds": rounds,
            "points": totals["points"],
            "ppr": round(totals["points"] / rounds, 2) if rounds else None,
            "dpr": round((totals["points"] - totals["opponentPoints"]) / rounds, 2) if rounds else None,
            "fourBaggers": totals["fourBaggers"],
            "fourBaggerPct": round(totals["fourBaggers"] * 100 / rounds, 2) if rounds else None,
            "bagsThrown": totals["bagsThrown"],
        }

    live = [match for match in matches if match["status"] == "live"]
    next_matches = [match for match in matches if match["status"] == "next"]
    completed = [match for match in matches if match["status"] == "completed"]
    return jsonify({
        "event": safe_swap_event(event_data),
        "leaderboard": leaderboard,
        "matches": {
            "all": matches,
            "live": live,
            "next": next_matches,
            "completed": completed,
        },
        "upNextPlayers": up_next_players,
        "counts": {
            "leaderboard": len(leaderboard),
            "upNextPlayers": len(up_next_players),
            "scheduleMatches": len(matches),
            "live": len(live),
            "next": len(next_matches),
            "completed": len(completed),
        },
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "errors": errors,
            "sources": {
                "event": "events",
                "schedule": "swiss-pairing-schedule-breakdown" if use_swiss else "swap-schedule-breakdown",
                "standings": "swiss-pairing-standings" if use_swiss else "swap-standings",
                "upNext": "swiss-pairing-up-next-players-list" if use_swiss else "swap-up-next-players-list",
                "eventStats": "event-player-stats",
            },
        },
    })


@app.route("/api/raw/events/<event_id>")
def api_raw_event(event_id: str):
    data = load_bracket(event_id, refresh=request.args.get("refresh", "1") == "1")
    return jsonify(data)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path: str):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    index_path = os.path.join(app.static_folder, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, "index.html")
    return jsonify({"message": "Frontend not built. Run npm install && npm run build in frontend/.", "api": "/api/events/<event_id>/matches"})

@app.route("/api/player/<int:player_id>/compare")

def api_player_compare(player_id):
    bucket_id = int(request.args.get("bucket_id", 11))

    url = "https://api.iplayacl.com/api/v1/player-compare-stats"

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://app.iplayacl.com",
        "referer": "https://app.iplayacl.com/",
        "user-agent": "Mozilla/5.0",
        "x-app-version": "14.1.0",
    }

    payload = {
        "playerIDs": [player_id],
        "bucketID": bucket_id,
    }

    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()
    raw = r.json()

    player = (raw.get("data") or [{}])[0]

    return jsonify({
        "playerId": player.get("playerID"),
        "name": f"{player.get('playerFirstName', '')} {player.get('playerLastName', '')}".strip(),
        "photo": player.get("playerPhoto"),
        "skillLevel": player.get("playerSkillLevel"),
        "bucketId": player.get("bucketID"),
        "year": player.get("yearDesc"),
        "ppr": player.get("ptsPerRnd"),
        "dpr": player.get("DPR"),
        "oppPpr": player.get("OppPtsPerRnd"),
        "bags": {
            "total": player.get("bagsTotal"),
            "in": player.get("bagsInTotal"),
            "inPct": player.get("bagsInPct"),
            "on": player.get("bagsOnTotal"),
            "onPct": player.get("bagsOnPct"),
            "off": player.get("bagsOffTotal"),
            "offPct": player.get("bagsOffPct"),
        },
        "fourBaggers": {
            "total": player.get("fourBaggersTotal"),
            "pct": player.get("fourBagPct"),
        },
        "rounds": {
            "total": player.get("rdsTotal"),
            "won": player.get("rdsWonTotal"),
            "wonPct": player.get("roundsWonPct"),
            "lost": player.get("rdsLostTotal"),
            "lostPct": player.get("roundsLostPct"),
            "tied": player.get("rdsTiedTotal"),
            "tiedPct": player.get("roundsTiedPct"),
        },
        "points": {
            "total": player.get("totPtsTotal"),
            "opponent": player.get("oppPtsTotal"),
        },
        "raw": player,
    })

@app.route("/api/player/<int:player_id>/events")
def api_player_events(player_id):
    bucket_id = int(request.args.get("bucket_id", 11))
    event_status = request.args.get("eventStatus", "COMPLETED").upper()

    url = (
        f"https://api.iplayacl.com/api/v1/player-events-grouped/"
        f"{player_id}?bucket_id={bucket_id}&eventStatus={event_status}"
    )

    headers = {
        "accept": "application/json, text/plain, */*",
        "origin": "https://fanzone.iplayacl.com",
        "referer": "https://fanzone.iplayacl.com/",
        "user-agent": "Mozilla/5.0",
    }

    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    raw = r.json()

    events = []
    for e in raw.get("eventsGrouped", []) or []:
        events.append({
            "eventId": e.get("leagueID"),
            "name": e.get("leagueName"),
            "date": e.get("leaguestartdate"),
            "time": e.get("leagueTime"),
            "status": e.get("leagueStatus"),
            "location": {
                "name": e.get("leagueLocationName"),
                "city": e.get("locationCity"),
                "state": e.get("locationState"),
            },
            "matchType": e.get("matchType"),
            "bracketType": e.get("bracketType"),
            "blindDraw": bool(e.get("blindDraw")),
            "eventType": e.get("eventType"),
            "eventSubType": e.get("eventSubType"),
            "scheduleCount": e.get("scheduleCount"),
            "bracketStarted": bool(e.get("bracketStarted")),
            "admin": {
                "id": e.get("adminID"),
                "name": f"{e.get('adminFirstName', '')} {e.get('adminLastName', '')}".strip(),
            },
            "raw": e,
        })

    return jsonify({
        "playerId": player_id,
        "bucketId": bucket_id,
        "eventStatus": event_status,
        "count": len(events),
        "events": events,
        "raw": raw,
    })
    
@app.route("/api/player/<int:player_id>/active-events")
def api_player_active_events(player_id):
    bucket_id = int(request.args.get("bucket_id", 11))
    return api_player_events(player_id)
    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    start_prediction_lifecycle_worker()
    start_historical_backfill_worker()
    start_payload_archive_worker(season_platform_db)
    start_player_analytics_snapshot_worker(season_platform_db)
    app.run(host="0.0.0.0", port=port, debug=debug)
