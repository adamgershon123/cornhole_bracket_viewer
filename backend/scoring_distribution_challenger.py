from __future__ import annotations

import math
from typing import Any


MODEL_VERSION = "nonlinear-scoring-distribution-v2"
FEATURE_NAMES = (
    "calculatedPpr",
    "calculatedPprSignedSquare",
    "ceilingRate",
    "ceilingRateSignedSquare",
    "floorAvoidance",
    "floorAvoidanceSignedSquare",
    "calculatedDpr",
    "calculatedDprSignedSquare",
)
MEANS = (
    -0.002124505395683454,
    0.011759242621402873,
    -0.00014627676095818203,
    0.00008573800603320567,
    -0.0034831601565292873,
    -0.000591860262470467,
    -0.00845499865561626,
    -0.010590379842005905,
)
SCALES = (
    0.8376230650305949,
    1.2787298647138303,
    0.09515105661847445,
    0.016733551039981753,
    0.1161228956040357,
    0.026033517693618793,
    0.5282604366767127,
    0.5115367136543355,
)
WEIGHTS = (
    0.1826782116785589,
    -0.04775946046135251,
    0.19094606039196327,
    0.048649878974731685,
    0.31245919731156335,
    0.20321157282745317,
    0.4756971747225877,
    0.01833944942306979,
)
INTERCEPT = 0.024533632861102377
VALIDATION = {
    "policy": "ROLLING_ORIGIN_COMMON_SAMPLE",
    "sourceMatchups": 4012,
    "commonEligibleMatchups": 2223,
    "testMatchups": 2148,
    "coverageRate": 0.554088,
    "pprOnlyAccuracy": 0.658752,
    "challengerAccuracy": 0.694134,
    "pprOnlyBrier": 0.211733,
    "challengerBrier": 0.200957,
    "pprOnlyLogLoss": 0.611158,
    "challengerLogLoss": 0.58667,
    "trainingMatchups": 2224,
}
PROFILE_FACTOR_POLICY = {
    "weighted": [
        {
            "factor": "Expected performance",
            "feature": "calculatedPpr",
            "status": "VALIDATED",
        },
        {
            "factor": "Scoring ceiling",
            "feature": "ceilingRate",
            "status": "VALIDATED",
        },
        {
            "factor": "Floor avoidance",
            "feature": "floorAvoidance",
            "status": "VALIDATED",
        },
        {
            "factor": "Point differential",
            "feature": "calculatedDpr",
            "status": "VALIDATED",
        },
    ],
    "selectionObjective": (
        "MAXIMIZE_ACCURACY_SUBJECT_TO_IMPROVED_BRIER_AND_LOG_LOSS"
    ),
    "promotionStatus": "PROSPECTIVE_SHADOW_ACTIVE",
}


def score_scoring_distribution_challenger(
    matchup: dict[str, Any],
) -> dict[str, Any]:
    deltas = matchup.get("deltasAminusB") or {}
    base_values = {
        "calculatedPpr": deltas.get("calculatedPpr"),
        "ceilingRate": deltas.get("ceilingRate"),
        "floorAvoidance": deltas.get("floorAvoidance"),
        "calculatedDpr": deltas.get("calculatedDpr"),
    }
    if any(value is None for value in base_values.values()):
        return {
            "modelVersion": MODEL_VERSION,
            "status": "ABSTAINED",
            "reason": "One or more nonlinear scoring-distribution features are unavailable.",
            "validation": VALIDATION,
            "factorPolicy": PROFILE_FACTOR_POLICY,
        }
    values = []
    for name in ("calculatedPpr", "ceilingRate", "floorAvoidance", "calculatedDpr"):
        value = float(base_values[name])
        values.extend((value, value * abs(value)))
    contributions = {
        name: round(
            weight * ((float(value) - center) / scale),
            6,
        )
        for name, value, center, scale, weight in zip(
            FEATURE_NAMES, values, MEANS, SCALES, WEIGHTS
        )
    }
    probability = _sigmoid(INTERCEPT + sum(contributions.values()))
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
