from __future__ import annotations

import random
import sqlite3
import math
from datetime import datetime, timezone
from typing import Any

from baseline_predictions import score_matchup
from bracket_templates import repository_bracket_templates, select_template
from stage_a_features import build_side_features
from tournament_reforecast import checkpoint_team_form
from double_dip_analysis import double_dip_baseline


def simulate_bracket(
    conn: sqlite3.Connection,
    bracket: dict[str, Any],
    *,
    simulations: int = 10_000,
    data_dir: str | None = None,
    eligible_team_ids: set[str] | None = None,
    completed_match_ids: list[str | int] | None = None,
) -> dict[str, Any]:
    event_info = bracket.get("eventInfo") or {}
    event_id = int(
        event_info.get("eventID")
        or event_info.get("leagueID")
        or 0
    )
    event_date = str(
        event_info.get("startdate")
        or event_info.get("leagueStartDate")
        or event_info.get("leaguestartdate")
        or ""
    )[:10]
    if not event_id or not event_date:
        return {
            "status": "BLOCKED_MISSING_EVENT_ID_OR_DATE",
            "eventId": event_id or None,
        }
    teams = _extract_teams(bracket.get("bracketDetails") or [])
    if eligible_team_ids is not None:
        teams = [team for team in teams if team["teamId"] in eligible_team_ids]
    if len(teams) < 2:
        return {
            "status": "BLOCKED_INSUFFICIENT_TEAMS",
            "eventId": event_id,
            "teamCount": len(teams),
        }
    simulations = min(max(int(simulations), 100), 50_000)
    cutoff = f"{event_date}T00:00:00+00:00"
    probability_cache: dict[tuple[str, str], dict[str, Any]] = {}
    team_feature_cache: dict[str, dict[str, Any]] = {
        team["teamId"]: build_side_features(
            conn,
            player_ids=team["playerIds"],
            cutoff_at=cutoff,
            window_days=365,
            include_acl_snapshots=True,
        )
        for team in teams
    }
    historical_team_ppr = {
        team_id: features.get("aggregate", {}).get("predictivePpr")
        for team_id, features in team_feature_cache.items()
    }
    event_form = checkpoint_team_form(
        conn,
        event_id=event_id,
        teams=teams,
        completed_match_ids=completed_match_ids or [],
        historical_team_ppr=historical_team_ppr,
    )
    event_context = conn.execute(
        "SELECT COALESCE(location_id, '') AS location_id, COALESCE(location_name, '') AS location_name FROM events WHERE event_id=?",
        (event_id,),
    ).fetchone()
    venue_key = str(
        (event_context["location_id"] or event_context["location_name"] if event_context else "")
        or event_info.get("leagueLocationID")
        or event_info.get("locationID")
        or event_info.get("leagueLocationName")
        or event_info.get("locationName")
        or ""
    )
    championship_context = double_dip_baseline(conn, venue_key=venue_key)
    abstained_pairs: set[tuple[str, str]] = set()

    def team_features(team: dict[str, Any]) -> dict[str, Any]:
        team_id = team["teamId"]
        features = team_feature_cache[team_id]
        adjusted = event_form.get(team_id, {}).get("adjustedPpr")
        if adjusted is None or not completed_match_ids:
            return features
        return {
            **features,
            "aggregate": {
                **features.get("aggregate", {}),
                "predictivePpr": adjusted,
            },
            "currentEventForm": event_form[team_id],
        }

    def probability(team_a: dict[str, Any], team_b: dict[str, Any]) -> float:
        key = tuple(sorted((team_a["teamId"], team_b["teamId"])))
        if key not in probability_cache:
            side_a = team_features(team_a)
            side_b = team_features(team_b)
            deltas = {
                metric: (
                    round(float(a_value) - float(side_b["aggregate"][metric]), 4)
                    if a_value is not None
                    and side_b["aggregate"].get(metric) is not None
                    else None
                )
                for metric, a_value in side_a["aggregate"].items()
            }
            matchup = {
                "featureVersion": side_a["featureVersion"],
                "dataCutoffAt": side_a["dataCutoffAt"],
                "windowDays": 365,
                "sideA": side_a,
                "sideB": side_b,
                "deltasAminusB": deltas,
                "modelReady": (
                    bool(side_a["playerIds"])
                    and bool(side_b["playerIds"])
                    and not side_a["missing"]["anyPlayerWithoutPredictivePpr"]
                    and not side_b["missing"]["anyPlayerWithoutPredictivePpr"]
                ),
            }
            prediction = score_matchup(
                matchup,
                model_version="fitted-ppr-logistic-v1",
            )
            probability_cache[key] = {
                "firstTeamId": team_a["teamId"],
                "secondTeamId": team_b["teamId"],
                "prediction": prediction,
                "matchup": matchup,
            }
            if prediction["status"] != "PREDICTED":
                abstained_pairs.add(key)
        cached = probability_cache[key]
        value = cached["prediction"].get("sideAProbability")
        if value is None:
            return 0.5
        return float(value) if cached["firstTeamId"] == team_a["teamId"] else 1.0 - float(value)

    stage_counts: dict[str, dict[int, int]] = {
        team["teamId"]: {1: simulations} for team in teams
    }
    champion_counts = {team["teamId"]: 0 for team in teams}
    rng = random.Random(f"bracket:{event_id}:{event_date}:{simulations}")
    template = None
    template_seed_slots = None
    if data_dir:
        repository = repository_bracket_templates(
            data_dir,
            exclude_event_id=event_id,
        )
        candidate = select_template(repository, bracket)
        template_seed_slots = (
            _template_seed_slots(candidate, bracket, teams)
            if candidate else None
        )
        if template_seed_slots:
            template = candidate
    if template:
        semifinal_counts = {team["teamId"]: 0 for team in teams}
        final_counts = {team["teamId"]: 0 for team in teams}
        for _ in range(simulations):
            champion, reached_semifinal, reached_final = _run_template(
                template, template_seed_slots, probability, rng,
                championship_context=championship_context,
            )
            if champion:
                champion_counts[champion["teamId"]] += 1
            for team_id in reached_semifinal:
                semifinal_counts[team_id] += 1
            for team_id in reached_final:
                final_counts[team_id] += 1
    else:
        for _ in range(simulations):
            field = list(teams)
            stage = 1
            while len(field) > 1:
                next_field = []
                for index in range(0, len(field), 2):
                    if index + 1 >= len(field):
                        winner = field[index]
                    else:
                        team_a, team_b = field[index], field[index + 1]
                        winner = team_a if rng.random() < probability(team_a, team_b) else team_b
                    next_field.append(winner)
                    stage_counts[winner["teamId"]][stage + 1] = (
                        stage_counts[winner["teamId"]].get(stage + 1, 0) + 1
                    )
                field = next_field
                stage += 1
            champion_counts[field[0]["teamId"]] += 1
    total_stages = max(
        max(counts, default=1) for counts in stage_counts.values()
    )
    results = []
    for team in teams:
        counts = stage_counts[team["teamId"]]
        round_probabilities = [
            {
                "stage": stage,
                "label": _stage_label(stage, total_stages),
                "probability": round(counts.get(stage, 0) / simulations, 6),
            }
            for stage in range(1, total_stages + 1)
        ]
        results.append({
            **team,
            "reachRoundProbabilities": round_probabilities,
            "reachSemifinalProbability": (
                round(semifinal_counts[team["teamId"]] / simulations, 6)
                if template else _named_probability(
                    counts, simulations, total_stages, "semifinal"
                )
            ),
            "reachFinalProbability": (
                round(final_counts[team["teamId"]] / simulations, 6)
                if template else _named_probability(
                    counts, simulations, total_stages, "final"
                )
            ),
            "winEventProbability": round(
                champion_counts[team["teamId"]] / simulations, 6
            ),
        })
    results.sort(key=lambda row: row["winEventProbability"], reverse=True)
    teams_by_id = {team["teamId"]: team for team in teams}
    pairing_details = []
    for key, cached in sorted(probability_cache.items()):
        first_team = teams_by_id[cached["firstTeamId"]]
        second_team = teams_by_id[cached["secondTeamId"]]
        matchup = cached["matchup"]
        prediction = cached["prediction"]
        missing_players = [
            {
                "playerId": player["playerId"],
                "playerName": next(
                    (
                        item["playerName"]
                        for team in (first_team, second_team)
                        for item in team["players"]
                        if item["playerId"] == player["playerId"]
                    ),
                    f"Player {player['playerId']}",
                ),
            }
            for side in ("sideA", "sideB")
            for player in matchup[side]["players"]
            if not player["rounds"]
        ]
        assisted_players = [
            {
                "playerId": player["playerId"],
                "playerName": next(
                    (
                        item["playerName"]
                        for team in (first_team, second_team)
                        for item in team["players"]
                        if item["playerId"] == player["playerId"]
                    ),
                    f"Player {player['playerId']}",
                ),
                "source": player.get("predictivePprSource"),
                "value": player.get("predictivePpr"),
                "sampleConfidence": player.get("predictivePprSampleConfidence"),
            }
            for side in ("sideA", "sideB")
            for player in matchup[side]["players"]
            if player.get("predictivePprSource") not in (
                "INTERNAL_CALCULATED_PPR",
                "UNAVAILABLE",
                None,
            )
        ]
        pairing_details.append({
            "teamAId": first_team["teamId"],
            "teamAName": " / ".join(
                player["playerName"] for player in first_team["players"]
            ) or first_team["teamName"],
            "teamBId": second_team["teamId"],
            "teamBName": " / ".join(
                player["playerName"] for player in second_team["players"]
            ) or second_team["teamName"],
            "status": prediction["status"],
            "teamACalculatedPpr": matchup["sideA"]["aggregate"]["predictivePpr"],
            "teamBCalculatedPpr": matchup["sideB"]["aggregate"]["predictivePpr"],
            "teamAProbability": prediction.get("sideAProbability"),
            "teamBProbability": prediction.get("sideBProbability"),
            "missingPlayers": missing_players,
            "assistedPlayers": assisted_players,
            "evidenceMode": (
                "ACL_ASSISTED"
                if assisted_players and prediction["status"] == "PREDICTED"
                else "INTERNAL_ONLY"
                if prediction["status"] == "PREDICTED"
                else "EQUAL_PROBABILITY_FALLBACK"
            ),
            "reason": (
                "One or more players have no pre-event round history."
                if missing_players else prediction.get("reason")
            ),
        })
    return {
        "status": "COMPLETE",
        "eventId": event_id,
        "eventName": (
            event_info.get("eventName")
            or event_info.get("leagueName")
            or event_info.get("leaguename")
        ),
        "eventDate": event_date,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "simulationVersion": "bracket-path-ppr-v1",
        "predictiveStatus": "EXPERIMENTAL_PENDING_RETROSPECTIVE_VALIDATION",
        "simulationCount": simulations,
        "modelVersion": "fitted-ppr-logistic-v1",
        "activeFeature": "calculatedPprDelta",
        "teamCount": len(teams),
        "teams": results,
        "coverage": {
            "possiblePairingsEvaluated": len(probability_cache),
            "modelPredictedPairings": len(probability_cache) - len(abstained_pairs),
            "equalProbabilityFallbackPairings": len(abstained_pairs),
            "modelCoverageRate": round(
                (len(probability_cache) - len(abstained_pairs))
                / len(probability_cache),
                6,
            ) if probability_cache else 0,
            "fullyInternalPairings": sum(
                1 for pairing in pairing_details
                if pairing["evidenceMode"] == "INTERNAL_ONLY"
            ),
            "aclAssistedPairings": sum(
                1 for pairing in pairing_details
                if pairing["evidenceMode"] == "ACL_ASSISTED"
            ),
            "pairingDetails": pairing_details,
        },
        "currentEventEvidence": {
            "mode": "CHECKPOINT_SAFE_SHRUNK_EVENT_FORM" if completed_match_ids else "PRE_EVENT_ONLY",
            "completedMatchIds": [str(value) for value in (completed_match_ids or [])],
            "teams": event_form,
            "priorEquivalentPlayerRounds": 40,
            "maximumAppliedPprShift": 1.5,
        },
        "championshipContext": championship_context,
        "structure": {
            "mode": (
                "VALIDATED_ACL_BRACKET_TEMPLATE"
                if template else "SEEDED_SINGLE_ELIMINATION_ABSTRACTION"
            ),
            "seedSource": "FIRST_RECORDED_BRACKET_APPEARANCE",
            "supportsByes": True,
            "exactAclAdvancementLinksAvailable": bool(template),
            "templateKey": template["templateKey"] if template else None,
            "templateEventCount": template["eventCount"] if template else 0,
            "templateEdgeCoverageRate": (
                template["edgeCoverageRate"] if template else None
            ),
        },
        "ratingWeights": {
            "currentForm": 0.0,
            "consistency": 0.0,
            "clutch": 0.0,
            "carryPerformance": 0.0,
            "strengthOfCompetition": 0.0,
            "opponentAdjustedPerformance": 0.0,
        },
        "notes": [
            "Unknown future winners are sampled from validated PPR matchup probabilities.",
            "Missing matchup history falls back to 50/50 and is counted in coverage.",
            (
                "Winner and loser advancement follows a repeated ACL layout inferred from completed events."
                if template else
                "No replicated layout matched this field; first-appearance seeding uses a single-elimination fallback."
            ),
            "Descriptive player ratings have zero simulation weight.",
            (
                "Current-event PPR is restricted to completed checkpoint matches and shrunk toward each team's pre-event baseline."
                if completed_match_ids else
                "The frozen forecast excludes every round from the current event."
            ),
            "Double-elimination finals use two-loss championship logic and a venue-shrunk historical king-seat context when the bracket template identifies the king-seat path.",
        ],
    }


def _extract_teams(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    sorted_details = sorted(
        details,
        key=lambda row: (
            _match_number(row.get("bracketmatchid")),
            str(row.get("bracketpos") or ""),
        ),
    )
    for row in sorted_details:
        if _is_bye_row(row):
            continue
        raw_id = row.get("bracketteamid")
        if raw_id in (None, ""):
            continue
        team_id = str(raw_id)
        try:
            if int(team_id) <= 0:
                continue
        except ValueError:
            continue
        players = []
        for player in row.get("player_info") or []:
            player_id = player.get("playerid") or player.get("id")
            if player_id in (None, ""):
                continue
            players.append({
                "playerId": int(player_id),
                "playerName": (
                    f"{player.get('firstname') or ''} {player.get('lastname') or ''}"
                ).strip() or f"Player {player_id}",
            })
        if team_id not in seen:
            order.append(team_id)
            seen[team_id] = {
                "teamId": team_id,
                "teamName": row.get("bracketteamname") or f"Team {team_id}",
                "playerIds": sorted({player["playerId"] for player in players}),
                "players": players,
            }
        elif players and not seen[team_id]["players"]:
            seen[team_id]["players"] = players
            seen[team_id]["playerIds"] = sorted(
                {player["playerId"] for player in players}
            )
    # ACL uses negative/empty teams as unresolved bracket destinations. A real
    # roster entry must identify at least one player before it can be simulated.
    return [seen[team_id] for team_id in order if seen[team_id]["playerIds"]]


def _is_bye_row(row: dict[str, Any]) -> bool:
    team_name = str(row.get("bracketteamname") or "").strip().lower()
    if "bye user" in team_name or team_name == "bye":
        return True
    players = [
        player for player in (row.get("player_info") or [])
        if isinstance(player, dict)
    ]
    if not players:
        return False
    names = [
        f"{player.get('firstname') or ''} {player.get('lastname') or ''}".strip().lower()
        for player in players
    ]
    return bool(names) and all(
        name == "bye" or name.startswith("bye user")
        for name in names
    )


def _template_seed_slots(
    template: dict[str, Any],
    bracket: dict[str, Any],
    teams: list[dict[str, Any]],
) -> dict[tuple[int, str], dict[str, Any]] | None:
    team_lookup = {team["teamId"]: team for team in teams}
    incoming = {
        (int(destination["matchId"]), str(destination["position"]))
        for destination in template["edges"].values()
    }
    seeds: dict[tuple[int, str], dict[str, Any]] = {}
    for row in bracket.get("bracketDetails") or []:
        if not isinstance(row, dict):
            continue
        try:
            match_id = int(row.get("bracketmatchid"))
        except (TypeError, ValueError):
            continue
        position_text = str(row.get("bracketpos") or "").upper()
        position = "T" if "T" in position_text else "B" if "B" in position_text else None
        team_id = str(row.get("bracketteamid") or "")
        coordinate = (match_id, position) if position else None
        if (
            coordinate
            and coordinate not in incoming
            and team_id in team_lookup
            and team_id not in {team["teamId"] for team in seeds.values()}
        ):
            seeds[coordinate] = team_lookup[team_id]
    return seeds if len(seeds) == len(teams) else None


def _run_template(
    template: dict[str, Any],
    seed_slots: dict[tuple[int, str], dict[str, Any]],
    probability,
    rng: random.Random,
    *,
    championship_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, set[str], set[str]]:
    slots = dict(seed_slots)
    reached_semifinal: set[str] = set()
    reached_final: set[str] = set()
    last_winner = None
    edges = template["edges"]
    for match_id_text in sorted(template["matches"], key=int):
        match_id = int(match_id_text)
        team_a = slots.get((match_id, "T"))
        team_b = slots.get((match_id, "B"))
        if not team_a and not team_b:
            continue
        description = str(
            template["matches"][match_id_text].get("roundDescription") or ""
        ).lower()
        participants = [team for team in (team_a, team_b) if team]
        if "semi" in description:
            reached_semifinal.update(team["teamId"] for team in participants)
        if "final" in description or "champ" in description:
            reached_final.update(team["teamId"] for team in participants)
        king_position = _king_seat_position(template, match_id) if "final" in description else None
        if team_a and team_b and king_position:
            king = team_a if king_position == "T" else team_b
            challenger = team_b if king_position == "T" else team_a
            king_probability = probability(king, challenger)
            king_probability = _contextual_king_game_probability(
                king_probability,
                championship_context or {},
            )
            # The king-seat team wins the event with a first-game victory. The
            # challenger must win game one to force a reset, then win again.
            if rng.random() < king_probability:
                winner, loser = king, challenger
            elif rng.random() < king_probability:
                winner, loser = king, challenger
            else:
                winner, loser = challenger, king
        elif not team_b:
            winner, loser = team_a, None
        elif not team_a:
            winner, loser = team_b, None
        elif rng.random() < probability(team_a, team_b):
            winner, loser = team_a, team_b
        else:
            winner, loser = team_b, team_a
        last_winner = winner
        for outcome, team in (("W", winner), ("L", loser)):
            destination = edges.get(f"{match_id}:{outcome}")
            if destination and team:
                slots[(
                    int(destination["matchId"]),
                    str(destination["position"]),
                )] = team
    return last_winner, reached_semifinal, reached_final


def _king_seat_position(template: dict[str, Any], final_match_id: int) -> str | None:
    candidates = []
    for edge_key, destination in (template.get("edges") or {}).items():
        if int(destination.get("matchId") or -1) != int(final_match_id):
            continue
        source_text, outcome = str(edge_key).split(":", 1)
        source = (template.get("matches") or {}).get(str(source_text)) or {}
        candidates.append((
            str(destination.get("position") or ""),
            outcome,
            str(source.get("bracketSide") or "").upper(),
        ))
    winners_side = [position for position, outcome, side in candidates if outcome == "W" and side == "W"]
    losers_side = [position for position, outcome, side in candidates if outcome == "W" and side == "L"]
    return winners_side[0] if len(winners_side) == 1 and len(losers_side) == 1 else None


def _contextual_king_game_probability(base_probability: float, context: dict[str, Any]) -> float:
    champion_rate = float(context.get("blendedKingSeatChampionshipRate") or 0.75)
    champion_rate = min(max(champion_rate, 0.5001), 0.9999)
    # For equal teams, king championship probability is 1-(1-p)^2. Convert the
    # observed championship rate back to its implied per-game king probability,
    # then use that as a contextual log-odds offset on the skill matchup.
    implied_game_probability = 1.0 - math.sqrt(1.0 - champion_rate)
    base_probability = min(max(float(base_probability), 0.0001), 0.9999)
    offset = math.log(implied_game_probability / (1.0 - implied_game_probability))
    logit = math.log(base_probability / (1.0 - base_probability)) + offset
    return 1.0 / (1.0 + math.exp(-logit))


def _match_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10**9


def _stage_label(stage: int, total_stages: int) -> str:
    remaining_rounds = total_stages - stage
    if remaining_rounds == 0:
        return "Champion"
    if remaining_rounds == 1:
        return "Final"
    if remaining_rounds == 2:
        return "Semifinal"
    if remaining_rounds == 3:
        return "Quarterfinal"
    return f"Stage {stage}"


def _named_probability(
    counts: dict[int, int],
    simulations: int,
    total_stages: int,
    name: str,
) -> float | None:
    offset = 1 if name == "final" else 2
    stage = total_stages - offset
    if stage < 1:
        return None
    return round(counts.get(stage, 0) / simulations, 6)
