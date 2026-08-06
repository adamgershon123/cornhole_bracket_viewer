from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


UNKNOWN = "UNKNOWN"
MANUAL = "MANUAL"
INFERRED_FROM_SCORE = "INFERRED_FROM_SCORE"
INFERRED_FROM_ROTATION = "INFERRED_FROM_ROTATION"


def reconstruct_game_states(
    rounds: Iterable[dict[str, Any]],
    *,
    opening_first_throw_team_id: str | int | None = None,
    opening_first_throw_player_id: str | int | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct score and first-throw ownership after every completed round.

    A scoring team throws first in the next round. A wash preserves the previous
    owner. Until the first scoring round, opening ownership remains unknown unless
    it was supplied manually.
    """
    ordered = sorted(
        (dict(row) for row in rounds),
        key=lambda row: int(row.get("round") or row.get("roundNumber") or 0),
    )
    rosters = _team_rosters(ordered)
    score: dict[str, int] = defaultdict(int)
    first_team = _id(opening_first_throw_team_id)
    first_player = _id(opening_first_throw_player_id)
    team_status = MANUAL if first_team is not None else UNKNOWN
    player_status = MANUAL if first_player is not None else UNKNOWN
    last_scoring_team: str | None = None
    last_scoring_player: str | None = None
    states: list[dict[str, Any]] = []

    for index, round_row in enumerate(ordered):
        round_number = int(round_row.get("round") or round_row.get("roundNumber") or index + 1)
        players = round_row.get("players") or []
        current_first_player = _player_for_team(players, first_team)
        if first_team is not None and current_first_player is not None:
            if player_status != MANUAL or first_player != current_first_player:
                first_player = current_first_player
                player_status = INFERRED_FROM_ROTATION

        score_before = dict(score)
        scoring_team = _id(round_row.get("scoringTeamId"))
        net_points = max(int(round_row.get("netPoints") or 0), 0)
        is_wash = scoring_team is None or net_points == 0
        scoring_player = _player_for_team(players, scoring_team)

        if not is_wash and scoring_team is not None:
            score[scoring_team] += net_points
            last_scoring_team = scoring_team
            last_scoring_player = scoring_player
            next_team = scoring_team
            next_team_status = INFERRED_FROM_SCORE
        else:
            next_team = first_team
            next_team_status = team_status if first_team is not None else UNKNOWN

        next_player = _next_round_player(ordered, index, next_team)
        if next_player is None:
            next_player = _rotated_partner(
                rosters.get(next_team, []),
                _player_for_team(players, next_team),
            )
        next_player_status = INFERRED_FROM_ROTATION if next_player is not None else UNKNOWN

        state = {
            "roundNumber": round_number,
            "scoreBefore": score_before,
            "scoreAfter": dict(score),
            "firstThrowTeamId": first_team,
            "firstThrowPlayerId": first_player,
            "firstThrowTeamStatus": team_status,
            "firstThrowPlayerStatus": player_status,
            "roundScoringTeamId": None if is_wash else scoring_team,
            "roundScoringPlayerId": None if is_wash else scoring_player,
            "netPoints": 0 if is_wash else net_points,
            "wasWash": is_wash,
            "lastScoringTeamId": last_scoring_team,
            "lastScoringPlayerId": last_scoring_player,
            "nextFirstThrowTeamId": next_team,
            "nextFirstThrowPlayerId": next_player,
            "nextFirstThrowTeamStatus": next_team_status,
            "nextFirstThrowPlayerStatus": next_player_status,
        }
        states.append(state)

        first_team = next_team
        first_player = next_player
        team_status = next_team_status
        player_status = next_player_status

    return states


def _id(value: Any) -> str | None:
    return None if value in (None, "", "None", "null") else str(value)


def _player_for_team(players: Iterable[dict[str, Any]], team_id: str | None) -> str | None:
    if team_id is None:
        return None
    matches = {
        _id(player.get("playerId"))
        for player in players
        if _id(player.get("teamId")) == team_id and _id(player.get("playerId")) is not None
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _team_rosters(rounds: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    rosters: dict[str, list[str]] = defaultdict(list)
    for round_row in rounds:
        for player in round_row.get("players") or []:
            team_id = _id(player.get("teamId"))
            player_id = _id(player.get("playerId"))
            if team_id and player_id and player_id not in rosters[team_id]:
                rosters[team_id].append(player_id)
    return dict(rosters)


def _next_round_player(
    rounds: list[dict[str, Any]],
    index: int,
    team_id: str | None,
) -> str | None:
    if index + 1 >= len(rounds):
        return None
    return _player_for_team(rounds[index + 1].get("players") or [], team_id)


def _rotated_partner(roster: list[str], current_player: str | None) -> str | None:
    if len(roster) == 1:
        return roster[0]
    if len(roster) == 2 and current_player in roster:
        return roster[1] if roster[0] == current_player else roster[0]
    return None
