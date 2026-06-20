import json
import os
import shutil
import tempfile
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

import requests
from filelock import FileLock
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from consolidate_tournament_stats import consolidate_tournament_stats
from match_stats_downloader import fetch_and_save_match_stats
from standings import compute_standings
from season_standings import SeasonConfig, build_consolidated_standings


app = Flask(__name__, static_folder="../frontend/dist", static_url_path="")
CORS(app)

DATA_DIR = os.environ.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Keep the existing ACL request behavior. Override from env when your cookie changes.
ACL_SESSION_COOKIE = os.environ.get(
    "ACL_SESSION_COOKIE",
    "connect.sid=s%3A2ZwZdDKGjb_ah_Rhfy1B_Bw92ttJj9jA.SjKAaL1%2FqfjAQ4YRlgaVPezy0vYeswcKhPDy4EIq0Fw; _gid=GA1.2.919253870.1748034241; _gat=1; _ga_083S5K2NVN=GS2.1.s1748034240$o146$g1$t1748034250$j0$l0$h0; _ga=GA1.1.238443575.1732375452",
)


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
                    print(f"✅ JSON updated safely for event {event_id}")
                except ValueError as e:
                    print(f"❌ Invalid JSON received: {e}")
            else:
                print(f"⚠️ Failed to fetch JSON: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching JSON for event {event_id}: {e}")


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_bracket(event_id: str, refresh: bool = True) -> Dict[str, Any]:
    if refresh:
        fetch_updated_json(event_id)
    path = os.path.join(DATA_DIR, f"event_{event_id}.json")
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


def load_game_stats(event_id: str, match_id: str, game_id: int) -> Optional[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, f"event_{event_id}_match_{match_id}_game_{game_id}_stats.json")
    data = read_json(path)
    return data if isinstance(data, dict) else None


def maybe_fetch_match_stats(event_id: str, match_id: str, game_id: int, force: bool = False) -> None:
    fetch_and_save_match_stats(event_id, [int(match_id)], game_id=game_id, session_cookie=ACL_SESSION_COOKIE, force=force)


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
        print(f"⚠️ Failed to fetch player season stats: {e}")
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
    return rounds


def normalize_match(event_id: str, match_id: str, pair: List[Dict[str, Any]], include_stats: bool = True) -> Optional[Dict[str, Any]]:
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
        if include_stats and (g.get("matchStatusID") == 0 or not stats):
            try:
                maybe_fetch_match_stats(event_id, match_id, gid, force=(g.get("matchStatusID") == 0))
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
        })
    status_id = top.get("matchStatusID")
    active_game = next((g for g in games if g.get("statusId") == 0), games[-1] if games else None)
    return {
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


def normalize_tournament(event_id: str, data: Dict[str, Any], include_stats: bool = False) -> Dict[str, Any]:
    matches_raw = data.get("bracketDetails", []) or []
    groups = get_match_groups(matches_raw)

    matches = []

    for mid, pair in groups.items():
        item = normalize_match(event_id, mid, pair, include_stats=include_stats)
        if item:
            matches.append(item)

    if include_stats:
        bucket_id = int(request.args.get("bucket_id", 11))
        matches = enrich_matches_with_season_stats(matches, bucket_id=bucket_id)

    matches = flatten_matches_by_game(matches)

    event_info = data.get("eventInfo", {}) or {}
    court_order = event_info.get("courtTotalDetails", "")
    courts = [c.strip() for c in str(court_order).split(",") if c.strip()]

    return {
        "event": {
            "id": event_id,
            "name": event_info.get("leagueName") or event_info.get("eventName") or event_info.get("leaguename") or f"Event {event_id}",
            "courts": courts,
            "lastUpdated": int(time.time()),
        },
        "meta": {
                    "serverTime": datetime.now(timezone.utc).isoformat(),
                    "dataFetchedAt": data.get("_fetchedAt"),
                    "aclResponseDate": data.get("_aclResponseDate"),
                    "aclEtag": data.get("_aclEtag"),
                    "eventId": event_id,
                },
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
    item = normalize_match(event_id, str(match_id), pair, include_stats=True)
    if not item:
        return jsonify({"error": "match not found"}), 404
    if game_id:
        item["games"] = [g for g in item["games"] if g["gameId"] == game_id]
        item["activeGame"] = item["games"][0] if item["games"] else None
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
    consolidate_tournament_stats(event_id)
    totals_path = os.path.join(DATA_DIR, f"event_{event_id}_player_totals.json")
    highlights_path = os.path.join(DATA_DIR, f"event_{event_id}_highlights.json")
    return jsonify({
        "eventId": event_id,
        "players": read_json(totals_path, []),
        "highlights": read_json(highlights_path, {}),
    })

@app.route("/api/standings/consolidated")
def api_consolidated_standings():
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
    app.run(host="0.0.0.0", port=port, debug=True)
