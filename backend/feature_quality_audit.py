from __future__ import annotations

import sqlite3
from collections import Counter
from statistics import mean, median
from typing import Any, Iterable

from stage_a_features import build_player_features


AUDIT_VERSION = "feature-quality-v1"


def provisional_evidence_tier(features: dict[str, Any]) -> str:
    rounds = int(features.get("rounds") or 0)
    games = int(features.get("games") or 0)
    coverage = features.get("coverage") or {}
    snapshots = features.get("aclSnapshots") or {}
    if rounds == 0 or games == 0:
        return "C" if snapshots.get("ppr") else "NO_PREDICTION"
    if (
        rounds >= 100
        and games >= 10
        and coverage.get("coverageKnown")
        and float(coverage.get("coverageRatio") or 0) >= 0.8
        and snapshots.get("cpi")
        and snapshots.get("ppr")
    ):
        return "A"
    if rounds >= 100 and games >= 10:
        return "B"
    return "C"


def feature_anomalies(features: dict[str, Any]) -> list[str]:
    anomalies: list[str] = []
    bounded_rates = (
        "bagsInRate",
        "bagsOnRate",
        "bagsOffRate",
        "fourBaggerRate",
        "roundWinRate",
        "roundLossRate",
        "roundTieRate",
    )
    for key in bounded_rates:
        value = features.get(key)
        if value is not None and not 0 <= float(value) <= 1:
            anomalies.append(f"{key}:outside_0_1")
    ppr = features.get("calculatedPpr")
    if ppr is not None and not 0 <= float(ppr) <= 12:
        anomalies.append("calculatedPpr:outside_0_12")
    opponent_ppr = features.get("calculatedOpponentPpr")
    if opponent_ppr is not None and not 0 <= float(opponent_ppr) <= 12:
        anomalies.append("calculatedOpponentPpr:outside_0_12")
    dpr = features.get("calculatedDpr")
    if dpr is not None and not -12 <= float(dpr) <= 12:
        anomalies.append("calculatedDpr:outside_-12_12")
    placement_sum = sum(
        float(features.get(key) or 0)
        for key in ("bagsInRate", "bagsOnRate", "bagsOffRate")
    )
    if features.get("rounds") and abs(placement_sum - 1.0) > 0.001:
        anomalies.append("bagPlacementRates:do_not_sum_to_1")
    coverage = features.get("coverage") or {}
    ratio = coverage.get("coverageRatio")
    if ratio is not None and not 0 <= float(ratio) <= 1:
        anomalies.append("coverageRatio:outside_0_1")
    return anomalies


def _distribution(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "median": median(values),
        "mean": round(mean(values), 4),
        "max": max(values),
    }


def _player_ids(conn: sqlite3.Connection, limit: int | None) -> list[int]:
    sql = """
        SELECT player_id, COUNT(*) AS rounds
        FROM player_rounds
        GROUP BY player_id
        ORDER BY rounds DESC, player_id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        sql += " LIMIT ?"
        params = (limit,)
    return [int(row[0]) for row in conn.execute(sql, params).fetchall()]


def _partnership_summary(
    conn: sqlite3.Connection,
    *,
    cutoff_date: str,
    player_ids: set[int],
) -> dict[str, int]:
    placeholders = ",".join("?" for _ in player_ids)
    if not placeholders:
        return {
            "sharedTeamGames": 0,
            "uniquePartnerships": 0,
            "playersWithPartnershipHistory": 0,
        }
    rows = conn.execute(
        f"""
        SELECT event_id, match_id, game_id, team_id,
               GROUP_CONCAT(DISTINCT player_id) AS player_ids
        FROM player_rounds
        WHERE event_date IS NOT NULL
          AND event_date < ?
          AND player_id IN ({placeholders})
          AND team_id IS NOT NULL
        GROUP BY event_id, match_id, game_id, team_id
        HAVING COUNT(DISTINCT player_id) >= 2
        """,
        [cutoff_date, *sorted(player_ids)],
    ).fetchall()
    partnerships: set[tuple[int, ...]] = set()
    players: set[int] = set()
    for row in rows:
        ids = tuple(sorted(int(value) for value in str(row[4]).split(",") if value))
        if len(ids) >= 2:
            partnerships.add(ids)
            players.update(ids)
    return {
        "sharedTeamGames": len(rows),
        "uniquePartnerships": len(partnerships),
        "playersWithPartnershipHistory": len(players),
    }


def run_feature_quality_audit(
    conn: sqlite3.Connection,
    *,
    cutoff_at: str,
    window_days: int | None = 365,
    player_ids: Iterable[int] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    selected = (
        sorted({int(player_id) for player_id in player_ids})
        if player_ids is not None
        else _player_ids(conn, limit)
    )
    features = [
        build_player_features(
            conn,
            player_id=player_id,
            cutoff_at=cutoff_at,
            window_days=window_days,
            include_acl_snapshots=True,
        )
        for player_id in selected
    ]
    cutoff_date = str(features[0]["cutoffEventDate"]) if features else cutoff_at[:10]
    tiers = Counter(provisional_evidence_tier(feature) for feature in features)
    anomalies_by_player = {
        str(feature["playerId"]): feature_anomalies(feature)
        for feature in features
        if feature_anomalies(feature)
    }
    coverage_known = [
        feature for feature in features if feature["coverage"]["coverageKnown"]
    ]
    coverage_unknown = [
        feature for feature in features if not feature["coverage"]["coverageKnown"]
    ]
    formats: Counter[str] = Counter()
    for feature in features:
        formats.update(feature["formatRoundCounts"])
    ppr_deltas: list[float] = []
    cpi_available = 0
    ppr_available = 0
    for feature in features:
        snapshots = feature.get("aclSnapshots") or {}
        cpi_available += int(bool(snapshots.get("cpi")))
        ppr_snapshot = snapshots.get("ppr")
        ppr_available += int(bool(ppr_snapshot))
        if ppr_snapshot and feature.get("calculatedPpr") is not None:
            ppr_deltas.append(
                float(ppr_snapshot["value"]) - float(feature["calculatedPpr"])
            )
    indexed_less_than_retrieved = sum(
        int(
            int(feature["coverage"]["indexedExpectedGames"] or 0)
            < int(feature["coverage"]["retrievedGames"] or 0)
        )
        for feature in features
    )
    return {
        "auditVersion": AUDIT_VERSION,
        "featureVersion": "stage-a-v1",
        "dataCutoffAt": features[0]["dataCutoffAt"] if features else cutoff_at,
        "windowDays": window_days,
        "playersAudited": len(features),
        "evidenceTiers": {
            tier: tiers.get(tier, 0)
            for tier in ("A", "B", "C", "NO_PREDICTION")
        },
        "history": {
            "rounds": _distribution([int(feature["rounds"]) for feature in features]),
            "games": _distribution([int(feature["games"]) for feature in features]),
            "events": _distribution([int(feature["events"]) for feature in features]),
            "calculatedPpr": _distribution([
                float(feature["calculatedPpr"])
                for feature in features
                if feature["calculatedPpr"] is not None
            ]),
            "calculatedDpr": _distribution([
                float(feature["calculatedDpr"])
                for feature in features
                if feature["calculatedDpr"] is not None
            ]),
        },
        "coverage": {
            "knownPlayers": len(coverage_known),
            "unknownPlayers": len(coverage_unknown),
            "indexedExpectedLessThanRetrieved": indexed_less_than_retrieved,
            "knownCoverageRatios": _distribution([
                float(feature["coverage"]["coverageRatio"])
                for feature in coverage_known
                if feature["coverage"]["coverageRatio"] is not None
            ]),
            "authBlockedGamesLatestAttempt": sum(
                int(feature["coverage"]["blockedGames"]) for feature in features
            ),
        },
        "aclSnapshots": {
            "cpiEligiblePlayers": cpi_available,
            "pprEligiblePlayers": ppr_available,
            "aclMinusCalculatedPpr": _distribution(ppr_deltas),
            "meanAbsolutePprDelta": (
                round(mean(abs(value) for value in ppr_deltas), 4)
                if ppr_deltas
                else None
            ),
        },
        "formatsByRoundCount": dict(sorted(formats.items())),
        "partnerships": _partnership_summary(
            conn,
            cutoff_date=cutoff_date,
            player_ids=set(selected),
        ),
        "anomalies": {
            "playersWithAnomalies": len(anomalies_by_player),
            "byPlayer": anomalies_by_player,
        },
        "baselineBuildReady": (
            bool(features)
            and not anomalies_by_player
            and tiers.get("B", 0) + tiers.get("A", 0) > 0
        ),
        "notes": [
            "Evidence tiers are provisional data-quality tiers, not prediction confidence.",
            "Coverage is unknown when the legacy expected-game index does not contain every retrieved game.",
            "ACL snapshots are eligible only when both effective and retrieval timing pass the cutoff.",
        ],
    }
