from __future__ import annotations

import glob
import json
import os
import threading
import time
from collections import Counter, defaultdict
from typing import Any


_REPOSITORY_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_REPOSITORY_CACHE_LOCK = threading.Lock()
_REPOSITORY_CACHE_SECONDS = 300


def infer_bracket_layout(payload: dict[str, Any]) -> dict[str, Any] | None:
    details = payload.get("bracketDetails") or []
    matches = _matches(details)
    teams = {
        slot["teamId"]
        for match in matches.values()
        for slot in match["slots"].values()
        if slot.get("teamId")
    }
    if len(teams) < 2:
        return None
    team_paths: dict[str, list[int]] = defaultdict(list)
    for match_id in sorted(matches):
        for slot in matches[match_id]["slots"].values():
            if slot.get("teamId"):
                team_paths[slot["teamId"]].append(match_id)
    edges: dict[str, dict[str, Any]] = {}
    for match_id, match in matches.items():
        winner = match.get("winnerTeamId")
        loser = match.get("loserTeamId")
        for outcome, team_id in (("W", winner), ("L", loser)):
            if not team_id:
                continue
            next_matches = [
                candidate for candidate in team_paths.get(team_id, [])
                if candidate > match_id
            ]
            if not next_matches:
                continue
            destination = min(next_matches)
            destination_position = next(
                (
                    position
                    for position, slot in matches[destination]["slots"].items()
                    if slot.get("teamId") == team_id
                ),
                None,
            )
            if destination_position:
                edges[f"{match_id}:{outcome}"] = {
                    "matchId": destination,
                    "position": destination_position,
                }
    info = payload.get("eventInfo") or {}
    bracket_type = str(
        info.get("bracketType")
        or info.get("brackettype")
        or "UNKNOWN"
    ).upper()
    side_signature = ",".join(sorted({
        str(match.get("bracketSide") or "UNKNOWN").upper()
        for match in matches.values()
    }))
    return {
        "eventId": int(info.get("eventID") or info.get("leagueID") or 0),
        "teamCount": len(teams),
        "bracketType": bracket_type,
        "sideSignature": side_signature,
        "templateKey": f"{len(teams)}:{bracket_type}:{side_signature}",
        "matchCount": len(matches),
        "matches": {
            str(match_id): {
                "roundDescription": match["roundDescription"],
                "bracketSide": match["bracketSide"],
            }
            for match_id, match in matches.items()
        },
        "edges": edges,
    }


def repository_bracket_templates(
    data_dir: str,
    *,
    minimum_events: int = 2,
    minimum_consistency: float = 0.9,
    exclude_event_id: int | None = None,
) -> dict[str, Any]:
    cache_key = (
        os.path.abspath(data_dir), minimum_events, minimum_consistency,
        int(exclude_event_id) if exclude_event_id is not None else None,
    )
    now = time.monotonic()
    with _REPOSITORY_CACHE_LOCK:
        cached = _REPOSITORY_CACHE.get(cache_key)
        if cached and now - cached[0] < _REPOSITORY_CACHE_SECONDS:
            return cached[1]
    layouts = []
    for path in glob.glob(os.path.join(data_dir, "event_*.json")):
        try:
            with open(path, "r", encoding="utf-8") as source:
                payload = json.load(source)
        except (OSError, ValueError, TypeError):
            continue
        layout = infer_bracket_layout(payload)
        if not layout or (
            exclude_event_id is not None
            and int(layout["eventId"]) == int(exclude_event_id)
        ):
            continue
        if not layout["edges"]:
            continue
        layouts.append(layout)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for layout in layouts:
        grouped[layout["templateKey"]].append(layout)
    templates = {}
    for key, events in grouped.items():
        edge_votes: dict[str, Counter[tuple[int, str]]] = defaultdict(Counter)
        edge_opportunities: Counter[str] = Counter()
        match_votes: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
        for event in events:
            for edge_key, destination in event["edges"].items():
                edge_opportunities[edge_key] += 1
                edge_votes[edge_key][(
                    int(destination["matchId"]),
                    str(destination["position"]),
                )] += 1
            for match_id, metadata in event["matches"].items():
                match_votes[match_id][(
                    str(metadata["roundDescription"]),
                    str(metadata["bracketSide"]),
                )] += 1
        consensus_edges = {}
        rejected_edges = {}
        for edge_key, votes in edge_votes.items():
            destination, count = votes.most_common(1)[0]
            consistency = count / edge_opportunities[edge_key]
            record = {
                "matchId": destination[0],
                "position": destination[1],
                "observations": count,
                "opportunities": edge_opportunities[edge_key],
                "consistency": round(consistency, 4),
            }
            if count >= minimum_events and consistency >= minimum_consistency:
                consensus_edges[edge_key] = record
            else:
                rejected_edges[edge_key] = record
        representative = events[0]
        templates[key] = {
            "templateKey": key,
            "teamCount": representative["teamCount"],
            "bracketType": representative["bracketType"],
            "sideSignature": representative["sideSignature"],
            "eventCount": len(events),
            "eventIds": sorted(event["eventId"] for event in events),
            "matchCountModes": Counter(
                event["matchCount"] for event in events
            ).most_common(),
            "matches": {
                match_id: {
                    "roundDescription": vote.most_common(1)[0][0][0],
                    "bracketSide": vote.most_common(1)[0][0][1],
                    "observations": vote.most_common(1)[0][1],
                }
                for match_id, vote in match_votes.items()
            },
            "edges": consensus_edges,
            "rejectedEdges": rejected_edges,
            "edgeCoverageRate": round(
                len(consensus_edges) / len(edge_votes), 4
            ) if edge_votes else 0,
            "status": (
                "VALIDATED_TEMPLATE"
                if len(events) >= minimum_events and consensus_edges
                else "INSUFFICIENT_REPLICATION"
            ),
        }
    result = {
        "status": "COMPLETE",
        "sourceLayouts": len(layouts),
        "templateCount": len(templates),
        "validatedTemplateCount": sum(
            template["status"] == "VALIDATED_TEMPLATE"
            for template in templates.values()
        ),
        "minimumEvents": minimum_events,
        "minimumConsistency": minimum_consistency,
        "templates": templates,
    }
    with _REPOSITORY_CACHE_LOCK:
        _REPOSITORY_CACHE[cache_key] = (time.monotonic(), result)
    return result


def select_template(
    repository: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    layout = infer_bracket_layout(payload)
    if not layout:
        return None
    exact = repository.get("templates", {}).get(layout["templateKey"])
    if exact and exact["status"] == "VALIDATED_TEMPLATE":
        return exact
    candidates = [
        template
        for template in repository.get("templates", {}).values()
        if template["status"] == "VALIDATED_TEMPLATE"
        and template["teamCount"] == layout["teamCount"]
        and template["bracketType"] == layout["bracketType"]
    ]
    return max(candidates, key=lambda row: row["eventCount"], default=None)


def _matches(details: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    matches: dict[int, dict[str, Any]] = {}
    for row in details:
        if not isinstance(row, dict):
            continue
        try:
            match_id = int(row.get("bracketmatchid"))
        except (TypeError, ValueError):
            continue
        position_text = str(row.get("bracketpos") or "").upper()
        position = "T" if "T" in position_text else "B" if "B" in position_text else None
        if not position:
            continue
        match = matches.setdefault(match_id, {
            "roundDescription": row.get("rounddesc") or "Match",
            "bracketSide": row.get("bracketside") or "",
            "slots": {},
            "winnerTeamId": None,
            "loserTeamId": None,
        })
        team_id = (
            str(row.get("bracketteamid"))
            if row.get("bracketteamid") not in (None, "")
            else None
        )
        match["slots"][position] = {"teamId": team_id}
        scores = row.get("scores") or []
        if scores and isinstance(scores[0], dict):
            try:
                home = int(scores[0].get("scorehome"))
                away = int(scores[0].get("scoreaway"))
            except (TypeError, ValueError):
                continue
            other_position = "B" if position == "T" else "T"
            other = match["slots"].get(other_position, {}).get("teamId")
            if team_id and other and home != away:
                if position == "T":
                    match["winnerTeamId"] = team_id if home > away else other
                    match["loserTeamId"] = other if home > away else team_id
                else:
                    match["winnerTeamId"] = other if home > away else team_id
                    match["loserTeamId"] = team_id if home > away else other
    return matches
