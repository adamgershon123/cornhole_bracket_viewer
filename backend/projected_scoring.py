from __future__ import annotations

import math
import random
import sqlite3
from dataclasses import dataclass
from statistics import mean, median
from typing import Any


SCORING_MODEL_VERSION = "empirical-finish-margin-v1"


@dataclass(frozen=True)
class ScoreCalibration:
    sample_size: int
    average_winner_score: float
    average_loser_score: float
    average_margin: float
    median_margin: float
    margin_deviation: float


def load_score_calibration(
    conn: sqlite3.Connection,
    *,
    cutoff_date: str,
) -> ScoreCalibration:
    """Load one cutoff-safe scoring calibration for an entire bracket run."""
    rows = conn.execute(
        """
        SELECT g.home_score, g.away_score
        FROM games g
        JOIN events e ON e.event_id=g.event_id
        WHERE g.completed=1
          AND g.home_score IS NOT NULL
          AND g.away_score IS NOT NULL
          AND g.home_score != g.away_score
          AND e.event_date IS NOT NULL
          AND e.event_date < ?
          AND g.home_score BETWEEN 0 AND 50
          AND g.away_score BETWEEN 0 AND 50
        """,
        (cutoff_date,),
    ).fetchall()
    winners = [float(max(row[0], row[1])) for row in rows]
    losers = [float(min(row[0], row[1])) for row in rows]
    margins = [winner - loser for winner, loser in zip(winners, losers)]
    if not margins:
        return ScoreCalibration(0, 21.0, 14.0, 7.0, 7.0, 4.0)
    average_margin = mean(margins)
    variance = mean((value - average_margin) ** 2 for value in margins)
    return ScoreCalibration(
        sample_size=len(margins),
        average_winner_score=mean(winners),
        average_loser_score=mean(losers),
        average_margin=average_margin,
        median_margin=median(margins),
        margin_deviation=max(1.0, math.sqrt(variance)),
    )


def projected_score(
    side_a_probability: float,
    calibration: ScoreCalibration,
) -> dict[str, Any]:
    probability = min(max(float(side_a_probability), 0.001), 0.999)
    favorite_probability = max(probability, 1.0 - probability)
    expected_margin = _expected_margin(favorite_probability, calibration)
    winner_score = max(1, int(round(calibration.average_winner_score)))
    loser_score = max(0, winner_score - int(round(expected_margin)))
    side_a_favored = probability >= 0.5
    return {
        "sideAScore": winner_score if side_a_favored else loser_score,
        "sideBScore": loser_score if side_a_favored else winner_score,
        "favoriteMargin": round(expected_margin, 2),
        "modelVersion": SCORING_MODEL_VERSION,
        "calibrationSampleSize": calibration.sample_size,
    }


def sample_score(
    *,
    winner_is_side_a: bool,
    side_a_probability: float,
    calibration: ScoreCalibration,
    rng: random.Random,
) -> tuple[int, int]:
    winner_probability = (
        side_a_probability if winner_is_side_a else 1.0 - side_a_probability
    )
    expected_margin = _expected_margin(max(0.5, winner_probability), calibration)
    sampled_margin = max(
        1,
        int(round(rng.gauss(expected_margin, calibration.margin_deviation * 0.45))),
    )
    winner_score = max(
        1,
        int(round(rng.gauss(calibration.average_winner_score, 0.75))),
    )
    loser_score = max(0, winner_score - sampled_margin)
    return (
        (winner_score, loser_score)
        if winner_is_side_a else
        (loser_score, winner_score)
    )


def _expected_margin(
    favorite_probability: float,
    calibration: ScoreCalibration,
) -> float:
    # At 50/50, close games should be more common but not assumed to finish by
    # exactly one. Confidence then expands the margin toward the archive's
    # typical decisive result. The archive controls the scale and score level.
    confidence = min(max((favorite_probability - 0.5) / 0.5, 0.0), 1.0)
    close_game_margin = max(1.0, calibration.median_margin * 0.42)
    decisive_margin = max(close_game_margin, calibration.average_margin * 1.55)
    return close_game_margin + (decisive_margin - close_game_margin) * confidence
