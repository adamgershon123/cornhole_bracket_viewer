from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import requests


ACL_BASE = "https://api.iplayacl.com/api/v1"


@dataclass
class SeasonConfig:
    player_id: int
    seed_event_id: int
    start_date: str
    end_date: str
    excluded_event_ids: set[int]
    bucket_id: int = 11


def acl_get(path: str) -> dict[str, Any]:
    response = requests.get(f"{ACL_BASE}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def parse_event_detail(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or payload

    return {
        "eventId": int(data.get("eventID") or data.get("leagueID") or data.get("eventId")),
        "eventName": data.get("eventName") or data.get("leagueName") or data.get("name"),
        "date": data.get("startdate") or data.get("leagueStartDate") or data.get("date"),
        "locationId": data.get("leagueLocationID"),
        "locationName": data.get("leagueLocationName") or data.get("locationName"),
        "bucketId": data.get("eventBucketID") or data.get("bucketID"),
        "teamCount": data.get("teamCount"),
        "raw": data,
    }


def parse_player_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventId": int(
            row.get("eventId")
            or row.get("eventID")
            or row.get("leagueID")
            or row.get("leagueid")
        ),
        "eventName": (
            row.get("name")
            or row.get("eventName")
            or row.get("leagueName")
            or row.get("leaguename")
        ),
        "date": (
            row.get("date")
            or row.get("startdate")
            or row.get("leagueStartDate")
            or row.get("leaguestartdate")
        ),
        "locationName": (
            row.get("leagueLocationName")
            or row.get("locationName")
            or (
                (row.get("location") or {}).get("name")
                if isinstance(row.get("location"), dict)
                else None
            )
        ),
        "raw": row,
    }

def get_event_details(event_id: int) -> dict[str, Any]:
    return parse_event_detail(acl_get(f"/events/{event_id}"))


def get_player_events(player_id: int, bucket_id: int, status: str) -> list[dict[str, Any]]:
    payload = acl_get(
        f"/player-events-grouped/{player_id}"
        f"?bucket_id={bucket_id}&eventStatus={status}"
    )

    print("PLAYER EVENTS RAW KEYS:", payload.keys())
    print("PLAYER EVENTS RAW SAMPLE:", str(payload)[:1000])

    events = (
    payload.get("eventsGrouped")
    or payload.get("events")
    or payload.get("data")
    or []
)
    return [parse_player_event(e) for e in events]


def get_player_completed_events(player_id: int, bucket_id: int) -> list[dict[str, Any]]:
    events = []

    for status in ["ACTIVE", "COMPLETED"]:
        try:
            batch = get_player_events(player_id, bucket_id, status)
            print(f"{status} EVENTS COUNT:", len(batch))
            events.extend(batch)
        except Exception as e:
            print(f"{status} EVENTS FAILED:", e)

    seen = set()
    deduped = []

    for event in events:
        event_id = event.get("eventId")
        if event_id and event_id not in seen:
            seen.add(event_id)
            deduped.append(event)

    return deduped


def get_candidate_events(config: SeasonConfig, seed_event: dict[str, Any]) -> list[dict[str, Any]]:
    player_events = get_player_completed_events(config.player_id, config.bucket_id)
    print("PLAYER EVENTS COUNT:", len(player_events))
    print("FIRST 5 PLAYER EVENTS:", player_events[:5])
    print("SEED LOCATION:", seed_event.get("locationId"), seed_event.get("locationName"))

    candidates: list[dict[str, Any]] = []

    for event in player_events:
        event_id = int(event["eventId"])

        if event_id in config.excluded_event_ids:
            continue

        event_date = event.get("date")
        if not event_date:
            continue

        if not (config.start_date <= event_date <= config.end_date):
            continue

        try:
            detail = get_event_details(event_id)
        except Exception:
            continue

        if detail.get("locationId") != seed_event.get("locationId"):
            continue

        candidates.append(detail)

    candidates.sort(key=lambda e: e.get("date") or "")
    return candidates


def get_event_standings(event_id: int) -> list[dict[str, Any]]:
    try:
        payload = acl_get(f"/event-standings/{event_id}")

        if payload.get("status") == "ERROR":
            print(f"STANDINGS ERROR {event_id}: {payload.get('message')}")
            return []

        rows = payload.get("data") or []
        print(f"STANDINGS FOUND: event {event_id}, rows={len(rows)}")
        return rows

    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        print(f"STANDINGS SKIPPED: event {event_id} HTTP {status}")
        return []
        
        
def normalize_player(player: dict[str, Any]) -> dict[str, Any]:
    player_id = (
        player.get("playerId")
        or player.get("playerID")
        or player.get("fldPlayerID")
        or player.get("id")
    )

    first = player.get("firstName") or player.get("playerFirstName") or ""
    last = player.get("lastName") or player.get("playerLastName") or ""

    name = (
        player.get("name")
        or player.get("playerName")
        or f"{first} {last}".strip()
        or f"Player {player_id}"
    )

    return {
        "playerId": int(player_id),
        "name": name,
    }


def normalize_standing_row(row: dict[str, Any]) -> dict[str, Any]:
    player_id = row.get("fldPlayerID") or row.get("playerID")
    first = row.get("fldPlayerFirstName") or ""
    last = row.get("fldPlayerLastname") or ""

    return {
        "place": int(row.get("fldEventRank") or 0),
        "position": int(row.get("fldEventPos") or 0),
        "points": float(row.get("fldEventWeekPoints") or 0),
        "teamId": row.get("fldTeamID"),
        "teamName": row.get("fldTeamName"),
        "wins": int(row.get("wins") or 0),
        "losses": int(row.get("losses") or 0),
        "playerPPR": float(row.get("playerPPR") or 0),
        "players": [
            {
                "playerId": int(player_id),
                "name": f"{first} {last}".strip() or f"Player {player_id}",
            }
        ],
        "raw": row,
    }

def build_consolidated_standings(config: SeasonConfig) -> dict[str, Any]:
    seed_event = get_event_details(config.seed_event_id)
    included_events = get_candidate_events(config, seed_event)

    players: dict[int, dict[str, Any]] = {}
    focused_player_id = config.player_id
    partner_history: dict[int, dict[str, Any]] = {}
    
    for event in included_events:
        event_id = int(event["eventId"])
        skipped_events = []
        raw_rows = get_event_standings(event_id)
        if not raw_rows:
            skipped_events.append({
                "eventId": event_id,
                "eventName": event.get("eventName"),
                "date": event.get("date"),
                "reason": "No standings returned",
            })
            continue
        rows = [normalize_standing_row(row) for row in raw_rows]
        teams_by_id: dict[Any, list[dict[str, Any]]] = {}

        for row in rows:
            team_id = row.get("teamId")
            if team_id is None:
                continue
            teams_by_id.setdefault(team_id, []).append(row)
        for row in rows:
            place = row["place"]
            points = row["points"]
            team_players = row["players"]

            for player in team_players:
                player_id = player["playerId"]

                if player_id not in players:
                    players[player_id] = {
                        "playerId": player_id,
                        "name": player["name"],
                        "eventsPlayed": 0,
                        "totalPoints": 0,
                        "averagePoints": 0,
                        "bestFinish": None,
                        "placements": [],
                        "eventResults": [],
                    }

                record = players[player_id]
                record["eventsPlayed"] += 1
                record["totalPoints"] += points
                record["placements"].append(place)

                if record["bestFinish"] is None or place < record["bestFinish"]:
                    record["bestFinish"] = place

                team_id = row.get("teamId")
                team_rows = teams_by_id.get(team_id, [])

                partners = [
                    tr["players"][0]
                    for tr in team_rows
                    if tr["players"] and tr["players"][0]["playerId"] != player_id
                ]
                record["eventResults"].append({
                        "eventId": event_id,
                        "eventName": event.get("eventName"),
                        "date": event.get("date"),
                        "place": place,
                        "points": points,
                        "teamId": team_id,
                        "teamName": row.get("teamName"),
                        "wins": row.get("wins"),
                        "losses": row.get("losses"),
                        "playerPPR": row.get("playerPPR"),
                        "partners": partners,
                    })
                if player_id == focused_player_id:
                    for partner in partners:
                        partner_id = partner["playerId"]

                        if partner_id not in partner_history:
                            partner_history[partner_id] = {
                                "partnerId": partner_id,
                                "partnerName": partner["name"],
                                "eventsTogether": 0,
                                "eventIds": [],
                                "totalPointsTogether": 0,
                                "bestFinishTogether": None,
                                "results": [],
                            }

                        ph = partner_history[partner_id]
                        ph["eventsTogether"] += 1
                        ph["eventIds"].append(event_id)
                        ph["totalPointsTogether"] += points

                        if ph["bestFinishTogether"] is None or place < ph["bestFinishTogether"]:
                            ph["bestFinishTogether"] = place

                        ph["results"].append({
                            "eventId": event_id,
                            "eventName": event.get("eventName"),
                            "date": event.get("date"),
                            "place": place,
                            "points": points,
                            "teamId": team_id,
                            "wins": row.get("wins"),
                            "losses": row.get("losses"),
                        })
    standings = list(players.values())

    for record in standings:
        if record["eventsPlayed"]:
            record["averagePoints"] = round(
                record["totalPoints"] / record["eventsPlayed"],
                2,
            )

    standings.sort(
        key=lambda r: (
            -r["totalPoints"],
            r["bestFinish"] or 999,
            -r["eventsPlayed"],
            r["name"],
        )
    )

    return {
        "season": {
            "playerId": config.player_id,
            "seedEventId": config.seed_event_id,
            "locationId": seed_event.get("locationId"),
            "locationName": seed_event.get("locationName"),
            "startDate": config.start_date,
            "endDate": config.end_date,
            "includedEventCount": len(included_events),
            "excludedEventIds": sorted(config.excluded_event_ids),
            "includedEvents": [
                {
                    "eventId": e.get("eventId"),
                    "eventName": e.get("eventName"),
                    "date": e.get("date"),
                    "teamCount": e.get("teamCount"),
                }
                for e in included_events
            ],
        },
        "standings": standings,
        "skippedEvents": skipped_events,
    }