from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from stage_a_features import build_player_features
from clutch_rating import clutch_ratings
from profile_ratings import profile_ratings
from performance_projections import rolling_ppr_profile
from carry_performance import carry_performance_ratings
from strength_of_competition import strength_of_competition_ratings
from opponent_adjusted_performance import opponent_adjusted_ratings
from prediction_weighting import prediction_weighting_policy
from swing_performance import swing_performance_ratings


PROFILE_SNAPSHOT_VERSION = "predictive-profile-leaderboard-v2-consistency-shrinkage"
_PROFILE_WORKER_LOCK = threading.Lock()
_PROFILE_WORKER_STARTED = False

def _profile_data_scope(
    conn: sqlite3.Connection,
    player_id: int,
    *,
    cutoff_at: str,
    window_days: int,
) -> dict[str, Any]:
    """Explain which collected rows are eligible for predictive profile metrics."""
    cutoff = datetime.fromisoformat(cutoff_at.replace("Z", "+00:00"))
    window_start = (cutoff - timedelta(days=window_days)).isoformat()
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS collected_rounds,
            COUNT(DISTINCT pr.event_id) AS collected_events,
            MIN(pr.event_date) AS first_event_date,
            MAX(pr.event_date) AS last_event_date,
            SUM(CASE WHEN pr.event_date IS NOT NULL
                AND pr.event_date >= ? AND pr.event_date < ?
                AND g.completed=1 THEN 1 ELSE 0 END) AS included_rounds,
            SUM(CASE WHEN pr.event_date IS NULL THEN 1 ELSE 0 END) AS missing_event_date,
            SUM(CASE WHEN pr.event_date IS NOT NULL
                AND (pr.event_date < ? OR pr.event_date >= ?)
                THEN 1 ELSE 0 END) AS outside_window,
            SUM(CASE WHEN pr.event_date IS NOT NULL
                AND pr.event_date >= ? AND pr.event_date < ?
                AND g.event_id IS NULL THEN 1 ELSE 0 END) AS missing_normalized_game,
            SUM(CASE WHEN pr.event_date IS NOT NULL
                AND pr.event_date >= ? AND pr.event_date < ?
                AND g.event_id IS NOT NULL AND COALESCE(g.completed, 0) != 1
                THEN 1 ELSE 0 END) AS incomplete_game
        FROM player_rounds pr
        LEFT JOIN games g
          ON g.event_id=pr.event_id
         AND g.match_id=pr.match_id
         AND g.game_id=pr.game_id
        WHERE pr.player_id=?
        """,
        (
            window_start, cutoff_at,
            window_start, cutoff_at,
            window_start, cutoff_at,
            window_start, cutoff_at,
            int(player_id),
        ),
    ).fetchone()
    values = dict(row) if row else {}
    collected = int(values.get("collected_rounds") or 0)
    included = int(values.get("included_rounds") or 0)
    return {
        "policy": "COMPLETED_NORMALIZED_GAMES_WITHIN_365_DAYS",
        "windowDays": int(window_days),
        "windowStart": window_start,
        "cutoffAt": cutoff_at,
        "collectedRounds": collected,
        "includedRounds": included,
        "excludedRounds": max(0, collected - included),
        "collectedEvents": int(values.get("collected_events") or 0),
        "firstEventDate": values.get("first_event_date"),
        "lastEventDate": values.get("last_event_date"),
        "exclusions": {
            "missingEventDate": int(values.get("missing_event_date") or 0),
            "outsideWindow": int(values.get("outside_window") or 0),
            "missingNormalizedGame": int(values.get("missing_normalized_game") or 0),
            "incompleteGame": int(values.get("incomplete_game") or 0),
        },
    }


def predictive_player_profile(conn: sqlite3.Connection, player_id: int) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc).isoformat()
    player = conn.execute(
        "SELECT * FROM players WHERE player_id=?",
        (int(player_id),),
    ).fetchone()
    features = build_player_features(
        conn,
        player_id=int(player_id),
        cutoff_at=cutoff,
        window_days=365,
        include_acl_snapshots=True,
    )
    predictions = conn.execute(
        """
        SELECT prediction_id, event_id, match_id, model_version, data_cutoff_at,
               evidence_tier, prediction_status, side_a_player_ids_json,
               side_b_player_ids_json, side_a_probability, side_b_probability,
               created_at
        FROM prediction_records
        WHERE side_a_player_ids_json LIKE ? OR side_b_player_ids_json LIKE ?
        ORDER BY prediction_id DESC LIMIT 25
        """,
        (f"%{int(player_id)}%", f"%{int(player_id)}%"),
    ).fetchall()
    prediction_rows = []
    for raw in predictions:
        row = dict(raw)
        side_a = {int(value) for value in json.loads(row.pop("side_a_player_ids_json"))}
        side_b = {int(value) for value in json.loads(row.pop("side_b_player_ids_json"))}
        if int(player_id) not in side_a | side_b:
            continue
        row["playerSide"] = "A" if int(player_id) in side_a else "B"
        row["playerWinProbability"] = (
            row["side_a_probability"] if row["playerSide"] == "A"
            else row["side_b_probability"]
        )
        prediction_rows.append(row)
    recent_events = conn.execute(
        """
        SELECT DISTINCT e.event_id, e.event_name, e.event_date, e.match_type,
               e.bracket_type, e.blind_draw
        FROM player_rounds pr JOIN events e ON e.event_id=pr.event_id
        WHERE pr.player_id=?
        ORDER BY e.event_date DESC LIMIT 20
        """,
        (int(player_id),),
    ).fetchall()
    initialize_player_analytics_snapshot_schema(conn)
    saved_row = conn.execute(
        """
        SELECT snapshot_json, snapshot_stage, generated_at
        FROM player_analytics_snapshots
        WHERE player_id=?
        """,
        (int(player_id),),
    ).fetchone()
    saved = json.loads(saved_row["snapshot_json"]) if saved_row else {}
    clutch = saved.get("clutchProfile")
    ratings = saved.get("profileRatings") or {}
    rolling = rolling_ppr_profile(conn, int(player_id), cutoff_at=cutoff)
    carry = saved.get("carryPerformance")
    competition = saved.get("strengthOfCompetition")
    opponent_adjusted = saved.get("opponentAdjustedPerformance")
    swing = saved.get("swingPerformance")
    weighting = prediction_weighting_policy()
    data_scope = _profile_data_scope(
        conn,
        int(player_id),
        cutoff_at=cutoff,
        window_days=365,
    )
    rating_catalog = _rating_catalog(
        ratings or {}, clutch, carry, competition, opponent_adjusted, swing, weighting
    )
    return {
        "generatedAt": cutoff,
        "snapshot": {
            "stage": saved_row["snapshot_stage"] if saved_row else "ON_DEMAND",
            "generatedAt": saved_row["generated_at"] if saved_row else cutoff,
            "refreshingAdvancedRatings": (
                not saved_row or saved_row["snapshot_stage"] != "FULL_READY"
            ),
        },
        "player": dict(player) if player else {
            "player_id": int(player_id),
            "display_name": f"Player {player_id}",
        },
        "officialAcl": features.get("aclSnapshots") or {},
        "calculated": {
            key: features.get(key)
            for key in (
                "calculatedPpr", "calculatedOpponentPpr", "calculatedDpr",
                "bagsInRate", "bagsOnRate", "bagsOffRate", "fourBaggerRate",
                "roundWinRate", "roundLossRate", "roundTieRate",
            )
        },
        "sample": {
            key: features.get(key)
            for key in ("events", "games", "rounds", "lastEventDate", "recencyDays")
        },
        "coverage": features.get("coverage"),
        "dataScope": data_scope,
        "missing": features.get("missing"),
        "formatRoundCounts": features.get("formatRoundCounts"),
        "recentPredictions": prediction_rows,
        "recentEvents": [dict(row) for row in recent_events],
        "clutch": clutch or {
            "clutchRating": None,
            "label": "Insufficient sample",
            "minimumOpportunities": 10,
            "status": "REFRESHING" if saved_row else "INSUFFICIENT_SAMPLE",
        },
        "ratings": ratings or {},
        "rollingPpr": rolling,
        "carryPerformance": carry or {
            "carryRating": None,
            "label": "Insufficient carry opportunities",
            "minimumOpportunities": 8,
            "status": "REFRESHING" if saved_row else "INSUFFICIENT_SAMPLE",
        },
        "strengthOfCompetition": competition or {
            "strengthOfCompetitionRating": None,
            "label": "Insufficient opponent history",
            "minimumGames": 10,
            "status": "REFRESHING" if saved_row else "INSUFFICIENT_SAMPLE",
        },
        "opponentAdjustedPerformance": opponent_adjusted or {
            "opponentAdjustedRating": None,
            "label": "Insufficient opponent-adjusted history",
            "minimumGames": 20,
            "status": "REFRESHING" if saved_row else "INSUFFICIENT_SAMPLE",
        },
        "swingPerformance": swing or {
            "largeSwingAvoidanceRating": None,
            "largeSwingResilienceRating": None,
            "avoidanceLabel": "Insufficient large-swing sample",
            "resilienceLabel": "Insufficient recovery sample",
            "minimumExposures": 5,
            "status": "REFRESHING" if saved_row else "INSUFFICIENT_SAMPLE",
        },
        "ratingCatalog": rating_catalog,
        "predictionWeighting": weighting,
        "featureVersion": features.get("featureVersion"),
        "dataCutoffAt": features.get("dataCutoffAt"),
    }


def _rating_catalog(
    ratings: dict[str, Any],
    clutch: dict[str, Any] | None,
    carry: dict[str, Any] | None,
    competition: dict[str, Any] | None,
    opponent_adjusted: dict[str, Any] | None,
    swing: dict[str, Any] | None,
    weighting: dict[str, Any],
) -> list[dict[str, Any]]:
    policy = weighting["profileRatings"]
    rows = [
        ("currentForm", "Current Form", ratings.get("currentFormRating"),
         ratings.get("currentFormLabel"), ratings.get("formReliability"),
         ratings.get("ratedPlayers")),
        ("consistency", "Consistency", ratings.get("consistencyRating"),
         ratings.get("consistencyLabel"), ratings.get("consistencyReliability"),
         ratings.get("ratedPlayers")),
        ("clutch", "Clutch", (clutch or {}).get("clutchRating"),
         (clutch or {}).get("label"), (clutch or {}).get("reliability"),
         (clutch or {}).get("ratedPlayers")),
        ("carryPerformance", "Carry Performance", (carry or {}).get("carryRating"),
         (carry or {}).get("label"), (carry or {}).get("reliability"),
         (carry or {}).get("ratedPlayers")),
        ("strengthOfCompetition", "Strength of Competition",
         (competition or {}).get("strengthOfCompetitionRating"),
         (competition or {}).get("label"), (competition or {}).get("sampleConfidence"),
         (competition or {}).get("ratedPlayers")),
        ("opponentAdjustedPerformance", "Opponent-Adjusted Performance",
         (opponent_adjusted or {}).get("opponentAdjustedRating"),
         (opponent_adjusted or {}).get("label"),
         (opponent_adjusted or {}).get("strongOpponentSampleConfidence"),
         (opponent_adjusted or {}).get("ratedPlayers")),
        ("largeSwingAvoidance", "Large Swing Avoidance",
         (swing or {}).get("largeSwingAvoidanceRating"),
         (swing or {}).get("avoidanceLabel"),
         (swing or {}).get("sampleConfidence"),
         (swing or {}).get("ratedPlayers")),
        ("largeSwingResilience", "Large Swing Resilience",
         (swing or {}).get("largeSwingResilienceRating"),
         (swing or {}).get("resilienceLabel"),
         (swing or {}).get("sampleConfidence"),
         (swing or {}).get("ratedPlayers")),
    ]
    return [
        {
            "key": key,
            "name": name,
            "rating": rating,
            "label": label or "Insufficient sample",
            "percentile": rating,
            "sampleConfidence": confidence,
            "comparisonPool": pool,
            **policy[key],
        }
        for key, name, rating, label, confidence, pool in rows
    ]


def initialize_player_analytics_snapshot_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS player_analytics_snapshots (
            player_id INTEGER PRIMARY KEY,
            snapshot_json TEXT NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_stage TEXT NOT NULL,
            ledger_rounds INTEGER NOT NULL,
            generated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS player_analytics_snapshot_state (
            state_id INTEGER PRIMARY KEY CHECK(state_id=1),
            status TEXT NOT NULL,
            stage TEXT,
            started_at TEXT,
            completed_at TEXT,
            ledger_rounds INTEGER NOT NULL DEFAULT 0,
            profile_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );

        INSERT OR IGNORE INTO player_analytics_snapshot_state(
            state_id, status
        ) VALUES (1, 'EMPTY');
        """
    )
    conn.commit()


def _player_catalog(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    return {
        int(row["player_id"]): dict(row)
        for row in conn.execute(
            """
            SELECT player_id, display_name, state, city, skill_level, is_pro,
                   pro_classification_source, pro_observed_at,
                   membership_name, membership_type, membership_source,
                   membership_observed_at
            FROM players
            """
        ).fetchall()
    }


def _performance_summary(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    return {
        int(row[0]): {
            "calculatedPpr": round(float(row[1] or 0), 4),
            "calculatedDpr": round(float(row[2] or 0), 4),
            "rounds": int(row[3] or 0),
        }
        for row in conn.execute(
            """
            SELECT player_id, AVG(gross_points), AVG(net_points), COUNT(*)
            FROM player_rounds GROUP BY player_id
            """
        ).fetchall()
    }


def _base_player_analytics_leaderboard(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    ratings = profile_ratings(conn)
    performance = _performance_summary(conn)
    players = _player_catalog(conn)
    result = []
    for player_id, rating in ratings.items():
        player = players.get(player_id, {})
        result.append({
            "playerId": player_id,
            "playerName": player.get("display_name") or f"Player {player_id}",
            "state": player.get("state"),
            "city": player.get("city"),
            "skillLevel": player.get("skill_level"),
            "isPro": bool(player.get("is_pro")),
            "proClassificationSource": player.get("pro_classification_source"),
            "proObservedAt": player.get("pro_observed_at"),
            "membershipName": player.get("membership_name"),
            "membershipType": player.get("membership_type"),
            "membershipSource": player.get("membership_source"),
            "membershipObservedAt": player.get("membership_observed_at"),
            **performance.get(player_id, {}),
            "currentFormRating": rating.get("currentFormRating"),
            "currentFormLabel": rating.get("currentFormLabel"),
            "consistencyRating": rating.get("consistencyRating"),
            "consistencyLabel": rating.get("consistencyLabel"),
            "reliability": rating.get("consistencyReliability"),
            "profileRatings": rating,
            "profileStage": "BASE_READY",
        })
    represented = {int(row["playerId"]) for row in result}
    for player_id, player in players.items():
        if (
            not player.get("is_pro")
            and not player.get("membership_name")
            and not player.get("membership_type")
        ) or player_id in represented:
            continue
        result.append({
            "playerId": player_id,
            "playerName": player.get("display_name") or f"Player {player_id}",
            "state": player.get("state"),
            "city": player.get("city"),
            "skillLevel": player.get("skill_level"),
            "isPro": bool(player.get("is_pro")),
            "proClassificationSource": player.get("pro_classification_source"),
            "proObservedAt": player.get("pro_observed_at"),
            "membershipName": player.get("membership_name"),
            "membershipType": player.get("membership_type"),
            "membershipSource": player.get("membership_source"),
            "membershipObservedAt": player.get("membership_observed_at"),
            "rounds": 0,
            "historyStatus": "GATHERING",
            "profileStage": "IDENTITY_READY",
        })
    return result


def _calculate_full_player_analytics_leaderboard(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    ratings = profile_ratings(conn)
    clutch = clutch_ratings(conn)
    carry = carry_performance_ratings(conn)
    competition = strength_of_competition_ratings(conn)
    opponent_adjusted = opponent_adjusted_ratings(conn)
    swing = swing_performance_ratings(conn)
    performance = _performance_summary(conn)
    players = _player_catalog(conn)
    result = []
    for player_id, rating in ratings.items():
        result.append({
            "playerId": player_id,
            "playerName": players.get(player_id, {}).get("display_name") or f"Player {player_id}",
            "state": players.get(player_id, {}).get("state"),
            "city": players.get(player_id, {}).get("city"),
            "skillLevel": players.get(player_id, {}).get("skill_level"),
            "isPro": bool(players.get(player_id, {}).get("is_pro")),
            "proClassificationSource": players.get(player_id, {}).get(
                "pro_classification_source"
            ),
            "proObservedAt": players.get(player_id, {}).get("pro_observed_at"),
            "membershipName": players.get(player_id, {}).get("membership_name"),
            "membershipType": players.get(player_id, {}).get("membership_type"),
            "membershipSource": players.get(player_id, {}).get("membership_source"),
            "membershipObservedAt": players.get(player_id, {}).get(
                "membership_observed_at"
            ),
            **performance.get(player_id, {}),
            "currentFormRating": rating.get("currentFormRating"),
            "currentFormLabel": rating.get("currentFormLabel"),
            "consistencyRating": rating.get("consistencyRating"),
            "consistencyLabel": rating.get("consistencyLabel"),
            "clutchRating": clutch.get(player_id, {}).get("clutchRating"),
            "clutchLabel": clutch.get(player_id, {}).get("label"),
            "clutchOpportunities": clutch.get(player_id, {}).get("opportunities", 0),
            "carryRating": carry.get(player_id, {}).get("carryRating"),
            "carryLabel": carry.get(player_id, {}).get("label"),
            "carryOpportunities": carry.get(player_id, {}).get("opportunities", 0),
            "competitionStrengthRating": competition.get(player_id, {}).get("strengthOfCompetitionRating"),
            "competitionStrengthLabel": competition.get(player_id, {}).get("label"),
            "reliability": rating.get("consistencyReliability"),
            "profileRatings": rating,
            "clutchProfile": clutch.get(player_id),
            "carryPerformance": carry.get(player_id),
            "strengthOfCompetition": competition.get(player_id),
            "opponentAdjustedPerformance": opponent_adjusted.get(player_id),
            "swingPerformance": swing.get(player_id),
            "profileStage": "FULL_READY",
        })
    represented = {int(row["playerId"]) for row in result}
    for player_id, player in players.items():
        if (
            not player.get("is_pro")
            and not player.get("membership_name")
            and not player.get("membership_type")
        ) or player_id in represented:
            continue
        result.append({
            "playerId": player_id,
            "playerName": player.get("display_name") or f"Player {player_id}",
            "state": player.get("state"),
            "city": player.get("city"),
            "skillLevel": player.get("skill_level"),
            "isPro": bool(player.get("is_pro")),
            "proClassificationSource": player.get("pro_classification_source"),
            "proObservedAt": player.get("pro_observed_at"),
            "membershipName": player.get("membership_name"),
            "membershipType": player.get("membership_type"),
            "membershipSource": player.get("membership_source"),
            "membershipObservedAt": player.get("membership_observed_at"),
            "rounds": 0,
            "historyStatus": "GATHERING",
            "profileStage": "IDENTITY_READY",
        })
    return result


def _store_player_analytics_snapshots(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    *,
    stage: str,
) -> dict[str, Any]:
    initialize_player_analytics_snapshot_schema(conn)
    generated_at = datetime.now(timezone.utc).isoformat()
    ledger_rounds = int(
        conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0]
    )
    existing_full: dict[int, tuple[dict[str, Any], str]] = {}
    if stage == "BASE_READY":
        for existing in conn.execute(
            """
            SELECT player_id, snapshot_json, generated_at
            FROM player_analytics_snapshots
            WHERE snapshot_stage='FULL_READY'
            """
        ).fetchall():
            existing_full[int(existing["player_id"])] = (
                json.loads(existing["snapshot_json"]),
                existing["generated_at"],
            )

    prepared_rows = []
    for row in rows:
        player_id = int(row["playerId"])
        row_stage = stage
        payload = dict(row)
        if stage == "BASE_READY" and player_id in existing_full:
            previous, advanced_generated_at = existing_full[player_id]
            payload = {**previous, **payload}
            payload["profileStage"] = "FULL_READY"
            payload["baseMetricsGeneratedAt"] = generated_at
            payload["advancedMetricsGeneratedAt"] = (
                previous.get("advancedMetricsGeneratedAt") or advanced_generated_at
            )
            row_stage = "FULL_READY"
        elif stage == "FULL_READY":
            payload["baseMetricsGeneratedAt"] = generated_at
            payload["advancedMetricsGeneratedAt"] = generated_at
        prepared_rows.append((
            player_id,
            json.dumps(payload, sort_keys=True, default=str),
            PROFILE_SNAPSHOT_VERSION,
            row_stage,
            ledger_rounds,
            generated_at,
        ))
    conn.executemany(
        """
        INSERT INTO player_analytics_snapshots(
            player_id, snapshot_json, snapshot_version, snapshot_stage,
            ledger_rounds, generated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            snapshot_json=excluded.snapshot_json,
            snapshot_version=excluded.snapshot_version,
            snapshot_stage=excluded.snapshot_stage,
            ledger_rounds=excluded.ledger_rounds,
            generated_at=excluded.generated_at
        """,
        prepared_rows,
    )
    conn.execute(
        """
        UPDATE player_analytics_snapshot_state
        SET status='READY', stage=?, completed_at=?, ledger_rounds=?,
            profile_count=?, last_error=NULL
        WHERE state_id=1
        """,
        (stage, generated_at, ledger_rounds, len(rows)),
    )
    conn.commit()
    return {
        "status": "READY",
        "stage": stage,
        "profiles": len(rows),
        "ledgerRounds": ledger_rounds,
        "generatedAt": generated_at,
    }


def refresh_base_player_analytics_snapshots(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    initialize_player_analytics_snapshot_schema(conn)
    conn.execute(
        """
        UPDATE player_analytics_snapshot_state
        SET status='BUILDING', stage='BASE', started_at=?, last_error=NULL
        WHERE state_id=1
        """,
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    return _store_player_analytics_snapshots(
        conn,
        _base_player_analytics_leaderboard(conn),
        stage="BASE_READY",
    )


def refresh_full_player_analytics_snapshots(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    initialize_player_analytics_snapshot_schema(conn)
    conn.execute(
        """
        UPDATE player_analytics_snapshot_state
        SET status='BUILDING', stage='FULL', started_at=?, last_error=NULL
        WHERE state_id=1
        """,
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    return _store_player_analytics_snapshots(
        conn,
        _calculate_full_player_analytics_leaderboard(conn),
        stage="FULL_READY",
    )


def player_analytics_snapshot_status(conn: sqlite3.Connection) -> dict[str, Any]:
    initialize_player_analytics_snapshot_schema(conn)
    return dict(conn.execute(
        "SELECT * FROM player_analytics_snapshot_state WHERE state_id=1"
    ).fetchone())


def player_analytics_leaderboard(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    initialize_player_analytics_snapshot_schema(conn)
    rows = conn.execute(
        """
        SELECT snapshot_json
        FROM player_analytics_snapshots
        ORDER BY player_id
        """
    ).fetchall()
    if not rows:
        refresh_base_player_analytics_snapshots(conn)
        rows = conn.execute(
            "SELECT snapshot_json FROM player_analytics_snapshots ORDER BY player_id"
        ).fetchall()
    return [json.loads(row["snapshot_json"]) for row in rows]


def start_player_analytics_snapshot_worker(db_factory: Any) -> None:
    global _PROFILE_WORKER_STARTED
    with _PROFILE_WORKER_LOCK:
        if _PROFILE_WORKER_STARTED:
            return
        _PROFILE_WORKER_STARTED = True

    def worker() -> None:
        time.sleep(20)
        while True:
            try:
                with db_factory() as conn:
                    initialize_player_analytics_snapshot_schema(conn)
                    state = player_analytics_snapshot_status(conn)
                    ledger_rounds = int(
                        conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0]
                    )
                    snapshot_rounds = int(state.get("ledger_rounds") or 0)
                    saved_version_row = conn.execute(
                        "SELECT snapshot_version FROM player_analytics_snapshots LIMIT 1"
                    ).fetchone()
                    saved_version = saved_version_row[0] if saved_version_row else None
                    if (
                        state.get("stage") != "FULL_READY"
                        or saved_version != PROFILE_SNAPSHOT_VERSION
                    ):
                        refresh_full_player_analytics_snapshots(conn)
                    elif ledger_rounds - snapshot_rounds >= 5000:
                        # Never erase valid advanced ratings with a base-only
                        # refresh while a full rebuild is still calculating.
                        refresh_full_player_analytics_snapshots(conn)
            except Exception as exc:
                try:
                    with db_factory() as conn:
                        initialize_player_analytics_snapshot_schema(conn)
                        conn.execute(
                            """
                            UPDATE player_analytics_snapshot_state
                            SET status='ERROR', last_error=?
                            WHERE state_id=1
                            """,
                            (str(exc),),
                        )
                        conn.commit()
                except Exception:
                    pass
                print(f"Player analytics snapshot refresh failed: {exc}")
            time.sleep(60)

    threading.Thread(
        target=worker,
        daemon=True,
        name="player-analytics-snapshots",
    ).start()
