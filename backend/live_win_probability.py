from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Iterable

MODEL_VERSION = "live-round-bootstrap-v2"
FIRST_THROW_NET_EDGE = 0.176857
DEFAULT_GROSS_POINTS = [0, 1, 2, 3, 4, 5, 6, 6, 7, 7, 8, 8, 8, 9, 9, 10, 10, 11, 12]


def calculate_probability_series(
    rounds: Iterable[dict[str, Any]], *, top_team_id: str, bottom_team_id: str,
    pregame_top_probability: float = 0.5,
    top_gross_samples: Iterable[int | float] = (),
    bottom_gross_samples: Iterable[int | float] = (),
    simulations: int = 10_000, seed_key: str = "",
    first_throw_net_edge: float = FIRST_THROW_NET_EDGE,
) -> dict[str, Any]:
    top_samples = _samples(top_gross_samples)
    bottom_samples = _samples(bottom_gross_samples)
    prior = min(max(float(pregame_top_probability), 0.01), 0.99)
    # Simulated continuation outcomes are converted into relative game-state
    # evidence and anchored to the locked pregame probability. This prevents
    # historical round samples from resetting or double-counting the pregame prior.
    baseline_raw = _simulate_state(
        0, 0, top_samples, bottom_samples, 0.0, simulations,
        _seed(seed_key, -1), None, str(top_team_id), str(bottom_team_id),
        first_throw_net_edge,
    )
    points = [{
        "round": 0, "topScore": 0, "bottomScore": 0,
        "topWinProbability": round(prior, 4),
        "bottomWinProbability": round(1.0 - prior, 4),
        "firstThrowTeamId": None, "firstThrowPlayerId": None,
        "probabilityChange": None, "status": "PREGAME",
    }]
    previous = prior
    for row in sorted(rounds, key=lambda item: int(item.get("round") or 0)):
        state = row.get("gameState") or {}
        scores = state.get("scoreAfter") or {}
        top_score = int(scores.get(str(top_team_id), 0) or 0)
        bottom_score = int(scores.get(str(bottom_team_id), 0) or 0)
        probability = _simulate_state(
            top_score, bottom_score, top_samples, bottom_samples,
            0.0, simulations, _seed(seed_key, int(row.get("round") or 0)),
            state.get("nextFirstThrowTeamId"), str(top_team_id), str(bottom_team_id),
            first_throw_net_edge,
        )
        probability = _anchor_probability(
            raw_probability=probability,
            raw_baseline=baseline_raw,
            pregame_probability=prior,
        )
        if top_score >= 21 or bottom_score >= 21:
            probability = 1.0 if top_score > bottom_score else 0.0
        points.append({
            "round": int(row.get("round") or 0),
            "topScore": top_score, "bottomScore": bottom_score,
            "topWinProbability": round(probability, 4),
            "bottomWinProbability": round(1.0 - probability, 4),
            "firstThrowTeamId": state.get("nextFirstThrowTeamId"),
            "firstThrowPlayerId": state.get("nextFirstThrowPlayerId"),
            "firstThrowTeamStatus": state.get("nextFirstThrowTeamStatus"),
            "firstThrowPlayerStatus": state.get("nextFirstThrowPlayerStatus"),
            "probabilityChange": round(probability - previous, 4),
            "status": "FINAL" if top_score >= 21 or bottom_score >= 21 else "LIVE",
        })
        previous = probability
    return {
        "modelVersion": MODEL_VERSION, "simulationCount": int(simulations),
        "pregameTopProbability": round(prior, 4),
        "firstThrowWeight": round(first_throw_net_edge, 6),
        "firstThrowWeightStatus": "CHRONOLOGICAL_HOLDOUT_SUPPORTED",
        "topHistoricalSamples": len(top_samples),
        "bottomHistoricalSamples": len(bottom_samples),
        "rawSimulationBaseline": round(baseline_raw, 4),
        "calibration": "PREGAME_LOG_ODDS_ANCHOR",
        "points": points,
    }


def _simulate_state(top: int, bottom: int, top_samples: list[int],
                    bottom_samples: list[int], shift: float,
                    simulations: int, seed: int,
                    first_team: str | None, top_team_id: str,
                    bottom_team_id: str, first_throw_edge: float) -> float:
    if top >= 21 or bottom >= 21:
        return 1.0 if top > bottom else 0.0
    rng = random.Random(seed)
    wins = 0
    for _ in range(max(simulations, 1)):
        a, b = top, bottom
        owner = first_team or (top_team_id if rng.random() < 0.5 else bottom_team_id)
        for _round in range(100):
            owner_shift = first_throw_edge if owner == top_team_id else -first_throw_edge
            difference = (rng.choice(top_samples) + shift / 2) - (rng.choice(bottom_samples) - shift / 2) + owner_shift
            if difference >= 0.5:
                a += max(1, min(12, int(round(difference))))
                owner = top_team_id
            elif difference <= -0.5:
                b += max(1, min(12, int(round(-difference))))
                owner = bottom_team_id
            if a >= 21 or b >= 21:
                wins += int(a > b)
                break
        else:
            wins += int(a > b)
    return wins / max(simulations, 1)


def _samples(values: Iterable[int | float]) -> list[int]:
    result = [max(0, min(12, int(round(float(value))))) for value in values if value is not None]
    return result or list(DEFAULT_GROSS_POINTS)


def _anchor_probability(
    *,
    raw_probability: float,
    raw_baseline: float,
    pregame_probability: float,
) -> float:
    epsilon = 1e-6
    raw = min(max(float(raw_probability), epsilon), 1.0 - epsilon)
    baseline = min(max(float(raw_baseline), epsilon), 1.0 - epsilon)
    prior = min(max(float(pregame_probability), epsilon), 1.0 - epsilon)
    relative_log_odds = math.log(raw / (1.0 - raw)) - math.log(
        baseline / (1.0 - baseline)
    )
    anchored_log_odds = math.log(prior / (1.0 - prior)) + relative_log_odds
    if anchored_log_odds >= 0:
        return 1.0 / (1.0 + math.exp(-anchored_log_odds))
    exp_value = math.exp(anchored_log_odds)
    return exp_value / (1.0 + exp_value)


def _seed(key: str, round_number: int) -> int:
    value = f"{key}:{round_number}:{MODEL_VERSION}".encode()
    return int(hashlib.sha256(value).hexdigest()[:16], 16)
