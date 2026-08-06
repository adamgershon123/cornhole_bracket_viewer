from __future__ import annotations

from typing import Any

from baseline_predictions import MODEL_DEFINITIONS


def prediction_weighting_policy() -> dict[str, Any]:
    fitted = MODEL_DEFINITIONS["fitted-ppr-logistic-v1"]["parameters"]
    ratings = {
        "currentForm": _zero(
            "REJECTED_FOR_NOW",
            "Worsened Brier score and log loss versus PPR-only in rolling-origin testing.",
        ),
        "consistency": _zero(
            "REJECTED_FOR_NOW",
            "Worsened Brier score, log loss, and accuracy versus PPR-only.",
        ),
        "clutch": _zero(
            "DESCRIPTIVE_ONLY",
            "Holdout validation had insufficient qualified players and negative correlation.",
        ),
        "carryPerformance": _zero(
            "DESCRIPTIVE_ONLY",
            "Only seven qualified holdout players; carry outperformance correlation was negative.",
        ),
        "strengthOfCompetition": _zero(
            "DESCRIPTIVE_ONLY",
            "Measures schedule difficulty but has not demonstrated incremental game-prediction value.",
        ),
        "opponentAdjustedPerformance": _zero(
            "REJECTED_FOR_NOW",
            "Slightly improved MAE but worsened RMSE; opponent-tier adjustment worsened both.",
        ),
        "largeSwingAvoidance": _zero(
            "DESCRIPTIVE_ONLY",
            "Skill-relative swing surprise is active in profiles but has not yet shown incremental predictive value.",
        ),
        "largeSwingResilience": _zero(
            "DESCRIPTIVE_ONLY",
            "Post-swing recovery is active in profiles but has not yet shown incremental predictive value.",
        ),
    }
    return {
        "policyVersion": "prediction-weighting-v1",
        "gamePrediction": {
            "status": "ACTIVE_SHADOW_MODEL",
            "modelVersion": "fitted-ppr-logistic-v1",
            "activeFeature": "calculatedPprDelta",
            "standardizedCoefficient": fitted["weight"],
            "intercept": fitted["intercept"],
            "confidenceCap": fitted["confidenceCap"],
            "ratingWeights": {
                key: value["gamePredictionWeight"] for key, value in ratings.items()
            },
        },
        "advancedChallenger": {
            "status": "SUPPORTED_SHADOW",
            "modelVersion": "scoring-distribution-challenger-v1",
            "activeFeatures": [
                "predictivePprDelta",
                "ceilingRateDelta",
                "floorAvoidanceDelta",
                "calculatedDprDelta",
            ],
            "rollingTestMatchups": 381,
            "accuracy": 0.677165,
            "pprOnlyAccuracy": 0.661417,
            "brierScore": 0.213115,
            "pprOnlyBrierScore": 0.215524,
            "logLoss": 0.616982,
            "pprOnlyLogLoss": 0.623167,
            "productionWeight": 0.0,
            "promotionRule": (
                "Remain shadow-only until live prospective predictions confirm "
                "the chronological validation improvement."
            ),
        },
        "liveGamePrediction": {
            "status": "ACTIVE",
            "pregameFoundation": "fitted-ppr-logistic-v1",
            "additionalValidatedInputs": [
                "scoreState", "roundState", "firstThrowWhenKnown",
            ],
        },
        "bracketPrediction": {
            "status": "EXPERIMENTAL_ACTIVE_ABSTRACTION",
            "modelVersion": "bracket-path-ppr-v1",
            "activeFeature": "calculatedPprDelta",
            "reason": (
                "Bracket paths use the validated PPR matchup probability at each "
                "simulated game. ACL advancement links are unavailable, so v1 uses "
                "a disclosed seeded single-elimination abstraction."
            ),
            "ratingWeights": {
                key: 0.0 for key in ratings
            },
        },
        "profileRatings": ratings,
        "rule": (
            "A profile rating receives nonzero game or bracket weight only after "
            "chronological out-of-sample testing improves both probability quality "
            "and the relevant prediction objective."
        ),
    }


def _zero(status: str, evidence: str) -> dict[str, Any]:
    return {
        "profileStatus": "ACTIVE_PROFILE_RATING",
        "gamePredictionWeight": 0.0,
        "bracketPredictionWeight": 0.0,
        "predictiveStatus": status,
        "evidence": evidence,
    }
