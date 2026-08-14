from __future__ import annotations

import math
import sqlite3
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any


# One complete game can contain only a few rounds for an individual doubles
# player. Treat two prior-equivalent rounds at a neutral grade as the guard
# against tiny-sample extremes; do not require the unusually long 12 rounds
# that fewer than ten percent of recorded player-games reach.
GAME_GRADE_PRIOR_ROUNDS = 2.0
GAME_GRADE_PRIOR_SCORE = 50.0
_GAME_CALIBRATION_CACHE: dict[str, dict[str, list[float]]] = {}
GRADING_MODEL_VERSION = "tournament-report-cards-v4-category-weighted"


def build_tournament_report_cards(conn: sqlite3.Connection, event_id: int) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    event = conn.execute(
        "SELECT event_id,event_name,event_date,status,match_type,bracket_type,blind_draw,location_name FROM events WHERE event_id=?",
        (int(event_id),),
    ).fetchone()
    rows = conn.execute(
        """
        SELECT * FROM player_rounds
        WHERE event_id=?
        ORDER BY CAST(match_id AS INTEGER),game_id,round_no,player_id
        """,
        (int(event_id),),
    ).fetchall()
    if not rows:
        return {
            "status": "AWAITING_ROUND_DATA",
            "eventId": int(event_id),
            "generatedAt": _now(),
            "message": "No normalized player rounds are available for this event yet.",
            "matches": [], "players": [], "teams": [], "highlights": [],
        }

    event_data = dict(event) if event else {"event_id": int(event_id)}
    event_date = str(event_data.get("event_date") or "9999-12-31")
    player_ids = sorted({int(row["player_id"]) for row in rows})
    baselines = _baselines(conn, player_ids, event_date, int(event_id))
    game_calibration = _historical_game_calibration(conn, int(event_id))
    games = _group_games(rows)
    match_metadata = _match_metadata(conn, int(event_id))
    match_cards: list[dict[str, Any]] = []
    aggregate: dict[int, list[dict[str, Any]]] = defaultdict(list)
    player_team: dict[int, str] = {}
    highlights: list[dict[str, Any]] = []

    for game_key, game_rows in games.items():
        cards, game_highlights = _game_cards(game_key, game_rows, baselines, game_calibration)
        match_cards.append({
            "matchId": game_key[0], "gameId": game_key[1],
            "courtId": next((str(row["court_id"]) for row in game_rows if row["court_id"]), None),
            **match_metadata.get(game_key, {}),
            "winnerTeamId": _winning_team(cards),
            "players": cards,
        })
        highlights.extend(game_highlights)
        for card in cards:
            aggregate[int(card["playerId"])].append(card)
            player_team[int(card["playerId"])] = str(card.get("teamId") or "")

    event_complete = _event_complete(conn, int(event_id))
    players = [_aggregate_player(pid, cards, baselines.get(pid)) for pid, cards in aggregate.items()]
    for player in players:
        if int(player.get("baselineRounds") or 0) == 0:
            player["possibleHistoricalAccounts"] = _possible_historical_accounts(
                conn,
                int(player["playerId"]),
                str(player["playerName"]),
                int(event_id),
            )
    _apply_event_relative_scores(players)
    _apply_tournament_resume_scores(
        players,
        match_cards,
        event_complete=event_complete,
        bracket_type=str(event_data.get("bracket_type") or ""),
    )
    players.sort(key=lambda row: (-float(row["overallScore"]), row["playerName"]))
    for rank, player in enumerate(players, 1):
        player["rank"] = rank

    teams_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for player in players:
        teams_by_id[str(player.get("teamId") or player_team.get(int(player["playerId"])) or "")].append(player)
    teams = []
    for team_id, members in teams_by_id.items():
        if not team_id:
            continue
        teams.append({
            "teamId": team_id,
            "teamName": " / ".join(member["playerName"] for member in members),
            "players": [{"playerId": member["playerId"], "playerName": member["playerName"]} for member in members],
            "overallScore": round(mean(float(member["overallScore"]) for member in members), 1),
            "performanceGrade": round(mean(float(member["performanceGrade"]) for member in members), 1),
            "depthScore": round(mean(float(member["depthScore"]) for member in members), 1),
            "sustainedEvidenceScore": round(mean(float(member["sustainedEvidenceScore"]) for member in members), 1),
            "expectationScore": round(mean(float(member["categoryScores"]["expectation"]) for member in members), 1),
            "performanceScore": round(mean(float(member["categoryScores"]["performance"]) for member in members), 1),
        })
    teams.sort(key=lambda row: (-row["overallScore"], row["teamName"]))
    for rank, team in enumerate(teams, 1):
        team["rank"] = rank

    highlights.extend(_event_highlights(players, match_cards))
    highlights = sorted(highlights, key=lambda row: (-float(row.get("importance", 0)), row.get("title", "")))
    return {
        "status": "COMPLETE" if event_complete else "LIVE",
        "eventId": int(event_id),
        "event": event_data,
        "generatedAt": _now(),
        "gradingModelVersion": GRADING_MODEL_VERSION,
        "calculationMode": "USER_INITIATED_ON_DEMAND",
        "playerMvp": players[0] if players else None,
        "teamMvp": teams[0] if len(teams) and any(len(value) > 1 for value in teams_by_id.values()) else None,
        "players": players,
        "teams": teams,
        "matches": match_cards,
        "highlights": highlights[:24],
        "scoringPolicy": {
            "performance": 0.35, "expectation": 0.25, "consistency": 0.15,
            "clutch": 0.15, "resilience": 0.10,
            "finalTournamentGrade": {"performanceGrade": 0.75, "depth": 0.15, "sustainedEvidence": 0.10},
            "gameGradePriorRounds": GAME_GRADE_PRIOR_ROUNDS,
            "note": "Performance grade measures how well a player performed. The final tournament/MVP grade adds tournament depth and sustained evidence, so equally strong play over a deeper run earns greater MVP credibility without changing the underlying performance grade.",
        },
    }


def build_game_report_card(
    conn: sqlite3.Connection,
    event_id: int,
    match_id: str,
    game_id: int,
) -> dict[str, Any]:
    """Grade one game without calculating or persisting the tournament report."""
    conn.row_factory = sqlite3.Row
    event = conn.execute(
        "SELECT event_id,event_name,event_date,status,match_type,bracket_type,blind_draw,location_name FROM events WHERE event_id=?",
        (int(event_id),),
    ).fetchone()
    rows = conn.execute(
        """
        SELECT * FROM player_rounds
        WHERE event_id=? AND CAST(match_id AS TEXT)=? AND game_id=?
        ORDER BY round_no,player_id
        """,
        (int(event_id), str(match_id), int(game_id)),
    ).fetchall()
    if not rows:
        return {
            "status": "AWAITING_ROUND_DATA",
            "eventId": int(event_id),
            "matchId": str(match_id),
            "gameId": int(game_id),
            "generatedAt": _now(),
            "message": "No verified player rounds are available for this game yet.",
            "players": [],
            "highlights": [],
        }

    event_data = dict(event) if event else {"event_id": int(event_id)}
    event_date = str(event_data.get("event_date") or "9999-12-31")
    player_ids = sorted({int(row["player_id"]) for row in rows})
    cards, highlights = _game_cards(
        (str(match_id), int(game_id)),
        rows,
        _baselines(conn, player_ids, event_date, int(event_id)),
        _historical_game_calibration(conn, int(event_id)),
    )
    cards.sort(key=lambda row: (-float(row.get("overallScore") or 0), row["playerName"]))
    for rank, card in enumerate(cards, 1):
        card["rank"] = rank
    metadata = _match_metadata(conn, int(event_id)).get((str(match_id), int(game_id)), {})
    return {
        "status": "COMPLETE",
        "scope": "SINGLE_GAME",
        "eventId": int(event_id),
        "event": event_data,
        "matchId": str(match_id),
        "gameId": int(game_id),
        "generatedAt": _now(),
        "gradingModelVersion": GRADING_MODEL_VERSION,
        "calculationMode": "USER_INITIATED_SINGLE_GAME",
        "game": {
            "matchId": str(match_id),
            "gameId": int(game_id),
            "courtId": next((str(row["court_id"]) for row in rows if row["court_id"]), None),
            **metadata,
            "winnerTeamId": _winning_team(cards),
            "players": cards,
        },
        "players": cards,
        "highlights": highlights,
        "scoringPolicy": {
            "gameGradePriorRounds": GAME_GRADE_PRIOR_ROUNDS,
            "note": "This calculation grades only the selected game and does not create or replace the tournament report.",
        },
    }


def _baselines(
    conn: sqlite3.Connection,
    player_ids: list[int],
    event_date: str,
    event_id: int,
) -> dict[int, dict[str, float]]:
    if not player_ids:
        return {}
    marks = ",".join("?" for _ in player_ids)
    rows = conn.execute(
        f"""
        SELECT player_id,COUNT(*) rounds,AVG(gross_points) ppr,AVG(net_points) dpr,
               AVG(CASE WHEN round_result='W' THEN 1.0 ELSE 0 END) round_win_rate,
               AVG(four_bagger*1.0) four_bagger_rate
        FROM player_rounds
        WHERE player_id IN ({marks}) AND event_id<?
        GROUP BY player_id
        """,
        [*player_ids, int(event_id)],
    ).fetchall()
    return {int(row["player_id"]): {key: float(row[key] or 0) for key in ("rounds", "ppr", "dpr", "round_win_rate", "four_bagger_rate")} for row in rows}


def _group_games(rows: list[sqlite3.Row]) -> dict[tuple[str, int], list[sqlite3.Row]]:
    grouped: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["match_id"]), int(row["game_id"] or 1))].append(row)
    return grouped


def _match_metadata(conn: sqlite3.Connection, event_id: int) -> dict[tuple[str, int], dict[str, Any]]:
    """Read bracket context when available while remaining compatible with older archives/tests."""
    try:
        rows = conn.execute(
            """
            SELECT g.match_id,g.game_id,g.home_team_id,g.away_team_id,g.home_score,g.away_score,
                   m.round_desc,m.bracket_side
            FROM games g LEFT JOIN matches m ON m.event_id=g.event_id AND m.match_id=g.match_id
            WHERE g.event_id=?
            """,
            (event_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {
        (str(row["match_id"]), int(row["game_id"] or 1)): {
            "roundDescription": row["round_desc"], "bracketSide": row["bracket_side"],
            "homeTeamId": row["home_team_id"], "awayTeamId": row["away_team_id"],
            "homeScore": row["home_score"], "awayScore": row["away_score"],
        }
        for row in rows
    }


def _game_cards(
    game_key: tuple[str, int],
    rows: list[sqlite3.Row],
    baselines: dict[int, dict[str, float]],
    calibration: dict[str, list[float]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_player: dict[int, list[sqlite3.Row]] = defaultdict(list)
    by_round: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_player[int(row["player_id"])].append(row)
        by_round[int(row["round_no"])].append(row)
    context = _game_context(by_round)
    cards = []
    for player_id, player_rows in by_player.items():
        baseline = baselines.get(player_id, {})
        gross = [float(row["gross_points"] or 0) for row in player_rows]
        nets = [float(row["net_points"] or 0) for row in player_rows]
        clutch_rows = [row for row in player_rows if int(row["round_no"]) in context["clutchRounds"]]
        large_losses = [row for row in player_rows if float(row["net_points"] or 0) <= -5]
        recovery = []
        lookup = {int(row["round_no"]): row for row in player_rows}
        for row in large_losses:
            following = lookup.get(int(row["round_no"]) + 1)
            if following is not None:
                recovery.append(float(following["net_points"] or 0))
        team_id = str(player_rows[0]["team_id"] or "")
        ppr = mean(gross) if gross else 0
        dpr = mean(nets) if nets else 0
        segment = max(1, math.ceil(len(gross) * .25))
        start_ppr = mean(gross[:segment]) if gross else 0
        finish_ppr = mean(gross[-segment:]) if gross else 0
        cards.append({
            "matchId": game_key[0], "gameId": game_key[1],
            "playerId": player_id, "playerName": str(player_rows[0]["player_name"] or f"Player {player_id}"),
            "teamId": team_id, "rounds": len(player_rows), "ppr": round(ppr, 3), "dpr": round(dpr, 3),
            "roundWinRate": round(sum(1 for row in player_rows if row["round_result"] == "W") / len(player_rows), 4),
            "fourBaggerRate": round(sum(int(row["four_bagger"] or 0) for row in player_rows) / len(player_rows), 4),
            "fourBaggers": sum(int(row["four_bagger"] or 0) for row in player_rows),
            "bagsInRate": round(sum(int(row["bags_in"] or 0) for row in player_rows) / (4 * len(player_rows)), 4),
            "consistencyRaw": round(-pstdev(gross), 4) if len(gross) > 1 else 0,
            "expectedPpr": round(float(baseline.get("ppr", ppr)), 3),
            "baselineRounds": int(baseline.get("rounds", 0)),
            "expectationSource": "PRIOR_PLAYER_HISTORY" if int(baseline.get("rounds", 0)) > 0 else "NO_PRIOR_HISTORY_NEUTRAL",
            "pprVsExpected": round(ppr - float(baseline.get("ppr", ppr)), 3),
            "clutchNet": round(mean(float(row["net_points"] or 0) for row in clutch_rows), 3) if clutch_rows else None,
            "clutchRounds": len(clutch_rows),
            "largeSwingsConceded": len(large_losses),
            "largestRoundConceded": round(min(nets), 1) if nets else 0,
            "recoveryNet": round(mean(recovery), 3) if recovery else None,
            "comeback": context["teamComebacks"].get(team_id, 0),
            "largestLeadBlown": context["teamLeadBlown"].get(team_id, 0),
            "longestFourBaggerStreak": _longest_streak([bool(row["four_bagger"]) for row in sorted(player_rows, key=lambda item: int(item["round_no"]))]),
            "startPpr": round(start_ppr, 3), "finishPpr": round(finish_ppr, 3),
            "finishLift": round(finish_ppr - start_ppr, 3),
            "roundTrend": round(_slope(gross), 4),
        })
    _apply_game_scores(cards, calibration)
    highlights = []
    if cards:
        best_dpr = max(cards, key=lambda row: row["dpr"])
        highlights.append(_highlight("Best match DPR", best_dpr, f"{best_dpr['dpr']:+.2f} DPR", 50, game_key))
        worst = min(cards, key=lambda row: row["largestRoundConceded"])
        highlights.append(_highlight("Largest round given up", worst, f"{abs(worst['largestRoundConceded']):.0f} net points", 55, game_key))
    return cards, highlights


def _winning_team(cards: list[dict[str, Any]]) -> str | None:
    if not cards:
        return None
    by_team: dict[str, list[float]] = defaultdict(list)
    for card in cards:
        by_team[str(card.get("teamId") or "")].append(float(card.get("dpr") or 0))
    viable = {team: values for team, values in by_team.items() if team}
    return max(viable, key=lambda team: mean(viable[team])) if viable else None


def _game_context(by_round: dict[int, list[sqlite3.Row]]) -> dict[str, Any]:
    scores: dict[str, int] = defaultdict(int)
    max_leads: dict[str, int] = defaultdict(int)
    lowest_deficit: dict[str, int] = defaultdict(int)
    clutch_rounds: set[int] = set()
    for round_no in sorted(by_round):
        rows = by_round[round_no]
        teams = list(dict.fromkeys(str(row["team_id"] or "") for row in rows if row["team_id"] is not None))
        if len(teams) >= 2 and max(scores.values(), default=0) >= 15 and abs(scores[teams[0]] - scores[teams[1]]) <= 5:
            clutch_rounds.add(round_no)
        team_net = {team: mean(float(row["net_points"] or 0) for row in rows if str(row["team_id"] or "") == team) for team in teams}
        if team_net:
            winner = max(team_net, key=team_net.get)
            gain = max(0, int(round(team_net[winner])))
            scores[winner] += gain
        for team in teams:
            opponents = [scores[other] for other in teams if other != team]
            if opponents:
                lead = scores[team] - max(opponents)
                max_leads[team] = max(max_leads[team], lead)
                lowest_deficit[team] = min(lowest_deficit[team], lead)
    winner = max(scores, key=scores.get) if scores else ""
    return {
        "clutchRounds": clutch_rounds,
        "teamComebacks": {team: abs(min(0, lowest_deficit[team])) if team == winner else 0 for team in scores},
        "teamLeadBlown": {team: max_leads[team] if team != winner else 0 for team in scores},
    }


def _apply_game_scores(cards: list[dict[str, Any]], calibration: dict[str, list[float]] | None = None) -> None:
    metrics = {
        "performanceScore": lambda row: row["ppr"],
        "impactScore": lambda row: row["dpr"],
        "expectationScore": lambda row: row["pprVsExpected"],
        "consistencyScore": lambda row: row["consistencyRaw"],
        "clutchScore": lambda row: row["clutchNet"] if row["clutchNet"] is not None else row["dpr"],
        "resilienceScore": lambda row: row["recoveryNet"] if row["recoveryNet"] is not None else -row["largeSwingsConceded"],
    }
    if calibration:
        reference_keys = {
            "performanceScore": "ppr",
            "impactScore": "dpr",
            "expectationScore": "pprVsExpected",
            "consistencyScore": "consistencyRaw",
            "clutchScore": "dpr",
            "resilienceScore": "resilienceRaw",
        }
        for row in cards:
            for key, getter in metrics.items():
                if key == "clutchScore" and row.get("clutchNet") is None:
                    row[key] = 50.0
                    continue
                value = getter(row)
                if key == "resilienceScore":
                    value = -float(row.get("largeSwingsConceded") or 0) / max(1, int(row.get("rounds") or 0))
                row[key] = _reference_percentile(calibration.get(reference_keys[key], []), float(value or 0))
            row["gradingReference"] = "historical-player-games"
    else:
        for key, getter in metrics.items():
            _assign_percentile(cards, key, getter)
        for row in cards:
            row["gradingReference"] = "within-match-fallback"
    for row in cards:
        throwing_grade = .45 * row["performanceScore"] + .35 * row["expectationScore"] + .20 * row["consistencyScore"]
        impact_grade = .60 * row["impactScore"] + .20 * row["clutchScore"] + .20 * row["resilienceScore"]
        raw = .65 * throwing_grade + .35 * impact_grade
        rounds = max(0, int(row["rounds"] or 0))
        evidence_weight = rounds / (rounds + GAME_GRADE_PRIOR_ROUNDS)
        row["observedPerformanceScore"] = round(raw, 1)
        row["throwingPerformanceGrade"] = round(throwing_grade, 1)
        row["competitiveImpactGrade"] = round(impact_grade, 1)
        row["overallScore"] = round(
            evidence_weight * raw
            + (1 - evidence_weight) * GAME_GRADE_PRIOR_SCORE,
            1,
        )
        row["sampleConfidence"] = round(evidence_weight, 3)
        row["sampleRounds"] = rounds


def _aggregate_player(player_id: int, cards: list[dict[str, Any]], baseline: dict[str, float] | None) -> dict[str, Any]:
    rounds = sum(card["rounds"] for card in cards)
    weighted = lambda key: sum(float(card[key]) * card["rounds"] for card in cards) / rounds if rounds else 0
    return {
        "playerId": player_id, "playerName": cards[0]["playerName"], "teamId": cards[-1]["teamId"],
        "games": len(cards), "rounds": rounds, "ppr": round(weighted("ppr"), 3), "dpr": round(weighted("dpr"), 3),
        "roundWinRate": round(weighted("roundWinRate"), 4), "fourBaggerRate": round(weighted("fourBaggerRate"), 4),
        "fourBaggers": sum(card["fourBaggers"] for card in cards), "bagsInRate": round(weighted("bagsInRate"), 4),
        "pprVsExpected": round(weighted("pprVsExpected"), 3), "expectedPpr": round(float((baseline or {}).get("ppr", weighted("ppr"))), 3),
        "baselineRounds": int((baseline or {}).get("rounds", 0)),
        "expectationSource": "PRIOR_PLAYER_HISTORY" if int((baseline or {}).get("rounds", 0)) > 0 else "NO_PRIOR_HISTORY_NEUTRAL",
        "consistencyRaw": round(weighted("consistencyRaw"), 3),
        "clutchNet": round(mean(card["clutchNet"] for card in cards if card["clutchNet"] is not None), 3) if any(card["clutchNet"] is not None for card in cards) else None,
        "clutchRounds": sum(card["clutchRounds"] for card in cards),
        "largeSwingsConceded": sum(card["largeSwingsConceded"] for card in cards),
        "recoveryNet": round(mean(card["recoveryNet"] for card in cards if card["recoveryNet"] is not None), 3) if any(card["recoveryNet"] is not None for card in cards) else None,
        "longestFourBaggerStreak": max(card["longestFourBaggerStreak"] for card in cards),
        "largestComeback": max(card["comeback"] for card in cards),
        "largestLeadBlown": max(card["largestLeadBlown"] for card in cards),
        "largestRoundConceded": min(card["largestRoundConceded"] for card in cards),
        "startPpr": round(weighted("startPpr"), 3), "finishPpr": round(weighted("finishPpr"), 3),
        "finishLift": round(weighted("finishLift"), 3), "roundTrend": round(weighted("roundTrend"), 4),
        "matchReportCards": cards,
    }


def _possible_historical_accounts(
    conn: sqlite3.Connection,
    player_id: int,
    player_name: str,
    event_id: int,
) -> list[dict[str, Any]]:
    normalized = " ".join(str(player_name or "").lower().split())
    if not normalized:
        return []
    try:
        rows = conn.execute(
            """
            SELECT p.player_id,p.display_name,COUNT(pr.rowid) rounds,
                   COUNT(DISTINCT pr.event_id) events,AVG(pr.gross_points) ppr,
                   MIN(pr.event_date) first_event,MAX(pr.event_date) last_event
            FROM players p JOIN player_rounds pr ON pr.player_id=p.player_id
            WHERE p.player_id<>? AND LOWER(TRIM(p.display_name))=? AND pr.event_id<?
            GROUP BY p.player_id,p.display_name
            HAVING COUNT(pr.rowid)>0
            ORDER BY rounds DESC,p.player_id
            LIMIT 5
            """,
            (int(player_id), normalized, int(event_id)),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{
        "playerId": int(row["player_id"]),
        "playerName": str(row["display_name"] or player_name),
        "rounds": int(row["rounds"] or 0),
        "events": int(row["events"] or 0),
        "ppr": round(float(row["ppr"] or 0), 3),
        "firstEvent": row["first_event"],
        "lastEvent": row["last_event"],
        "matchEvidence": "EXACT_NORMALIZED_NAME_ONLY",
        "usedInGrade": False,
    } for row in rows]


def _apply_event_relative_scores(players: list[dict[str, Any]]) -> None:
    mappings = {
        "performance": lambda row: row["ppr"], "expectation": lambda row: row["pprVsExpected"],
        "consistency": lambda row: row["consistencyRaw"],
        "clutch": lambda row: row["clutchNet"] if row["clutchNet"] is not None else row["dpr"],
        "resilience": lambda row: row["recoveryNet"] if row["recoveryNet"] is not None else -row["largeSwingsConceded"],
    }
    for category, getter in mappings.items():
        _assign_percentile(players, f"_{category}", getter)
    for row in players:
        scores = {category: round(float(row.pop(f"_{category}")), 1) for category in mappings}
        cards = row.get("matchReportCards") or []
        # These are the published performance-grade weights. Earlier report
        # versions displayed the five category scores but accidentally graded
        # only the game-level observed-performance value, so a major
        # above-expectation result could be visible without affecting the grade.
        raw = (
            .35 * scores["performance"]
            + .25 * scores["expectation"]
            + .15 * scores["consistency"]
            + .15 * scores["clutch"]
            + .10 * scores["resilience"]
        )
        confidence = min(1.0, math.sqrt(max(0, row["rounds"]) / 24))
        row["categoryScores"] = scores
        row["categoryWeightedScore"] = round(raw, 1)
        row["performanceGrade"] = round(50 + (raw - 50) * confidence, 1)
        row["sampleConfidence"] = round(confidence, 3)
        row["performanceGradeLetter"] = _grade(row["performanceGrade"])


def _historical_game_calibration(conn: sqlite3.Connection, event_id: int) -> dict[str, list[float]]:
    """Build a prior-event-only empirical grading reference distribution."""
    try:
        database_path = str(conn.execute("PRAGMA database_list").fetchone()[2] or ":memory:")
        cache_key = f"{database_path}:{int(event_id)}"
        if cache_key in _GAME_CALIBRATION_CACHE:
            return _GAME_CALIBRATION_CACHE[cache_key]
        rows = conn.execute(
            """
            WITH eligible AS (
                SELECT * FROM player_rounds WHERE event_id<?
            ), baselines AS (
                SELECT player_id,AVG(gross_points) baseline_ppr
                FROM eligible GROUP BY player_id
            )
            SELECT AVG(pr.gross_points) ppr,AVG(pr.net_points) dpr,
                   AVG(pr.gross_points)-MAX(b.baseline_ppr) ppr_delta,
                   AVG(pr.gross_points*pr.gross_points)-AVG(pr.gross_points)*AVG(pr.gross_points) variance,
                   AVG(CASE WHEN pr.net_points<=-5 THEN 1.0 ELSE 0 END) swing_rate
            FROM eligible pr JOIN baselines b ON b.player_id=pr.player_id
            GROUP BY pr.event_id,pr.match_id,pr.game_id,pr.player_id
            HAVING COUNT(*)>=2
            ORDER BY MAX(pr.event_date) DESC
            LIMIT 50000
            """,
            (int(event_id),),
        ).fetchall()
    except (sqlite3.OperationalError, IndexError):
        return {}
    calibration = {
        "ppr": sorted(float(row["ppr"] or 0) for row in rows),
        "dpr": sorted(float(row["dpr"] or 0) for row in rows),
        "pprVsExpected": sorted(float(row["ppr_delta"] or 0) for row in rows),
        "consistencyRaw": sorted(-math.sqrt(max(0, float(row["variance"] or 0))) for row in rows),
        "resilienceRaw": sorted(-float(row["swing_rate"] or 0) for row in rows),
    }
    if rows:
        _GAME_CALIBRATION_CACHE[cache_key] = calibration
    return calibration


def _reference_percentile(reference: list[float], value: float) -> float:
    if not reference:
        return 50.0
    left, right = bisect_left(reference, value), bisect_right(reference, value)
    average_rank = (left + right - 1) / 2 if right > left else left
    return round(100 * average_rank / max(1, len(reference) - 1), 1)


def _apply_tournament_resume_scores(
    players: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    *,
    event_complete: bool,
    bracket_type: str = "",
) -> None:
    """Combine performance quality with advancement and repeated evidence.

    Depth is based on when a team leaves the bracket, not merely how many games
    it played. Sustained evidence rewards repeated above-baseline games and a
    larger body of rounds, rather than granting an automatic bonus for volume.
    """
    team_ids = {
        str(card.get("teamId") or "")
        for match in matches
        for card in match.get("players", [])
        if str(card.get("teamId") or "")
    }
    ordered_matches = sorted(
        matches,
        key=lambda match: (_numeric_sort(match.get("matchId")), int(match.get("gameId") or 1)),
    )
    double_elimination = (
        str(bracket_type).upper() in {"W", "D", "DOUBLE", "DOUBLE_ELIMINATION"}
        or any(str(match.get("bracketSide") or "").upper().startswith("L") for match in matches)
    )
    loss_limit = 2 if double_elimination else 1
    losses: dict[str, int] = defaultdict(int)
    last_seen: dict[str, int] = defaultdict(int)
    eliminated_at: dict[str, int] = {}
    for sequence, match in enumerate(ordered_matches, 1):
        participants = {
            str(card.get("teamId") or "")
            for card in match.get("players", [])
            if str(card.get("teamId") or "")
        }
        for team_id in participants:
            last_seen[team_id] = sequence
        winner = str(match.get("winnerTeamId") or "")
        if not winner or winner not in participants:
            continue
        for loser in participants - {winner}:
            losses[loser] += 1
            if losses[loser] >= loss_limit and loser not in eliminated_at:
                eliminated_at[loser] = sequence

    depth_by_team: dict[str, float] = {}
    if team_ids:
        survivors = team_ids - set(eliminated_at)
        if event_complete and len(survivors) == 1:
            survivor = next(iter(survivors))
            elimination_order = sorted(team_ids - {survivor}, key=lambda team: (eliminated_at.get(team, 0), last_seen.get(team, 0)))
            placement_order = [survivor, *reversed(elimination_order)]
            denominator = max(1, len(placement_order) - 1)
            depth_by_team = {team: 100 * (len(placement_order) - rank - 1) / denominator for rank, team in enumerate(placement_order)}
        else:
            progress_rows = [{"teamId": team, "progress": last_seen.get(team, 0) + (len(ordered_matches) + 1 if team in survivors else 0)} for team in team_ids]
            _assign_percentile(progress_rows, "depth", lambda row: row["progress"])
            depth_by_team = {str(row["teamId"]): float(row["depth"]) for row in progress_rows}

    for row in players:
        games = max(0, int(row.get("games") or 0))
        rounds = max(0, int(row.get("rounds") or 0))
        cards = row.get("matchReportCards") or []
        above_expected = sum(1 for card in cards if float(card.get("pprVsExpected") or 0) > 0)
        repeat_quality = 100 * above_expected / games if games else 0.0
        game_evidence = 100 * games / (games + 2) if games else 0.0
        round_evidence = 100 * rounds / (rounds + 7) if rounds else 0.0
        sustained = .40 * game_evidence + .30 * round_evidence + .30 * repeat_quality
        depth = depth_by_team.get(str(row.get("teamId") or ""), 50.0)
        performance = float(row.get("performanceGrade") or 50.0)
        final_score = .75 * performance + .15 * depth + .10 * sustained
        row["depthScore"] = round(depth, 1)
        row["sustainedEvidenceScore"] = round(sustained, 1)
        row["aboveExpectedGames"] = above_expected
        row["overallScore"] = round(final_score, 1)
        row["grade"] = _grade(row["overallScore"])


def _numeric_sort(value: Any) -> tuple[int, str]:
    text = str(value or "")
    try:
        return int(text), text
    except ValueError:
        digits = "".join(character for character in text if character.isdigit())
        return (int(digits) if digits else 10**9), text


def _assign_percentile(rows: list[dict[str, Any]], key: str, getter) -> None:
    values = [float(getter(row) or 0) for row in rows]
    ordered = sorted(range(len(rows)), key=lambda index: values[index])
    denominator = max(1, len(rows) - 1)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and math.isclose(values[ordered[end]], values[ordered[cursor]], abs_tol=1e-9):
            end += 1
        average_rank = (cursor + end - 1) / 2
        score = round(100 * average_rank / denominator, 1) if len(rows) > 1 else 50.0
        for position in range(cursor, end):
            rows[ordered[position]][key] = score
        cursor = end


def _event_highlights(players: list[dict[str, Any]], matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not players:
        return []
    specs = [
        ("Most above expectation", max(players, key=lambda row: row["pprVsExpected"]), lambda row: f"{row['pprVsExpected']:+.2f} PPR vs baseline", 90),
        ("Longest four-bagger streak", max(players, key=lambda row: row["longestFourBaggerStreak"]), lambda row: f"{row['longestFourBaggerStreak']} consecutive rounds", 75),
        ("Best tournament DPR", max(players, key=lambda row: row["dpr"]), lambda row: f"{row['dpr']:+.2f} DPR", 85),
        ("Most consistent", max(players, key=lambda row: row["consistencyRaw"]), lambda row: "Lowest round-to-round scoring variation", 70),
        ("Iron player", max(players, key=lambda row: row["rounds"]), lambda row: f"{row['rounds']} recorded rounds", 55),
    ]
    output = [{"title": title, "playerId": row["playerId"], "playerName": row["playerName"], "value": formatter(row), "importance": importance} for title, row, formatter, importance in specs]
    by_player = {int(player["playerId"]): player for player in players}

    pressure = [player for player in players if int(player.get("clutchRounds") or 0) > 0 and player.get("clutchNet") is not None]
    if pressure:
        row = max(pressure, key=lambda player: (float(player["clutchNet"]), int(player["clutchRounds"])))
        output.append(_event_award("Best pressure performance", row, f"{row['clutchNet']:+.2f} net points across {row['clutchRounds']} pressure rounds", 96))

    hottest = max(players, key=lambda row: float(row.get("startPpr", 0)) - float(row.get("expectedPpr", 0)))
    output.append(_event_award("Hottest start", hottest, f"{hottest['startPpr']:.2f} PPR in opening round segments ({hottest['startPpr'] - hottest['expectedPpr']:+.2f} vs baseline)", 91))
    finish = max(players, key=lambda row: float(row.get("finishLift", 0)))
    output.append(_event_award("Strongest finish", finish, f"Improved {finish['finishLift']:+.2f} PPR from opening to closing segments", 92))
    improved = max(players, key=lambda row: float(row.get("roundTrend", 0)))
    output.append(_event_award("Most improved across rounds", improved, f"{improved['roundTrend']:+.3f} PPR trend per recorded round", 89))

    partner_candidates: list[tuple[float, dict[str, Any]]] = []
    for player in players:
        partners = [other for other in players if other["playerId"] != player["playerId"] and str(other.get("teamId") or "") == str(player.get("teamId") or "")]
        if partners:
            lift = float(player["pprVsExpected"]) - mean(float(partner["pprVsExpected"]) for partner in partners)
            partner_candidates.append((lift, player))
    if partner_candidates:
        lift, row = max(partner_candidates, key=lambda item: item[0])
        output.append(_event_award("Best partner lift", row, f"Outperformed expectation {lift:+.2f} PPR more than partner", 93))

    game_cards = [(match, card) for match in matches for card in match.get("players", [])]
    if game_cards:
        match, row = max(game_cards, key=lambda item: (float(item[1].get("overallScore", 0)), float(item[1].get("dpr", 0))))
        output.append(_match_award("Most dominant game", row, f"{row['overallScore']:.1f} game score · {row['ppr']:.2f} PPR · {row['dpr']:+.2f} DPR", 97, match))

        match, row = min(game_cards, key=lambda item: float(item[1].get("largestRoundConceded", 0)))
        output.append(_match_award("Largest round given up", row, f"Conceded {abs(row['largestRoundConceded']):.0f} net points", 80, match))

        comeback_candidates: list[tuple[float, dict[str, Any], str]] = []
        lead_blown_candidates: list[tuple[float, dict[str, Any], str]] = []
        for match in matches:
            for team_id, cards in _match_teams(match).items():
                comeback = max((float(card.get("comeback") or 0) for card in cards), default=0)
                lead_blown = max((float(card.get("largestLeadBlown") or 0) for card in cards), default=0)
                if comeback > 0:
                    comeback_candidates.append((comeback, match, team_id))
                if lead_blown > 0:
                    lead_blown_candidates.append((lead_blown, match, team_id))
        if comeback_candidates:
            deficit, match, team_id = max(comeback_candidates, key=lambda item: item[0])
            output.append(_team_match_award("Largest comeback", match, team_id, f"Came back from {deficit:.0f} points down to win", 88))
        if lead_blown_candidates:
            lead, match, team_id = max(lead_blown_candidates, key=lambda item: item[0])
            output.append(_team_match_award("Largest lead blown", match, team_id, f"Led by {lead:.0f} points before losing", 82))

    upset = _largest_upset(matches)
    if upset:
        match, winners, baseline_gap = upset
        names = " / ".join(card["playerName"] for card in winners)
        output.append({"title": "Upset of the tournament", "playerId": winners[0]["playerId"], "playerName": names,
                       "value": f"Won despite a {baseline_gap:.2f} PPR pre-event baseline disadvantage", "importance": 100,
                       "awardType": "TEAM", "teamId": match.get("winnerTeamId"),
                       "opponentName": _opponent_name(match, str(match.get("winnerTeamId") or "")),
                       "matchId": match["matchId"], "gameId": match["gameId"]})
        giant = max(winners, key=lambda row: float(row.get("pprVsExpected", 0)))
        output.append(_match_award("Giant killer", giant, f"Beat the strongest baseline favorite while posting {giant['pprVsExpected']:+.2f} PPR vs expectation", 95, match))

    elimination_wins: dict[str, int] = defaultdict(int)
    for match in matches:
        if str(match.get("bracketSide") or "").upper().startswith("L") and match.get("winnerTeamId"):
            elimination_wins[str(match["winnerTeamId"])] += 1
    if not elimination_wins:
        # Older normalized archives did not retain bracket-side labels. In a
        # double-elimination field, wins after a team's first loss are its
        # elimination-side run and can be reconstructed without guessing labels.
        loss_seen: set[str] = set()
        for match in sorted(matches, key=lambda row: (int(row["matchId"]) if str(row["matchId"]).isdigit() else 10**9, int(row["gameId"]))):
            winner = str(match.get("winnerTeamId") or "")
            teams = {str(card.get("teamId") or "") for card in match.get("players", []) if card.get("teamId")}
            for team in teams:
                if team == winner:
                    if team in loss_seen:
                        elimination_wins[team] += 1
                else:
                    loss_seen.add(team)
    if elimination_wins:
        team_id = max(elimination_wins, key=elimination_wins.get)
        members = [player for player in players if str(player.get("teamId") or "") == team_id]
        if members:
            names = " / ".join(player["playerName"] for player in members)
            output.append({"title": "Best elimination-bracket run", "playerId": members[0]["playerId"], "playerName": names,
                           "value": f"Won {elimination_wins[team_id]} elimination-side games", "importance": 94})

    rebound_candidates: list[tuple[float, dict[str, Any], float, float]] = []
    for player in players:
        cards = list(player.get("matchReportCards") or [])
        for index, low_card in enumerate(cards[:-1]):
            best_later = max(cards[index + 1:], key=lambda card: float(card.get("ppr") or 0))
            rebound = float(best_later.get("ppr") or 0) - float(low_card.get("ppr") or 0)
            rebound_candidates.append((rebound, player, float(low_card.get("ppr") or 0), float(best_later.get("ppr") or 0)))
    if rebound_candidates:
        rebound, player, low_ppr, later_ppr = max(rebound_candidates, key=lambda item: item[0])
        if rebound > 0:
            output.append(_event_award("Comeback player", player, f"Rebounded {rebound:+.2f} PPR after a {low_ppr:.2f} PPR low game (later reached {later_ppr:.2f} PPR)", 90))
    return output


def _largest_upset(matches: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], float] | None:
    candidates = []
    for match in matches:
        winner = str(match.get("winnerTeamId") or "")
        teams: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for card in match.get("players", []):
            teams[str(card.get("teamId") or "")].append(card)
        if not winner or winner not in teams or len(teams) < 2:
            continue
        winner_baseline = mean(float(card.get("expectedPpr") or 0) for card in teams[winner])
        opponent_baseline = max(mean(float(card.get("expectedPpr") or 0) for card in cards) for team, cards in teams.items() if team != winner)
        gap = opponent_baseline - winner_baseline
        if gap > 0:
            candidates.append((gap, match, teams[winner]))
    if not candidates:
        return None
    gap, match, winners = max(candidates, key=lambda item: item[0])
    return match, winners, gap


def _event_award(title: str, player: dict[str, Any], value: str, importance: int) -> dict[str, Any]:
    return {"title": title, "playerId": player["playerId"], "playerName": player["playerName"], "value": value, "importance": importance}


def _match_award(title: str, player: dict[str, Any], value: str, importance: int, match: dict[str, Any]) -> dict[str, Any]:
    return {
        **_event_award(title, player, value, importance),
        "opponentName": _opponent_name(match, str(player.get("teamId") or "")),
        "matchId": match["matchId"], "gameId": match["gameId"],
    }


def _match_teams(match: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    teams: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in match.get("players", []):
        team_id = str(card.get("teamId") or "")
        if team_id:
            teams[team_id].append(card)
    return teams


def _team_name(cards: list[dict[str, Any]]) -> str:
    return " / ".join(str(card.get("playerName") or "Unknown player") for card in cards)


def _opponent_name(match: dict[str, Any], team_id: str) -> str | None:
    opponents = [cards for candidate, cards in _match_teams(match).items() if candidate != team_id]
    return " vs ".join(_team_name(cards) for cards in opponents) if opponents else None


def _team_match_award(title: str, match: dict[str, Any], team_id: str, value: str, importance: int) -> dict[str, Any]:
    cards = _match_teams(match).get(team_id, [])
    return {
        "title": title,
        "playerId": cards[0]["playerId"] if cards else None,
        "playerName": _team_name(cards),
        "awardType": "TEAM",
        "teamId": team_id,
        "opponentName": _opponent_name(match, team_id),
        "value": value,
        "importance": importance,
        "matchId": match["matchId"],
        "gameId": match["gameId"],
    }


def _highlight(title: str, player: dict[str, Any], value: str, importance: int, game_key: tuple[str, int]) -> dict[str, Any]:
    return {"title": title, "playerId": player["playerId"], "playerName": player["playerName"], "value": value, "importance": importance, "matchId": game_key[0], "gameId": game_key[1]}


def _longest_streak(values: list[bool]) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    return sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator if denominator else 0.0


def _grade(score: float) -> str:
    if score >= 93: return "A+"
    if score >= 85: return "A"
    if score >= 77: return "B+"
    if score >= 69: return "B"
    if score >= 60: return "C+"
    if score >= 50: return "C"
    if score >= 40: return "D"
    return "F"


def _event_complete(conn: sqlite3.Connection, event_id: int) -> bool:
    row = conn.execute("SELECT COUNT(*),SUM(CASE WHEN completed=1 THEN 1 ELSE 0 END) FROM games WHERE event_id=?", (event_id,)).fetchone()
    return bool(row and int(row[0] or 0) > 0 and int(row[0] or 0) == int(row[1] or 0))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
