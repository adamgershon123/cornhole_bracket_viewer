from __future__ import annotations

import math
import sqlite3
from collections import defaultdict, deque
from typing import Any


LARGE_SWING_THRESHOLD = 5
SEVERE_SWING_THRESHOLD = 7
MINIMUM_EXPOSURES = 5


def swing_performance_ratings(
    conn: sqlite3.Connection,
    *,
    minimum_exposures: int = MINIMUM_EXPOSURES,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[int, dict[str, Any]]:
    """Build skill-relative large-swing ratings using only prior observations.

    A swing is attributed to every player on the side conceding the net points.
    Expected concession and volatility are learned chronologically, so a seven
    point loss can be more surprising for a strong/stable player than for a
    player whose prior round distribution makes that result less unusual.
    """
    rows = _round_rows(conn, start_date=start_date, end_date=end_date)
    histories: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=250))
    totals: dict[int, dict[str, Any]] = defaultdict(_empty_total)
    game_rows: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        game_rows[(row["eventId"], row["matchId"], row["gameId"])].append(row)

    for game in game_rows.values():
        game_key = (
            int(game[0]["eventId"]),
            str(game[0]["matchId"]),
            int(game[0]["gameId"]),
        )
        by_round: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in game:
            by_round[row["roundNo"]].append(row)
            totals[row["playerId"]]["_games"].add(game_key)
        ordered_rounds = sorted(by_round)
        score_by_team: dict[str, int] = defaultdict(int)
        pending_recovery: dict[int, dict[str, float]] = {}
        pending_immediate: list[dict[str, Any]] = []
        game_swings: list[dict[str, Any]] = []

        for round_no in ordered_rounds:
            current = by_round[round_no]
            # The immediately following round shows how the partner and
            # opposing side respond to the momentum event.
            for pending in pending_immediate:
                item = totals[int(pending["playerId"])]
                partner = next(
                    (
                        row for row in current
                        if str(row["teamId"]) == pending["teamId"]
                        and int(row["playerId"]) != int(pending["playerId"])
                    ),
                    None,
                )
                if partner:
                    partner_baseline = _baseline(histories[int(partner["playerId"])])
                    partner_delta = float(partner["netPoints"]) - partner_baseline["mean"]
                    item["partnerResponseOpportunities"] += 1
                    item["partnerResponseVsExpected"] += partner_delta
                    item["partnerPositiveResponses"] += int(float(partner["netPoints"]) > 0)
                opponent = next(
                    (
                        row for row in current
                        if str(row["teamId"]) == pending["opponentTeamId"]
                    ),
                    None,
                )
                if opponent:
                    item["opponentResponseOpportunities"] += 1
                    item["opponentFollowThrough"] += int(float(opponent["netPoints"]) > 0)
                    item["opponentGivebacks"] += int(float(opponent["netPoints"]) < 0)
            pending_immediate = []

            # Resolve recovery on the player's next recorded throwing round.
            for row in current:
                player_id = row["playerId"]
                if player_id in pending_recovery:
                    baseline = _baseline(histories[player_id])
                    recovery = float(row["netPoints"]) - baseline["mean"]
                    item = totals[player_id]
                    item["recoveryOpportunities"] += 1
                    item["recoveryAboveExpected"] += recovery
                    item["recovered"] += int(recovery > 0)
                    del pending_recovery[player_id]

            teams = {str(row["teamId"]) for row in current if row["teamId"] is not None}
            before = dict(score_by_team)
            scoring_team = next(
                (str(row["teamId"]) for row in current if int(row["netPoints"]) > 0),
                None,
            )
            net = max((int(row["netPoints"]) for row in current), default=0)
            if scoring_team and net > 0:
                score_by_team[scoring_team] += net

            for row in current:
                player_id = row["playerId"]
                signed_net = float(row["netPoints"])
                baseline = _baseline(histories[player_id])
                item = totals[player_id]
                item["rounds"] += 1
                if round_no == ordered_rounds[0]:
                    item["openingRoundOpportunities"] += 1
                    item["openingRoundNet"] += signed_net
                    item["openingRoundWins"] += int(signed_net > 0)
                if signed_net <= -LARGE_SWING_THRESHOLD:
                    concession = -signed_net
                    expected_concession = max(-baseline["mean"], 0.0)
                    surprise_points = max(concession - expected_concession, 0.0)
                    surprise_z = surprise_points / max(baseline["stdDev"], 1.5)
                    severity = concession / 21.0
                    team_id = str(row["teamId"])
                    opponent_team_id = next(
                        (
                            str(candidate["teamId"]) for candidate in current
                            if str(candidate["teamId"]) != team_id
                        ),
                        "",
                    )
                    opponent_scores = [
                        value for key, value in before.items() if key != team_id
                    ]
                    own_before = before.get(team_id, 0)
                    opp_before = max(opponent_scores, default=0)
                    own_after = score_by_team.get(team_id, own_before)
                    opp_after = max(
                        (value for key, value in score_by_team.items() if key != team_id),
                        default=opp_before,
                    )
                    context = 1.0
                    if round_no == 1:
                        context += 0.10
                    if own_before > opp_before and own_after <= opp_after:
                        context += 0.15
                        item["leadLosses"] += 1
                    if own_before == opp_before and own_after < opp_after:
                        item["tieBreaksConceded"] += 1
                    if opp_after >= 15:
                        context += 0.10
                    impact = surprise_z * severity * context
                    item["largeSwings"] += 1
                    item["_swingGames"].add(game_key)
                    item["severeSwings"] += int(concession >= SEVERE_SWING_THRESHOLD)
                    item["firstRoundSwings"] += int(round_no == 1)
                    item["concededPoints"] += concession
                    item["surprisePoints"] += surprise_points
                    item["surpriseZ"] += surprise_z
                    item["adjustedImpact"] += impact
                    pending_recovery[player_id] = {"round": float(round_no)}
                    swing_context = {
                        "playerId": player_id,
                        "teamId": team_id,
                        "opponentTeamId": opponent_team_id,
                    }
                    pending_immediate.append(swing_context)
                    game_swings.append(swing_context)

            # Updating after all calculations prevents same-round leakage.
            for row in current:
                histories[row["playerId"]].append(float(row["netPoints"]))

        if score_by_team:
            for swing in game_swings:
                item = totals[int(swing["playerId"])]
                own_score = score_by_team.get(str(swing["teamId"]), 0)
                opponent_score = max(
                    (
                        score for team, score in score_by_team.items()
                        if team != str(swing["teamId"])
                    ),
                    default=0,
                )
                item["swingOutcomeOpportunities"] += 1
                item["comebackWinsAfterSwing"] += int(own_score > opponent_score)
                item["opponentConversions"] += int(opponent_score > own_score)

    rated = []
    for player_id, item in totals.items():
        exposures = int(item["largeSwings"])
        rounds = int(item["rounds"])
        if exposures < minimum_exposures:
            continue
        reliability = exposures / (exposures + 20.0)
        exposure_rate = exposures / rounds if rounds else 0.0
        avg_surprise = item["surpriseZ"] / exposures
        avg_impact = item["adjustedImpact"] / exposures
        recovery_opportunities = int(item["recoveryOpportunities"])
        recovery_mean = (
            item["recoveryAboveExpected"] / recovery_opportunities
            if recovery_opportunities else None
        )
        partner_opportunities = int(item["partnerResponseOpportunities"])
        opponent_opportunities = int(item["opponentResponseOpportunities"])
        outcome_opportunities = int(item["swingOutcomeOpportunities"])
        opening_opportunities = int(item["openingRoundOpportunities"])
        rated.append({
            **item,
            "playerId": player_id,
            "largeSwingRate": round(exposure_rate, 4),
            "games": len(item["_games"]),
            "gamesWithLargeSwing": len(item["_swingGames"]),
            "largeSwingGameRate": (
                round(len(item["_swingGames"]) / len(item["_games"]), 4)
                if item["_games"] else 0.0
            ),
            "largeSwingsPerGame": (
                round(exposures / len(item["_games"]), 4)
                if item["_games"] else 0.0
            ),
            "severeSwingRate": round(item["severeSwings"] / rounds, 4) if rounds else 0.0,
            "averageConcession": round(item["concededPoints"] / exposures, 4),
            "averageSwingSurprise": round(avg_surprise, 4),
            "averageSurprisePoints": round(item["surprisePoints"] / exposures, 4),
            "averageAdjustedImpact": round(avg_impact, 4),
            "firstRoundSwingRate": round(item["firstRoundSwings"] / exposures, 4),
            "recoveryNetVsExpected": (
                round(recovery_mean, 4) if recovery_mean is not None else None
            ),
            "recoveryRate": (
                round(item["recovered"] / recovery_opportunities, 4)
                if recovery_opportunities else None
            ),
            "partnerResponseVsExpected": (
                round(item["partnerResponseVsExpected"] / partner_opportunities, 4)
                if partner_opportunities else None
            ),
            "partnerPositiveResponseRate": (
                round(item["partnerPositiveResponses"] / partner_opportunities, 4)
                if partner_opportunities else None
            ),
            "opponentFollowThroughRate": (
                round(item["opponentFollowThrough"] / opponent_opportunities, 4)
                if opponent_opportunities else None
            ),
            "opponentGivebackRate": (
                round(item["opponentGivebacks"] / opponent_opportunities, 4)
                if opponent_opportunities else None
            ),
            "comebackWinRateAfterSwing": (
                round(item["comebackWinsAfterSwing"] / outcome_opportunities, 4)
                if outcome_opportunities else None
            ),
            "opponentConversionRate": (
                round(item["opponentConversions"] / outcome_opportunities, 4)
                if outcome_opportunities else None
            ),
            "averageOpeningRoundNet": (
                round(item["openingRoundNet"] / opening_opportunities, 4)
                if opening_opportunities else None
            ),
            "openingRoundWinRate": (
                round(item["openingRoundWins"] / opening_opportunities, 4)
                if opening_opportunities else None
            ),
            "sampleConfidence": round(reliability, 4),
            # Lower exposure and lower skill-relative surprise are better.
            "avoidanceSignal": -(exposure_rate * 2.0 + avg_impact) * reliability,
            "resilienceSignal": (
                recovery_mean * (recovery_opportunities / (recovery_opportunities + 20.0))
                if recovery_mean is not None else None
            ),
        })
    _assign_rating(rated, "avoidanceSignal", "largeSwingAvoidanceRating")
    _assign_rating(rated, "resilienceSignal", "largeSwingResilienceRating")
    for row in rated:
        row["avoidanceLabel"] = _label(row["largeSwingAvoidanceRating"])
        row["resilienceLabel"] = _label(row.get("largeSwingResilienceRating"))
        row["ratedPlayers"] = len(rated)
        row.pop("avoidanceSignal", None)
        row.pop("resilienceSignal", None)
        row.pop("_games", None)
        row.pop("_swingGames", None)
    return {int(row["playerId"]): row for row in rated}


def validate_swing_performance(conn: sqlite3.Connection) -> dict[str, Any]:
    dates = [
        str(row[0]) for row in conn.execute(
            "SELECT DISTINCT event_date FROM events "
            "WHERE event_date IS NOT NULL ORDER BY event_date"
        ).fetchall()
    ]
    if len(dates) < 4:
        return {"status": "INSUFFICIENT_DATA"}
    split = dates[int(len(dates) * 0.7)]
    development = swing_performance_ratings(conn, end_date=split)
    holdout = swing_performance_ratings(conn, start_date=split)
    common = sorted(set(development) & set(holdout))
    pairs = [
        (
            -float(development[p]["averageAdjustedImpact"]),
            -float(holdout[p]["averageAdjustedImpact"]),
        )
        for p in common
    ]
    correlation = _correlation(pairs)
    return {
        "policy": "OLDEST_70_PERCENT_DATES_DEVELOPMENT_NEWEST_30_PERCENT_HOLDOUT",
        "splitDate": split,
        "developmentPlayers": len(development),
        "holdoutPlayers": len(holdout),
        "commonPlayers": len(common),
        "avoidanceRepeatability": round(correlation, 4) if correlation is not None else None,
        "status": (
            "REPEATABLE"
            if correlation is not None and correlation > 0.15 and len(common) >= 30
            else "DESCRIPTIVE_ONLY"
        ),
        "predictionWeight": 0.0,
    }


def _round_rows(
    conn: sqlite3.Connection,
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_id, match_id, game_id, round_no, player_id, team_id,
               net_points, event_date
        FROM player_rounds
        WHERE event_date IS NOT NULL
          AND (? IS NULL OR event_date >= ?)
          AND (? IS NULL OR event_date < ?)
        ORDER BY event_date, event_id, match_id, game_id, round_no, player_id
        """,
        (start_date, start_date, end_date, end_date),
    ).fetchall()
    return [{
        "eventId": int(row[0]), "matchId": str(row[1]), "gameId": int(row[2]),
        "roundNo": int(row[3]), "playerId": int(row[4]), "teamId": row[5],
        "netPoints": int(row[6] or 0), "eventDate": str(row[7]),
    } for row in rows]


def _baseline(history: deque[float]) -> dict[str, float]:
    if not history:
        return {"mean": 0.0, "stdDev": 3.0}
    values = list(history)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {"mean": mean, "stdDev": math.sqrt(variance)}


def _empty_total() -> dict[str, Any]:
    return {
        "rounds": 0, "largeSwings": 0, "severeSwings": 0,
        "firstRoundSwings": 0, "leadLosses": 0, "tieBreaksConceded": 0,
        "concededPoints": 0.0, "surprisePoints": 0.0, "surpriseZ": 0.0,
        "adjustedImpact": 0.0, "recoveryOpportunities": 0,
        "recoveryAboveExpected": 0.0, "recovered": 0,
        "partnerResponseOpportunities": 0, "partnerResponseVsExpected": 0.0,
        "partnerPositiveResponses": 0, "opponentResponseOpportunities": 0,
        "opponentFollowThrough": 0, "opponentGivebacks": 0,
        "swingOutcomeOpportunities": 0, "comebackWinsAfterSwing": 0,
        "opponentConversions": 0, "openingRoundOpportunities": 0,
        "openingRoundNet": 0.0, "openingRoundWins": 0,
        "_games": set(), "_swingGames": set(),
    }


def _assign_rating(rows: list[dict[str, Any]], signal: str, output: str) -> None:
    eligible = sorted(
        (row for row in rows if row.get(signal) is not None),
        key=lambda row: float(row[signal]),
    )
    count = len(eligible)
    for index, row in enumerate(eligible):
        row[output] = round(((index + 0.5) / count) * 100) if count else None


def _label(rating: int | None) -> str:
    if rating is None: return "Insufficient recovery sample"
    if rating >= 90: return "Elite"
    if rating >= 75: return "Very Good"
    if rating >= 60: return "Above Average"
    if rating >= 40: return "Average"
    if rating >= 25: return "Below Average"
    return "Developing"


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = (
        sum((x - mean_x) ** 2 for x in xs)
        * sum((y - mean_y) ** 2 for y in ys)
    ) ** 0.5
    return numerator / denominator if denominator else None
