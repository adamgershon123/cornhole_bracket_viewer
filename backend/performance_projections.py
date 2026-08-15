from __future__ import annotations

import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable


def rolling_ppr_profile(
    conn: sqlite3.Connection,
    player_id: int,
    *,
    cutoff_at: str | None = None,
) -> dict[str, Any]:
    cutoff = _cutoff_date(cutoff_at)
    rows = _player_rows(conn, int(player_id), cutoff)
    season_start = _season_start(cutoff)
    definitions = (
        ("season", season_start, None),
        ("last90Days", cutoff - timedelta(days=90), None),
        ("last30Days", cutoff - timedelta(days=30), None),
        ("last7Days", cutoff - timedelta(days=7), None),
        ("last100Rounds", None, 100),
    )
    windows: dict[str, dict[str, Any]] = {}
    for key, start, round_limit in definitions:
        selected = rows
        if start is not None:
            selected = [row for row in selected if date.fromisoformat(row["event_date"]) >= start]
        if round_limit is not None:
            selected = selected[-round_limit:]
        windows[key] = _window_summary(selected, start, cutoff)
    season = windows["season"]
    population = _population_ppr(conn, cutoff, season_start)
    rounds = int(season["rounds"])
    reliability = rounds / (rounds + 30)
    raw = season["ppr"]
    shrinkage_candidate = (
        reliability * float(raw) + (1 - reliability) * population
        if raw is not None else population
    )
    expected = raw
    for value in windows.values():
        value["differenceFromSeason"] = (
            round(float(value["ppr"]) - float(raw), 4)
            if value["ppr"] is not None and raw is not None else None
        )
    return {
        "playerId": int(player_id),
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE",
        "dataCutoffDate": cutoff.isoformat(),
        "seasonStart": season_start.isoformat(),
        "source": "CHEESEBAGGERS_CALCULATED_FROM_ACL_MATCH_ROUNDS",
        "windows": windows,
        "expectedPerformance": {
            "expectedPpr": round(expected, 4) if expected is not None else None,
            "rawSeasonPpr": raw,
            "populationPpr": round(population, 4) if population is not None else None,
            "seasonReliability": round(reliability, 4),
            "method": "RAW_SEASON_PPR_V1",
            "predictiveInputs": ["seasonPpr"],
            "reliabilityAdjustedCandidatePpr": (
                round(shrinkage_candidate, 4)
                if shrinkage_candidate is not None else None
            ),
            "validationStatus": "SUPPORTED_OVER_TESTED_ROLLING_WINDOWS",
            "candidateSignalsNotYetWeighted": [
                "last90Days", "last30Days", "last7Days", "last100Rounds",
                "partnershipCompatibility",
            ],
        },
    }


def partnership_compatibility(
    conn: sqlite3.Connection,
    player_ids: Iterable[int],
    *,
    cutoff_at: str | None = None,
    window_days: int = 365,
) -> dict[str, Any]:
    ids = sorted({int(value) for value in player_ids})
    cutoff = _cutoff_date(cutoff_at)
    if len(ids) < 2:
        return _empty_partnership(ids, cutoff)
    start = cutoff - timedelta(days=window_days)
    placeholders = ",".join("?" for _ in ids)
    rows = [dict(row) for row in conn.execute(
        f"""
        SELECT pr.player_id, pr.event_id, pr.match_id, pr.game_id, pr.team_id,
               pr.round_no, pr.event_date, pr.gross_points, pr.net_points,
               pr.round_result
        FROM player_rounds pr
        JOIN games g
          ON g.event_id=pr.event_id
         AND g.match_id=pr.match_id
         AND g.game_id=pr.game_id
        WHERE pr.player_id IN ({placeholders})
          AND pr.event_date>=? AND pr.event_date<?
          AND pr.team_id IS NOT NULL
          AND g.completed=1
        ORDER BY pr.event_date, pr.event_id, pr.match_id, pr.game_id, pr.round_no
        """,
        [*ids, start.isoformat(), cutoff.isoformat()],
    ).fetchall()]
    by_game: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_game[(row["event_id"], str(row["match_id"]), row["game_id"], str(row["team_id"]))].append(row)
    shared = [
        game_rows for game_rows in by_game.values()
        if {int(row["player_id"]) for row in game_rows} == set(ids)
    ]
    shared_rows = [row for game in shared for row in game]
    player_rounds = Counter(int(row["player_id"]) for row in shared_rows)
    pprs = {
        player_id: (
            sum(float(row["gross_points"] or 0) for row in shared_rows if int(row["player_id"]) == player_id)
            / player_rounds[player_id]
        )
        for player_id in ids if player_rounds[player_id]
    }
    baselines = {
        player_id: rolling_ppr_profile(
            conn, player_id, cutoff_at=f"{cutoff.isoformat()}T00:00:00+00:00"
        )["windows"]["season"]["ppr"]
        for player_id in ids
    }
    expected = {
        player_id: rolling_ppr_profile(
            conn, player_id, cutoff_at=f"{cutoff.isoformat()}T00:00:00+00:00"
        )["expectedPerformance"]["expectedPpr"]
        for player_id in ids
    }
    effects = [
        pprs[player_id] - float(baselines[player_id])
        for player_id in ids
        if player_id in pprs and baselines[player_id] is not None
    ]
    shared_rounds = min(player_rounds.values(), default=0)
    reliability = shared_rounds / (shared_rounds + 30)
    raw_effect = sum(effects) / len(effects) if effects else None
    adjusted_effect = raw_effect * reliability if raw_effect is not None else None
    ranked = sorted(
        ((player_id, float(value)) for player_id, value in expected.items() if value is not None),
        key=lambda item: item[1],
        reverse=True,
    )
    strongest = ranked[0] if ranked else None
    weakest = ranked[-1] if ranked else None
    skill_gap = strongest[1] - weakest[1] if strongest and weakest else None
    results = Counter(str(row.get("round_result") or "") for row in shared_rows)
    result_total = sum(results.values())
    return {
        "playerIds": ids,
        "knownPartnership": bool(shared),
        "dataCutoffDate": cutoff.isoformat(),
        "windowDays": window_days,
        "sharedGames": len(shared),
        "sharedEvents": len({int(game[0]["event_id"]) for game in shared}),
        "sharedRoundsPerPlayer": shared_rounds,
        "playerPprTogether": {str(key): round(value, 4) for key, value in pprs.items()},
        "playerSeasonPpr": {str(key): value for key, value in baselines.items()},
        "playerExpectedPpr": {str(key): value for key, value in expected.items()},
        "strongerPlayerId": strongest[0] if strongest else None,
        "weakerPlayerId": weakest[0] if weakest else None,
        "partnerSkillGap": round(skill_gap, 4) if skill_gap is not None else None,
        "teamBalanceRating": (
            round(max(0.0, 100.0 - 12.5 * skill_gap), 1)
            if skill_gap is not None else None
        ),
        "rawPprEffect": round(raw_effect, 4) if raw_effect is not None else None,
        "reliability": round(reliability, 4),
        "reliabilityAdjustedPprEffect": (
            round(adjusted_effect, 4) if adjusted_effect is not None else None
        ),
        "roundWinRate": round(results["W"] / result_total, 4) if result_total else None,
        "status": "DESCRIPTIVE_ONLY_PENDING_INCREMENTAL_VALIDATION",
        "interpretation": (
            "Positive effect means these players scored above their individual season "
            "baselines while playing together. Team balance describes internal skill "
            "distribution; it is not yet a prediction adjustment."
        ),
    }


def matchup_expected_performance(
    conn: sqlite3.Connection,
    side_a_player_ids: Iterable[int],
    side_b_player_ids: Iterable[int],
    *,
    cutoff_at: str | None = None,
) -> dict[str, Any]:
    cutoff_text = cutoff_at or datetime.now(timezone.utc).isoformat()
    sides = {}
    for name, ids_source in (("sideA", side_a_player_ids), ("sideB", side_b_player_ids)):
        ids = sorted({int(value) for value in ids_source})
        profiles = [rolling_ppr_profile(conn, player_id, cutoff_at=cutoff_text) for player_id in ids]
        expected_values = [
            float(profile["expectedPerformance"]["expectedPpr"])
            for profile in profiles
            if profile["expectedPerformance"]["expectedPpr"] is not None
        ]
        partnership = partnership_compatibility(conn, ids, cutoff_at=cutoff_text)
        baseline = sum(expected_values) / len(expected_values) if expected_values else None
        sides[name] = {
            "playerIds": ids,
            "players": profiles,
            "baselineExpectedPpr": round(baseline, 4) if baseline is not None else None,
            "partnership": partnership,
            "partnershipAdjustmentApplied": 0.0,
            "expectedPpr": round(baseline, 4) if baseline is not None else None,
        }
    a_value = sides["sideA"]["expectedPpr"]
    b_value = sides["sideB"]["expectedPpr"]
    sides["sideA"]["teamDynamics"] = _team_dynamics(
        sides["sideA"], opponent_expected_ppr=b_value
    )
    sides["sideB"]["teamDynamics"] = _team_dynamics(
        sides["sideB"], opponent_expected_ppr=a_value
    )
    return {
        "projectionVersion": "expected-performance-v1",
        "dataCutoffAt": cutoff_text,
        **sides,
        "expectedPprDeltaAminusB": (
            round(float(a_value) - float(b_value), 4)
            if a_value is not None and b_value is not None else None
        ),
        "guardrails": [
            "Rolling-window values are visible but do not alter Expected PPR in v1.",
            "Partnership adjustment remains zero until incremental validation passes.",
            "All internally calculated values are distinct from ACL-reported PPR.",
        ],
    }


def _team_dynamics(
    side: dict[str, Any],
    *,
    opponent_expected_ppr: float | None,
) -> dict[str, Any]:
    players = [
        (
            int(profile["playerId"]),
            profile["expectedPerformance"]["expectedPpr"],
        )
        for profile in side.get("players") or []
        if profile["expectedPerformance"]["expectedPpr"] is not None
    ]
    if len(players) < 2:
        return {
            "status": "NOT_APPLICABLE",
            "partnerSkillGap": None,
            "carryBurden": None,
            "weakLinkExposure": None,
        }
    ordered = sorted(
        ((player_id, float(value)) for player_id, value in players),
        key=lambda item: item[1],
        reverse=True,
    )
    stronger_id, stronger_ppr = ordered[0]
    weaker_id, weaker_ppr = ordered[-1]
    skill_gap = stronger_ppr - weaker_ppr
    opponent = float(opponent_expected_ppr) if opponent_expected_ppr is not None else None
    weak_link_exposure = max(opponent - weaker_ppr, 0.0) if opponent is not None else None
    required_carry_ppr = (
        max(2 * opponent - weaker_ppr, 0.0) if opponent is not None else None
    )
    carry_burden = (
        max(required_carry_ppr - stronger_ppr, 0.0)
        if required_carry_ppr is not None else None
    )
    carry_reserve = (
        stronger_ppr - required_carry_ppr
        if required_carry_ppr is not None else None
    )
    return {
        "status": "DESCRIPTIVE_ONLY_PENDING_INCREMENTAL_VALIDATION",
        "strongerPlayerId": stronger_id,
        "weakerPlayerId": weaker_id,
        "strongerExpectedPpr": round(stronger_ppr, 4),
        "weakerExpectedPpr": round(weaker_ppr, 4),
        "partnerSkillGap": round(skill_gap, 4),
        "teamBalanceRating": round(max(0.0, 100.0 - 12.5 * skill_gap), 1),
        "opponentExpectedPpr": round(opponent, 4) if opponent is not None else None,
        "weakLinkExposure": (
            round(weak_link_exposure, 4) if weak_link_exposure is not None else None
        ),
        "requiredCarryPpr": (
            round(required_carry_ppr, 4) if required_carry_ppr is not None else None
        ),
        "carryBurden": round(carry_burden, 4) if carry_burden is not None else None,
        "carryReserve": round(carry_reserve, 4) if carry_reserve is not None else None,
        "definitions": {
            "weakLinkExposure": "Opponent expected PPR minus weaker partner expected PPR.",
            "requiredCarryPpr": "Strong player PPR required to offset the weak-link deficit.",
            "carryBurden": "Required carry PPR above the strong player's own expectation.",
            "carryReserve": "Strong player's expected PPR remaining after the required carry level.",
        },
    }


def _player_rows(conn: sqlite3.Connection, player_id: int, cutoff: date) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        """
        SELECT pr.event_id, pr.match_id, pr.game_id, pr.event_date,
               pr.gross_points, pr.net_points
        FROM player_rounds pr
        JOIN games g
          ON g.event_id=pr.event_id
         AND g.match_id=pr.match_id
         AND g.game_id=pr.game_id
        WHERE pr.player_id=? AND pr.event_date IS NOT NULL
          AND pr.event_date<? AND g.completed=1
        ORDER BY pr.event_date, pr.event_id, pr.match_id, pr.game_id, pr.round_no
        """,
        (player_id, cutoff.isoformat()),
    ).fetchall()]


def _window_summary(rows: list[dict[str, Any]], start: date | None, cutoff: date) -> dict[str, Any]:
    rounds = len(rows)
    gross = sum(float(row["gross_points"] or 0) for row in rows)
    ppr = gross / rounds if rounds else None
    observed_dates = [str(row["event_date"]) for row in rows]
    reliability = rounds / (rounds + 30)
    return {
        "ppr": round(ppr, 4) if ppr is not None else None,
        "rounds": rounds,
        "games": len({(row["event_id"], str(row["match_id"]), row["game_id"]) for row in rows}),
        "events": len({row["event_id"] for row in rows}),
        "requestedStartDate": start.isoformat() if start else None,
        "firstObservedDate": min(observed_dates, default=None),
        "lastObservedDate": max(observed_dates, default=None),
        "cutoffDate": cutoff.isoformat(),
        "sampleStrength": round(reliability, 4),
        "sampleLabel": _sample_label(rounds),
    }


def _population_ppr(conn: sqlite3.Connection, cutoff: date, start: date) -> float:
    row = conn.execute(
        """
        SELECT AVG(pr.gross_points)
        FROM player_rounds pr
        JOIN games g
          ON g.event_id=pr.event_id
         AND g.match_id=pr.match_id
         AND g.game_id=pr.game_id
        WHERE pr.event_date>=? AND pr.event_date<? AND g.completed=1
        """,
        (start.isoformat(), cutoff.isoformat()),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 7.0


def _season_start(cutoff: date) -> date:
    year = cutoff.year if cutoff.month >= 9 else cutoff.year - 1
    return date(year, 9, 1)


def _cutoff_date(value: str | None) -> date:
    if not value:
        return datetime.now(timezone.utc).date()
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).date()


def _sample_label(rounds: int) -> str:
    if rounds >= 100:
        return "STRONG"
    if rounds >= 30:
        return "MODERATE"
    if rounds >= 10:
        return "LIMITED"
    return "VERY_LIMITED"


def _empty_partnership(ids: list[int], cutoff: date) -> dict[str, Any]:
    return {
        "playerIds": ids,
        "knownPartnership": False,
        "dataCutoffDate": cutoff.isoformat(),
        "sharedGames": 0,
        "sharedEvents": 0,
        "sharedRoundsPerPlayer": 0,
        "rawPprEffect": None,
        "reliability": 0.0,
        "reliabilityAdjustedPprEffect": None,
        "status": "NOT_APPLICABLE",
    }
