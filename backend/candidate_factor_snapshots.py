from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Iterable

from carry_performance import carry_performance_ratings
from clutch_rating import clutch_ratings
from opponent_adjusted_performance import opponent_adjusted_ratings
from performance_projections import partnership_compatibility
from profile_ratings import profile_ratings
from strength_of_competition import strength_of_competition_ratings
from swing_performance import swing_performance_ratings


SNAPSHOT_VERSION = "candidate-profile-factors-v1"
_RATING_CACHE: dict[tuple[int, str, int, str], dict[str, Any]] = {}


def initialize_candidate_snapshot_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_factor_snapshots (
            candidate_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shadow_run_id INTEGER NOT NULL UNIQUE,
            snapshot_version TEXT NOT NULL,
            cutoff_at TEXT NOT NULL,
            factors_json TEXT NOT NULL,
            completeness_rate REAL NOT NULL,
            available_factors INTEGER NOT NULL,
            expected_factors INTEGER NOT NULL,
            missing_reasons_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            FOREIGN KEY(shadow_run_id) REFERENCES shadow_prediction_runs(shadow_run_id)
        )
        """
    )
    conn.commit()


def build_candidate_factor_snapshot(
    conn: sqlite3.Connection,
    *,
    side_a_player_ids: Iterable[int],
    side_b_player_ids: Iterable[int],
    cutoff_at: str,
) -> dict[str, Any]:
    cutoff_date = _cutoff_date(cutoff_at)
    side_a = sorted({int(value) for value in side_a_player_ids})
    side_b = sorted({int(value) for value in side_b_player_ids})
    all_ids = sorted(set(side_a + side_b))

    populations = _rating_populations(conn, cutoff_date)
    form = populations["form"]
    clutch = populations["clutch"]
    carry = populations["carry"]
    competition = populations["competition"]
    opponent = populations["opponent"]
    swing = populations["swing"]

    players: dict[str, Any] = {}
    available = 0
    expected = len(all_ids) * 7 + 2
    missing: list[dict[str, Any]] = []
    for player_id in all_ids:
        values = {
            "currentForm": _select(
                form.get(player_id), "currentFormRating", "formSignal", "formReliability"
            ),
            "consistency": _select(
                form.get(player_id), "consistencyRating", "consistencySignal",
                "consistencyReliability",
            ),
            "opponentAdjustedPerformance": _select(
                opponent.get(player_id), "opponentAdjustedRating",
                "opponentAdjustedSignal", "strongOpponentSampleConfidence",
            ),
            "strengthOfCompetition": _select(
                competition.get(player_id), "strengthOfCompetitionRating",
                "averageOpponentExpectedPpr", "sampleConfidence",
            ),
            "carryPerformance": _select(
                carry.get(player_id), "carryRating", "carrySignal", "reliability"
            ),
            "clutchPerformance": _select(
                clutch.get(player_id), "clutchRating", "reliabilityAdjustedDelta",
                "reliability",
            ),
            "largeSwingPerformance": _select(
                swing.get(player_id), "largeSwingAvoidanceRating",
                "swingSurprise", "sampleConfidence",
                secondary_rating="largeSwingResilienceRating",
            ),
        }
        players[str(player_id)] = values
        for factor, value in values.items():
            if value["available"]:
                available += 1
            else:
                missing.append({
                    "scope": f"PLAYER:{player_id}",
                    "factor": factor,
                    "reason": "INSUFFICIENT_CUTOFF_SAFE_SAMPLE",
                })

    partnerships = {}
    for name, ids in (("sideA", side_a), ("sideB", side_b)):
        value = partnership_compatibility(conn, ids, cutoff_at=cutoff_at)
        is_available = value.get("teamBalanceRating") is not None
        partnerships[name] = {
            "available": is_available,
            "teamBalanceRating": value.get("teamBalanceRating"),
            "reliabilityAdjustedPprEffect": value.get("reliabilityAdjustedPprEffect"),
            "reliability": value.get("reliability"),
            "sharedGames": value.get("sharedGames"),
        }
        if is_available:
            available += 1
        else:
            missing.append({
                "scope": name.upper(),
                "factor": "partnershipCompatibility",
                "reason": "NO_OR_INSUFFICIENT_PRIOR_SHARED_GAMES",
            })
    return {
        "snapshotVersion": SNAPSHOT_VERSION,
        "cutoffAt": cutoff_at,
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE",
        "playerFactors": players,
        "partnershipFactors": partnerships,
        "availableFactors": available,
        "expectedFactors": expected,
        "completenessRate": round(available / expected, 6) if expected else 0.0,
        "missingReasons": missing,
    }


def persist_candidate_factor_snapshot(
    conn: sqlite3.Connection,
    *,
    shadow_run_id: int,
    snapshot: dict[str, Any],
    recorded_at: str,
) -> None:
    initialize_candidate_snapshot_schema(conn)
    conn.execute(
        """
        INSERT INTO candidate_factor_snapshots(
            shadow_run_id, snapshot_version, cutoff_at, factors_json,
            completeness_rate, available_factors, expected_factors,
            missing_reasons_json, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(shadow_run_id) DO NOTHING
        """,
        (
            shadow_run_id,
            snapshot["snapshotVersion"],
            snapshot["cutoffAt"],
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
            snapshot["completenessRate"],
            snapshot["availableFactors"],
            snapshot["expectedFactors"],
            json.dumps(snapshot["missingReasons"], sort_keys=True, separators=(",", ":")),
            recorded_at,
        ),
    )
    conn.commit()


def _select(
    row: dict[str, Any] | None,
    rating: str,
    signal: str,
    confidence: str,
    *,
    secondary_rating: str | None = None,
) -> dict[str, Any]:
    row = row or {}
    result = {
        "available": row.get(rating) is not None,
        "rating": row.get(rating),
        "signal": row.get(signal),
        "sampleConfidence": row.get(confidence),
    }
    if secondary_rating:
        result["secondaryRating"] = row.get(secondary_rating)
    return result


def _cutoff_date(value: str) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.date().isoformat()


def _rating_populations(
    conn: sqlite3.Connection,
    cutoff_date: str,
) -> dict[str, Any]:
    watermark = conn.execute(
        """
        SELECT COUNT(*), COALESCE(MAX(event_date), '')
        FROM player_rounds WHERE event_date < ?
        """,
        (cutoff_date,),
    ).fetchone()
    key = (id(conn), cutoff_date, int(watermark[0]), str(watermark[1]))
    cached = _RATING_CACHE.get(key)
    if cached is not None:
        return cached
    result = {
        "form": profile_ratings(conn, end_date=cutoff_date),
        "clutch": clutch_ratings(conn, end_date=cutoff_date),
        "carry": carry_performance_ratings(conn, end_date=cutoff_date),
        "competition": strength_of_competition_ratings(conn, end_date=cutoff_date),
        "opponent": opponent_adjusted_ratings(conn, end_date=cutoff_date),
        "swing": swing_performance_ratings(conn, end_date=cutoff_date),
    }
    # Keep only entries for this connection and current cutoff watermark. This
    # avoids unbounded growth in the long-running lifecycle worker.
    stale = [candidate for candidate in _RATING_CACHE if candidate[:2] == key[:2]]
    for candidate in stale:
        _RATING_CACHE.pop(candidate, None)
    _RATING_CACHE[key] = result
    return result
