from __future__ import annotations

import math
from typing import Any


MODEL_VERSION = "bag-efficiency-challenger-v1"
FEATURE_NAMES = (
    "predictivePpr",
    "fourBaggerRate",
    "bagsInRate",
)
MEANS = (0.0198125926, 0.0043749985, 0.0031266441)
SCALES = (0.7449174464, 0.0525767860, 0.0808420435)
WEIGHTS = (0.4411613808, 0.4017505353, 0.2685000859)
INTERCEPT = 0.0621826529
VALIDATION = {
    "policy": "ROLLING_ORIGIN_COMMON_SAMPLE",
    "testMatchups": 381,
    "developmentExamples": 405,
    "pprOnlyBrier": 0.215524,
    "challengerBrier": 0.212235,
    "pprOnlyLogLoss": 0.623167,
    "challengerLogLoss": 0.615287,
    "pprOnlyAccuracy": 0.661417,
    "challengerAccuracy": 0.661417,
}
PROFILE_FACTOR_POLICY = {
    "weighted": [
        {
            "factor": "Expected performance",
            "feature": "predictivePpr",
            "status": "VALIDATED",
            "reason": "Core pre-match performance signal.",
        },
        {
            "factor": "Four-bagger rate",
            "feature": "fourBaggerRate",
            "status": "VALIDATED",
            "reason": "Improved common-sample Brier score and log loss with bag efficiency.",
        },
        {
            "factor": "Bags-in rate",
            "feature": "bagsInRate",
            "status": "VALIDATED",
            "reason": "Improved common-sample Brier score and log loss with bag efficiency.",
        },
    ],
    "validatedAlternatives": [
        {
            "factor": "Scoring distribution",
            "features": ["ceilingRate", "floorAvoidance", "dpr"],
            "status": "VALIDATED_STANDALONE_SHADOW",
            "reason": (
                "Improved Brier score, log loss, and accuracy versus PPR-only, "
                "but combining it with bag efficiency was worse than bag efficiency alone."
            ),
            "historicalMetrics": {
                "matchups": 381,
                "brierScore": 0.213115,
                "logLoss": 0.616982,
                "accuracy": 0.677165,
            },
        }
    ],
    "shadowOnlyZeroWeight": [
        {
            "factor": "Current form",
            "status": "AWAITING_INCREMENTAL_VALIDATION",
        },
        {
            "factor": "Consistency",
            "status": "AWAITING_INCREMENTAL_VALIDATION",
        },
        {
            "factor": "Opponent-adjusted performance",
            "status": "AWAITING_COMMON_SAMPLE_VALIDATION",
        },
        {
            "factor": "Strength of competition",
            "status": "AWAITING_COMMON_SAMPLE_VALIDATION",
        },
        {
            "factor": "Partner compatibility and carry performance",
            "status": "AWAITING_INCREMENTAL_VALIDATION",
        },
        {
            "factor": "Clutch performance",
            "status": "DESCRIPTIVE_PENDING_SAMPLE",
        },
        {
            "factor": "Large-swing avoidance and resilience",
            "status": "DESCRIPTIVE_PENDING_SAMPLE",
        },
    ],
    "promotionRule": (
        "A factor receives nonzero prediction weight only after improving both "
        "Brier score and log loss on a cutoff-safe common chronological sample."
    ),
    "historicalDecision": {
        "sample": "381 rolling-origin test matchups from 405 common-eligible matchups",
        "selected": "PPR_PLUS_BAG_EFFICIENCY",
        "rejectedForNow": [
            "currentForm",
            "consistency",
            "teamBalance",
            "carryDynamics",
            "bagEfficiencyPlusScoringDistribution",
        ],
    },
    "historicalSpecialtyTests": {
        "swingPerformance": {
            "status": "REJECTED_FOR_NOW",
            "sourceMatchups": 1264,
            "commonEligibleMatchups": 208,
            "rollingTestMatchups": 188,
            "bestSwingCandidate": "PPR_PLUS_SWING_EXPOSURE",
            "commonSample": {
                "pprOnly": {
                    "accuracy": 0.680851,
                    "brierScore": 0.209700,
                    "logLoss": 0.613666,
                },
                "bagEfficiency": {
                    "accuracy": 0.691489,
                    "brierScore": 0.210074,
                    "logLoss": 0.614022,
                },
                "pprPlusSwingExposure": {
                    "accuracy": 0.654255,
                    "brierScore": 0.211791,
                    "logLoss": 0.615031,
                },
            },
            "tested": [
                "avoidance",
                "resilience",
                "surprise",
                "exposure",
                "recovery",
                "allSwing",
                "bagEfficiencyPlusAllSwing",
            ],
            "decision": (
                "Keep swing ratings descriptive. No swing candidate improved both "
                "Brier score and log loss, and every swing candidate reduced accuracy "
                "on the common rolling-origin sample."
            ),
        }
    },
}


def score_advanced_challenger(matchup: dict[str, Any]) -> dict[str, Any]:
    deltas = matchup.get("deltasAminusB") or {}
    values = [deltas.get(name) for name in FEATURE_NAMES]
    if any(value is None for value in values):
        return {
            "modelVersion": MODEL_VERSION,
            "status": "ABSTAINED",
            "reason": "One or more validated bag-efficiency features are unavailable.",
            "validation": VALIDATION,
            "factorPolicy": PROFILE_FACTOR_POLICY,
        }
    contributions = {
        name: round(
            weight * ((float(value) - mean) / scale),
            6,
        )
        for name, value, mean, scale, weight in zip(
            FEATURE_NAMES, values, MEANS, SCALES, WEIGHTS
        )
    }
    logit = INTERCEPT + sum(contributions.values())
    probability = _sigmoid(logit)
    return {
        "modelVersion": MODEL_VERSION,
        "status": "PREDICTED",
        "sideAProbability": round(probability, 6),
        "sideBProbability": round(1.0 - probability, 6),
        "featureValues": {
            name: round(float(value), 6)
            for name, value in zip(FEATURE_NAMES, values)
        },
        "featureContributions": contributions,
        "validation": VALIDATION,
        "factorPolicy": PROFILE_FACTOR_POLICY,
    }


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)
