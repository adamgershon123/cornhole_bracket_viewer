from __future__ import annotations

import math
from typing import Any


MODEL_VERSION = "ppr-round-loss-recent-form-v1"
FEATURE_NAMES = ("predictivePpr", "roundLossRate", "recent90PprEffect")
CENTERS = (0.0473248418026347, -0.0013545632332537263, 0.0008447125446182177)
SCALES = (1.0324621420111433, 0.13123953811320438, 0.09919805430118292)
WEIGHTS = (1.0357219264098168, -0.06964721628149495, 0.038618121120192965)
INTERCEPT = 0.03837927072432058

VALIDATION = {
    "policy": "CHRONOLOGICAL_60_20_20_STRICT_PRIOR_DATE",
    "developmentMatchups": 7882,
    "validationMatchups": 3145,
    "finalTestMatchups": 4344,
    "pprOnlyValidationAccuracy": 0.682989,
    "challengerValidationAccuracy": 0.686169,
    "pprOnlyFinalAccuracy": 0.679328,
    "challengerFinalAccuracy": 0.682090,
    "netAdditionalFinalCorrect": 12,
    "promotionStatus": "PROSPECTIVE_SHADOW_ACTIVE",
}

PROFILE_FACTOR_POLICY = {
    "weighted": [
        {"factor": "PPR", "feature": "predictivePpr", "status": "BASELINE"},
        {"factor": "Round-loss rate", "feature": "roundLossRate", "status": "HISTORICAL_CHALLENGER"},
        {"factor": "Recent form", "feature": "recent90PprEffect", "status": "HISTORICAL_CHALLENGER"},
    ],
    "promotionStatus": "PROSPECTIVE_SHADOW_ACTIVE_ZERO_PRODUCTION_WEIGHT",
    "promotionRule": (
        "Must outperform PPR on prospectively frozen common-sample predictions "
        "before receiving production weight."
    ),
}


def score_round_loss_recent_challenger(matchup: dict[str, Any]) -> dict[str, Any]:
    deltas = matchup.get("deltasAminusB") or {}
    values = [deltas.get(name) for name in FEATURE_NAMES]
    if any(value is None for value in values):
        return {
            "modelVersion": MODEL_VERSION,
            "status": "ABSTAINED",
            "reason": "PPR, round-loss rate, or recent-form history is unavailable.",
            "validation": VALIDATION,
            "factorPolicy": PROFILE_FACTOR_POLICY,
        }
    contributions = {
        name: round(weight * ((float(value) - center) / scale), 6)
        for name, value, center, scale, weight in zip(
            FEATURE_NAMES, values, CENTERS, SCALES, WEIGHTS
        )
    }
    logit = INTERCEPT + sum(contributions.values())
    probability = 1.0 / (1.0 + math.exp(-max(min(logit, 35), -35)))
    return {
        "modelVersion": MODEL_VERSION,
        "status": "PREDICTED",
        "sideAProbability": round(probability, 6),
        "sideBProbability": round(1.0 - probability, 6),
        "featureValues": {
            name: round(float(value), 6) for name, value in zip(FEATURE_NAMES, values)
        },
        "featureContributions": contributions,
        "validation": VALIDATION,
        "factorPolicy": PROFILE_FACTOR_POLICY,
    }
