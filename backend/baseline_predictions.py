from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

from feature_quality_audit import provisional_evidence_tier
from provenance import canonical_payload_hash
from stage_a_features import FEATURE_VERSION, build_matchup_features


MODEL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "equal-v1": {
        "modelType": "EQUAL_PROBABILITY",
        "parameters": {},
        "description": "Control benchmark assigning 50% to each identified side.",
    },
    "ppr-difference-v1": {
        "modelType": "PPR_DIFFERENCE_LOGISTIC",
        "parameters": {"scale": 1.5},
        "description": (
            "Interpretable heuristic benchmark applying a logistic transform to "
            "side A minus side B calculated PPR."
        ),
    },
    "fitted-ppr-logistic-v1": {
        "modelType": "FITTED_PPR_LOGISTIC",
        "parameters": {
            "meanPprDelta": 0.04321041666666667,
            "pprDeltaScale": 0.8521722192610962,
            "weight": 0.6712677997126119,
            "intercept": -0.050044150378253466,
            "l2": 0.1,
            "developmentExamples": 288,
            "minimumDevelopmentExamples": 100,
            "confidenceCap": 0.85,
        },
        "description": (
            "Frozen PPR-only logistic candidate selected by chronological holdout "
            "and rolling-origin validation. Intended for monitored shadow use."
        ),
    },
    "fitted-ppr-logistic-v2-acl-assisted": {
        "modelType": "FITTED_PPR_LOGISTIC",
        "parameters": {
            "meanPprDelta": 0.04321041666666667,
            "pprDeltaScale": 0.8521722192610962,
            "weight": 0.6712677997126119,
            "intercept": -0.050044150378253466,
            "l2": 0.1,
            "developmentExamples": 288,
            "minimumDevelopmentExamples": 100,
            "confidenceCap": 0.85,
        },
        "description": (
            "Rapid monitored prediction using internal calculated PPR when available "
            "and a confidence-shrunk ACL season PPR when round history is unavailable."
        ),
    },
}

EVIDENCE_ORDER = {"A": 3, "B": 2, "C": 1, "NO_PREDICTION": 0}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_prediction_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS model_definitions (
            model_version TEXT PRIMARY KEY,
            model_type TEXT NOT NULL,
            feature_version TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prediction_records (
            prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_version TEXT NOT NULL,
            feature_version TEXT NOT NULL,
            data_cutoff_at TEXT NOT NULL,
            event_id TEXT,
            match_id TEXT,
            side_a_player_ids_json TEXT NOT NULL,
            side_b_player_ids_json TEXT NOT NULL,
            evidence_tier TEXT NOT NULL,
            prediction_status TEXT NOT NULL,
            side_a_probability REAL,
            side_b_probability REAL,
            raw_side_a_probability REAL,
            shrinkage_factor REAL,
            feature_hash TEXT NOT NULL,
            features_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(model_version) REFERENCES model_definitions(model_version),
            CHECK(evidence_tier IN ('A', 'B', 'C', 'NO_PREDICTION')),
            CHECK(prediction_status IN ('PREDICTED', 'ABSTAINED')),
            CHECK(
                (prediction_status='ABSTAINED'
                    AND side_a_probability IS NULL
                    AND side_b_probability IS NULL)
                OR
                (prediction_status='PREDICTED'
                    AND side_a_probability BETWEEN 0 AND 1
                    AND side_b_probability BETWEEN 0 AND 1)
            )
        );

        CREATE INDEX IF NOT EXISTS idx_prediction_lookup
            ON prediction_records(event_id, match_id, model_version, created_at);

        CREATE INDEX IF NOT EXISTS idx_prediction_cutoff
            ON prediction_records(data_cutoff_at, model_version);
        """
    )
    for version, definition in MODEL_DEFINITIONS.items():
        conn.execute(
            """
            INSERT INTO model_definitions(
                model_version, model_type, feature_version, parameters_json,
                description, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_version) DO NOTHING
            """,
            (
                version,
                definition["modelType"],
                FEATURE_VERSION,
                json.dumps(definition["parameters"], sort_keys=True),
                definition["description"],
                utc_now(),
            ),
        )
    conn.commit()


def matchup_evidence_tier(matchup: dict[str, Any]) -> str:
    if not matchup.get("modelReady"):
        return "NO_PREDICTION"
    tiers = [
        provisional_evidence_tier(player)
        for side in ("sideA", "sideB")
        for player in matchup[side]["players"]
    ]
    if not tiers or "NO_PREDICTION" in tiers:
        return "NO_PREDICTION"
    return min(tiers, key=lambda tier: EVIDENCE_ORDER[tier])


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _raw_probability(matchup: dict[str, Any], model_version: str) -> float | None:
    if model_version == "equal-v1":
        return 0.5
    if model_version == "ppr-difference-v1":
        delta = matchup.get("deltasAminusB", {}).get("predictivePpr")
        if delta is None:
            delta = matchup.get("deltasAminusB", {}).get("calculatedPpr")
        if delta is None:
            return None
        scale = float(MODEL_DEFINITIONS[model_version]["parameters"]["scale"])
        return _sigmoid(float(delta) / scale)
    if model_version in {
        "fitted-ppr-logistic-v1",
        "fitted-ppr-logistic-v2-acl-assisted",
    }:
        delta = matchup.get("deltasAminusB", {}).get("predictivePpr")
        if delta is None:
            delta = matchup.get("deltasAminusB", {}).get("calculatedPpr")
        if delta is None:
            return None
        parameters = MODEL_DEFINITIONS[model_version]["parameters"]
        standardized = (
            float(delta) - float(parameters["meanPprDelta"])
        ) / float(parameters["pprDeltaScale"])
        return _sigmoid(
            float(parameters["intercept"])
            + float(parameters["weight"]) * standardized
        )
    raise ValueError(f"Unsupported model version: {model_version}")


def _shrinkage_factor(matchup: dict[str, Any], evidence_tier: str) -> float:
    if evidence_tier in {"A", "B"}:
        return 1.0
    if evidence_tier == "NO_PREDICTION":
        return 0.0
    player_rounds = [
        int(player.get("rounds") or 0)
        for side in ("sideA", "sideB")
        for player in matchup[side]["players"]
    ]
    minimum_rounds = min(player_rounds, default=0)
    return round(min(max(minimum_rounds / 100.0, 0.0), 1.0), 4)


def score_matchup(
    matchup: dict[str, Any],
    *,
    model_version: str,
) -> dict[str, Any]:
    if model_version not in MODEL_DEFINITIONS:
        raise ValueError(f"Unsupported model version: {model_version}")
    evidence_tier = matchup_evidence_tier(matchup)
    raw = _raw_probability(matchup, model_version)
    definition = MODEL_DEFINITIONS[model_version]
    minimum_development = int(
        definition["parameters"].get("minimumDevelopmentExamples", 0)
    )
    fitted_development = int(
        definition["parameters"].get("developmentExamples", minimum_development)
    )
    if fitted_development < minimum_development:
        evidence_tier = "NO_PREDICTION"
    if evidence_tier == "NO_PREDICTION" or raw is None:
        return {
            "modelVersion": model_version,
            "featureVersion": matchup.get("featureVersion"),
            "dataCutoffAt": matchup.get("dataCutoffAt"),
            "evidenceTier": "NO_PREDICTION",
            "status": "ABSTAINED",
            "sideAProbability": None,
            "sideBProbability": None,
            "rawSideAProbability": raw,
            "shrinkageFactor": 0.0,
            "reason": (
                "Required pre-match history or a required benchmark feature is unavailable."
            ),
        }
    acl_assisted_confidence = [
        float(player.get("predictivePprSampleConfidence") or 0)
        for side in ("sideA", "sideB")
        for player in matchup.get(side, {}).get("players", [])
        if player.get("predictivePprSource") not in (
            "INTERNAL_CALCULATED_PPR",
            None,
        )
    ]
    shrinkage = (
        min(acl_assisted_confidence)
        if model_version in {
            "fitted-ppr-logistic-v1",
            "fitted-ppr-logistic-v2-acl-assisted",
        } and acl_assisted_confidence
        else 1.0
        if model_version in {
            "fitted-ppr-logistic-v1",
            "fitted-ppr-logistic-v2-acl-assisted",
        }
        else _shrinkage_factor(matchup, evidence_tier)
    )
    probability_a = 0.5 + (float(raw) - 0.5) * shrinkage
    confidence_cap = definition["parameters"].get("confidenceCap")
    if confidence_cap is not None:
        probability_a = min(
            max(probability_a, 1.0 - float(confidence_cap)),
            float(confidence_cap),
        )
    probability_a = round(min(max(probability_a, 0.0), 1.0), 6)
    probability_b = round(1.0 - probability_a, 6)
    return {
        "modelVersion": model_version,
        "featureVersion": matchup["featureVersion"],
        "dataCutoffAt": matchup["dataCutoffAt"],
        "evidenceTier": evidence_tier,
        "status": "PREDICTED",
        "sideAProbability": probability_a,
        "sideBProbability": probability_b,
        "rawSideAProbability": round(float(raw), 6),
        "shrinkageFactor": shrinkage,
        "reason": None,
    }


def persist_prediction(
    conn: sqlite3.Connection,
    *,
    matchup: dict[str, Any],
    prediction: dict[str, Any],
    event_id: str | int | None = None,
    match_id: str | int | None = None,
) -> int:
    initialize_prediction_schema(conn)
    feature_json = json.dumps(
        matchup,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    cursor = conn.execute(
        """
        INSERT INTO prediction_records(
            model_version, feature_version, data_cutoff_at, event_id, match_id,
            side_a_player_ids_json, side_b_player_ids_json, evidence_tier,
            prediction_status, side_a_probability, side_b_probability,
            raw_side_a_probability, shrinkage_factor, feature_hash,
            features_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prediction["modelVersion"],
            prediction["featureVersion"],
            prediction["dataCutoffAt"],
            None if event_id is None else str(event_id),
            None if match_id is None else str(match_id),
            json.dumps(matchup["sideA"]["playerIds"]),
            json.dumps(matchup["sideB"]["playerIds"]),
            prediction["evidenceTier"],
            prediction["status"],
            prediction["sideAProbability"],
            prediction["sideBProbability"],
            prediction["rawSideAProbability"],
            prediction["shrinkageFactor"],
            canonical_payload_hash(matchup),
            feature_json,
            utc_now(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def create_prediction(
    conn: sqlite3.Connection,
    *,
    side_a_player_ids: Iterable[int],
    side_b_player_ids: Iterable[int],
    cutoff_at: str,
    model_version: str,
    window_days: int | None = 365,
    event_id: str | int | None = None,
    match_id: str | int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    initialize_prediction_schema(conn)
    matchup = build_matchup_features(
        conn,
        side_a_player_ids=side_a_player_ids,
        side_b_player_ids=side_b_player_ids,
        cutoff_at=cutoff_at,
        window_days=window_days,
        include_acl_snapshots=model_version == "fitted-ppr-logistic-v2-acl-assisted",
    )
    prediction = score_matchup(matchup, model_version=model_version)
    prediction_id = (
        persist_prediction(
            conn,
            matchup=matchup,
            prediction=prediction,
            event_id=event_id,
            match_id=match_id,
        )
        if persist
        else None
    )
    return {
        **prediction,
        "predictionId": prediction_id,
        "eventId": event_id,
        "matchId": match_id,
        "sideAPlayerIds": matchup["sideA"]["playerIds"],
        "sideBPlayerIds": matchup["sideB"]["playerIds"],
        "featureHash": canonical_payload_hash(matchup),
    }
