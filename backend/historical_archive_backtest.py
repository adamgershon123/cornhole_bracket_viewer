from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from statistics import NormalDist
from typing import Any

import numpy as np

from chronological_evaluation import historical_matchups


BACKTEST_VERSION = "historical-archive-holdout-v6"
FEATURE_NAMES = ("pprDelta", "fourBaggerDelta", "bagsInDelta")
EXPECTED_FEATURE_NAMES = (
    "adjustedPprDelta",
    "recentFormDelta",
    "teamSkillGapDelta",
    "venueEffectDelta",
    "formatEffectDelta",
)


def historical_backtest_report(
    conn: sqlite3.Connection,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    _init_schema(conn)
    signature = _ledger_signature(conn)
    cached = conn.execute(
        "SELECT * FROM historical_backtest_snapshots WHERE backtest_version=?",
        (BACKTEST_VERSION,),
    ).fetchone()
    if cached and not refresh:
        payload = json.loads(cached["payload_json"])
        payload["cacheStatus"] = (
            "CURRENT" if cached["ledger_signature"] == signature else "NEW_DATA_AVAILABLE"
        )
        return payload
    payload = _run_backtest(conn)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload.update({
        "backtestVersion": BACKTEST_VERSION,
        "generatedAt": generated_at,
        "ledgerSignature": signature,
        "cacheStatus": "CURRENT",
    })
    conn.execute(
        """
        INSERT INTO historical_backtest_snapshots(
          backtest_version, ledger_signature, payload_json, generated_at
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(backtest_version) DO UPDATE SET
          ledger_signature=excluded.ledger_signature,
          payload_json=excluded.payload_json,
          generated_at=excluded.generated_at
        """,
        (BACKTEST_VERSION, signature, json.dumps(payload), generated_at),
    )
    conn.commit()
    return payload


def _run_backtest(conn: sqlite3.Connection) -> dict[str, Any]:
    matchups = historical_matchups(conn)
    examples = _cutoff_safe_examples(conn, matchups)
    dates = sorted({row["eventDate"] for row in examples})
    if len(dates) < 2:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "archiveMatchups": len(matchups),
            "eligibleMatchups": len(examples),
            "models": [],
        }
    validation_index = min(max(int(len(dates) * 0.60), 1), len(dates) - 2)
    final_index = min(max(int(len(dates) * 0.80), validation_index + 1), len(dates) - 1)
    validation_start = dates[validation_index]
    final_start = dates[final_index]
    development = [row for row in examples if row["eventDate"] < validation_start]
    validation = [row for row in examples if validation_start <= row["eventDate"] < final_start]
    holdout = [row for row in examples if row["eventDate"] >= final_start]
    model_specs = (
        ("PPR only", ("pprDelta",)),
        ("PPR + bag efficiency", FEATURE_NAMES),
        ("Reliability-adjusted PPR", ("adjustedPprDelta",)),
        ("PPR + recent form", ("pprDelta", "recentFormDelta")),
        ("PPR + round loss rate", ("pprDelta", "roundLossRateDelta")),
        ("PPR + recent round loss", ("pprDelta", "recentRoundLossDelta")),
        ("PPR + round loss + recent form", (
            "pprDelta", "roundLossRateDelta", "recentFormDelta"
        )),
        ("PPR + partner skill gap", ("pprDelta", "teamSkillGapDelta")),
        ("PPR + venue effect", ("pprDelta", "venueEffectDelta")),
        ("PPR + format effect", ("pprDelta", "formatEffectDelta")),
        ("Expected performance challenger", EXPECTED_FEATURE_NAMES),
    )
    models = []
    final_predictions: dict[str, list[dict[str, Any]]] = {}
    validation_predictions_by_model: dict[str, list[dict[str, Any]]] = {}
    for label, features in model_specs:
        fitted = _fit_logistic(development, features)
        validation_predictions = _predict(validation, fitted)
        predictions = _predict(holdout, fitted)
        final_predictions[label] = predictions
        validation_predictions_by_model[label] = validation_predictions
        models.append({
            "model": label,
            "features": list(features),
            "developmentMatchups": len(development),
            **_metrics(predictions, len(holdout)),
            "validationMetrics": _metrics(validation_predictions, len(validation)),
            "finalTimeSegments": _time_segment_metrics(holdout, predictions, segments=4),
            "parameters": fitted,
        })
    baseline_final = final_predictions.get("PPR only") or []
    baseline_validation = validation_predictions_by_model.get("PPR only") or []
    for model in models:
        label = str(model["model"])
        if label == "PPR only":
            continue
        model["pairedVsPpr"] = {
            "validation": _paired_comparison(
                baseline_validation, validation_predictions_by_model.get(label) or []
            ),
            "finalTest": _paired_comparison(
                baseline_final, final_predictions.get(label) or []
            ),
        }
    equal = [
        {"probability": 0.5, "outcome": int(row["sideAWon"])}
        for row in holdout
    ]
    models.insert(0, {
        "model": "Equal odds",
        "features": [],
        "developmentMatchups": 0,
        **_metrics(equal, len(holdout)),
    })
    return {
        "status": "COMPLETE",
        "methodology": "CHRONOLOGICAL_60_20_20",
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE_365_DAY_WINDOW",
        "archiveMatchups": len(matchups),
        "eligibleMatchups": len(examples),
        "excludedMatchups": len(matchups) - len(examples),
        "eventDates": len(dates),
        "developmentMatchups": len(development),
        "validationMatchups": len(validation),
        "validationStartDate": validation_start,
        "holdoutMatchups": len(holdout),
        "holdoutStartDate": final_start,
        "models": models,
        "notes": [
            "All games on an event date remain entirely in development or holdout.",
            "Every player feature uses only rounds dated before the target event.",
            "The middle 20% of dates validates challengers; the final 20% is an untouched final test.",
        ],
    }


def _cutoff_safe_examples(
    conn: sqlite3.Connection,
    matchups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    daily_rows = conn.execute(
        """
        SELECT player_id, event_date, COALESCE(location_id, '') AS location_id,
               COALESCE(match_type, 'UNKNOWN') AS match_type,
               COUNT(*) AS rounds,
               SUM(COALESCE(gross_points, 0)) AS gross,
               SUM(COALESCE(four_bagger, 0)) AS four_baggers,
               SUM(COALESCE(bags_in, 0)) AS bags_in,
               SUM(COALESCE(bags_on, 0)) AS bags_on,
               SUM(COALESCE(bags_off, 0)) AS bags_off,
               SUM(CASE WHEN UPPER(COALESCE(round_result, ''))='L' THEN 1 ELSE 0 END) AS losses
        FROM player_rounds
        WHERE event_date IS NOT NULL
        GROUP BY player_id, event_date, COALESCE(location_id, ''), COALESCE(match_type, 'UNKNOWN')
        ORDER BY event_date, player_id
        """
    ).fetchall()
    additions: dict[str, list[tuple[int, tuple[int, ...], str, str]]] = defaultdict(list)
    for row in daily_rows:
        additions[str(row["event_date"])].append((
            int(row["player_id"]),
            tuple(int(row[key] or 0) for key in (
                "rounds", "gross", "four_baggers", "bags_in", "bags_on", "bags_off", "losses"
            )),
            str(row["location_id"] or ""),
            str(row["match_type"] or "UNKNOWN").upper(),
        ))
    ordered_dates = sorted(additions)
    histories: dict[int, deque[tuple[date, tuple[int, ...], str, str]]] = defaultdict(deque)
    totals: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0])
    date_index = 0
    examples = []
    for matchup in matchups:
        event_date = str(matchup["eventDate"])
        target_date = date.fromisoformat(event_date)
        while date_index < len(ordered_dates) and ordered_dates[date_index] < event_date:
            source_date = ordered_dates[date_index]
            parsed_date = date.fromisoformat(source_date)
            for player_id, values, location_id, match_type in additions[source_date]:
                histories[player_id].append((parsed_date, values, location_id, match_type))
                for index, value in enumerate(values):
                    totals[player_id][index] += value
            date_index += 1
        player_ids = set(matchup["sideAPlayerIds"] + matchup["sideBPlayerIds"])
        threshold = target_date - timedelta(days=365)
        for player_id in player_ids:
            history = histories[player_id]
            while history and history[0][0] < threshold:
                _, values, _, _ = history.popleft()
                for index, value in enumerate(values):
                    totals[player_id][index] -= value
        side_a = _side_features(matchup["sideAPlayerIds"], totals)
        side_b = _side_features(matchup["sideBPlayerIds"], totals)
        if side_a is None or side_b is None:
            continue
        population_rounds = sum(value[0] for value in totals.values())
        population_ppr = (
            sum(value[1] for value in totals.values()) / population_rounds
            if population_rounds else 7.0
        )
        event_context = conn.execute(
            "SELECT COALESCE(location_id, ''), COALESCE(match_type, 'UNKNOWN') FROM events WHERE event_id=?",
            (int(matchup["eventId"]),),
        ).fetchone()
        location_id = str(event_context[0] or "") if event_context else ""
        match_type = str(event_context[1] or "UNKNOWN").upper() if event_context else "UNKNOWN"
        context_a = _side_context_features(
            matchup["sideAPlayerIds"], histories, totals, population_ppr,
            target_date, location_id, match_type,
        )
        context_b = _side_context_features(
            matchup["sideBPlayerIds"], histories, totals, population_ppr,
            target_date, location_id, match_type,
        )
        examples.append({
            **matchup,
            "features": {
                "pprDelta": side_a["ppr"] - side_b["ppr"],
                "fourBaggerDelta": side_a["fourBaggerRate"] - side_b["fourBaggerRate"],
                "bagsInDelta": side_a["bagsInRate"] - side_b["bagsInRate"],
                "adjustedPprDelta": context_a["adjustedPpr"] - context_b["adjustedPpr"],
                "recentFormDelta": context_a["recentEffect"] - context_b["recentEffect"],
                "roundLossRateDelta": context_a["roundLossRate"] - context_b["roundLossRate"],
                "recentRoundLossDelta": context_a["recentRoundLossEffect"] - context_b["recentRoundLossEffect"],
                "teamSkillGapDelta": context_a["skillGap"] - context_b["skillGap"],
                "venueEffectDelta": context_a["venueEffect"] - context_b["venueEffect"],
                "formatEffectDelta": context_a["formatEffect"] - context_b["formatEffect"],
            },
        })
    return examples


def _side_context_features(
    player_ids: list[int],
    histories: dict[int, deque[tuple[date, tuple[int, ...], str, str]]],
    totals: dict[int, list[int]],
    population_ppr: float,
    target_date: date,
    location_id: str,
    match_type: str,
) -> dict[str, float]:
    adjusted = []
    raw_pprs = []
    recent_effects = []
    loss_rates = []
    recent_loss_effects = []
    venue_effects = []
    format_effects = []
    recent_start = target_date - timedelta(days=90)
    for player_id in player_ids:
        total = totals[int(player_id)]
        base_ppr = total[1] / total[0]
        reliability = total[0] / (total[0] + 30.0)
        adjusted.append(reliability * base_ppr + (1.0 - reliability) * population_ppr)
        raw_pprs.append(base_ppr)
        recent_rounds = recent_gross = 0
        recent_losses = 0
        venue_rounds = venue_gross = 0
        format_rounds = format_gross = 0
        for event_day, values, row_location, row_format in histories[int(player_id)]:
            if event_day >= recent_start:
                recent_rounds += values[0]
                recent_gross += values[1]
                recent_losses += values[6]
            if location_id and row_location == location_id:
                venue_rounds += values[0]
                venue_gross += values[1]
            if row_format == match_type:
                format_rounds += values[0]
                format_gross += values[1]
        recent_effects.append(_shrunk_effect(recent_gross, recent_rounds, base_ppr))
        base_loss_rate = total[6] / total[0]
        loss_rates.append(base_loss_rate)
        recent_loss_effects.append(
            _shrunk_rate_effect(recent_losses, recent_rounds, base_loss_rate)
        )
        venue_effects.append(_shrunk_effect(venue_gross, venue_rounds, base_ppr))
        format_effects.append(_shrunk_effect(format_gross, format_rounds, base_ppr))
    return {
        "adjustedPpr": mean(adjusted),
        "recentEffect": mean(recent_effects),
        "roundLossRate": mean(loss_rates),
        "recentRoundLossEffect": mean(recent_loss_effects),
        "skillGap": max(raw_pprs) - min(raw_pprs) if len(raw_pprs) > 1 else 0.0,
        "venueEffect": mean(venue_effects),
        "formatEffect": mean(format_effects),
    }


def _shrunk_effect(gross: int, rounds: int, baseline: float) -> float:
    if rounds <= 0:
        return 0.0
    reliability = rounds / (rounds + 30.0)
    return reliability * ((gross / rounds) - baseline)


def _shrunk_rate_effect(count: int, rounds: int, baseline: float) -> float:
    if rounds <= 0:
        return 0.0
    reliability = rounds / (rounds + 30.0)
    return reliability * ((count / rounds) - baseline)


def _side_features(player_ids: list[int], totals: dict[int, list[int]]) -> dict[str, float] | None:
    player_pprs = []
    rounds = gross = four_baggers = bags_in = total_bags = 0
    for player_id in player_ids:
        values = totals[int(player_id)]
        if values[0] <= 0:
            return None
        player_pprs.append(values[1] / values[0])
        rounds += values[0]
        gross += values[1]
        four_baggers += values[2]
        bags_in += values[3]
        total_bags += values[3] + values[4] + values[5]
    if not rounds or not total_bags:
        return None
    return {
        "ppr": mean(player_pprs),
        "fourBaggerRate": four_baggers / rounds,
        "bagsInRate": bags_in / total_bags,
    }


def _fit_logistic(examples: list[dict[str, Any]], features: tuple[str, ...]) -> dict[str, Any]:
    matrix = np.asarray([
        [float(row["features"][feature]) for feature in features]
        for row in examples
    ], dtype=float)
    outcomes = np.asarray([float(row["sideAWon"]) for row in examples], dtype=float)
    centers = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales == 0] = 1.0
    standardized = (matrix - centers) / scales
    weights = np.zeros(len(features), dtype=float)
    intercept = 0.0
    for _ in range(800):
        logits = np.clip(intercept + standardized @ weights, -35, 35)
        predictions = 1.0 / (1.0 + np.exp(-logits))
        errors = predictions - outcomes
        intercept -= 0.08 * float(errors.mean())
        weights -= 0.08 * ((standardized.T @ errors + 0.1 * weights) / len(outcomes))
    return {
        "featureNames": list(features),
        "centers": centers.tolist(),
        "scales": scales.tolist(),
        "weights": weights.tolist(),
        "intercept": intercept,
        "developmentExamples": len(examples),
    }


def _predict(examples: list[dict[str, Any]], model: dict[str, Any]) -> list[dict[str, Any]]:
    features = model["featureNames"]
    centers = model["centers"]
    scales = model["scales"]
    weights = model["weights"]
    rows = []
    for example in examples:
        standardized = [
            (float(example["features"][feature]) - center) / scale
            for feature, center, scale in zip(features, centers, scales)
        ]
        logit = float(model["intercept"]) + sum(
            weight * value for weight, value in zip(weights, standardized)
        )
        probability = 1.0 / (1.0 + math.exp(-max(min(logit, 35), -35)))
        rows.append({"probability": probability, "outcome": int(example["sideAWon"])})
    return rows


def _metrics(predictions: list[dict[str, Any]], total: int) -> dict[str, Any]:
    if not predictions:
        return {"evaluatedMatchups": 0, "coverageRate": 0, "accuracy": None,
                "brierScore": None, "logLoss": None}
    return {
        "evaluatedMatchups": len(predictions),
        "coverageRate": round(len(predictions) / total, 6) if total else 0,
        "accuracy": round(mean(
            int((row["probability"] >= 0.5) == bool(row["outcome"]))
            for row in predictions
        ), 6),
        "brierScore": round(mean(
            (row["probability"] - row["outcome"]) ** 2 for row in predictions
        ), 6),
        "logLoss": round(mean(
            -(row["outcome"] * math.log(max(row["probability"], 1e-15))
              + (1 - row["outcome"]) * math.log(max(1 - row["probability"], 1e-15)))
            for row in predictions
        ), 6),
    }


def _paired_comparison(
    baseline: list[dict[str, Any]],
    challenger: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not baseline or len(baseline) != len(challenger):
        return None
    challenger_only = baseline_only = 0
    for base, candidate in zip(baseline, challenger):
        outcome = bool(base["outcome"])
        base_correct = (float(base["probability"]) >= 0.5) == outcome
        candidate_correct = (float(candidate["probability"]) >= 0.5) == outcome
        if candidate_correct and not base_correct:
            challenger_only += 1
        elif base_correct and not candidate_correct:
            baseline_only += 1
    disagreements = challenger_only + baseline_only
    if not disagreements:
        p_value = 1.0
    else:
        z = (abs(challenger_only - baseline_only) - 1.0) / math.sqrt(disagreements)
        p_value = 2.0 * (1.0 - NormalDist().cdf(max(z, 0.0)))
    return {
        "challengerOnlyCorrect": challenger_only,
        "pprOnlyCorrect": baseline_only,
        "netAdditionalCorrect": challenger_only - baseline_only,
        "disagreements": disagreements,
        "mcnemarPValueApprox": round(min(max(p_value, 0.0), 1.0), 6),
        "statisticallyClearAt95": p_value < 0.05,
    }


def _time_segment_metrics(
    examples: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    segments: int,
) -> list[dict[str, Any]]:
    if not examples or len(examples) != len(predictions) or segments <= 0:
        return []
    dates = sorted({str(row["eventDate"]) for row in examples})
    output = []
    for index in range(segments):
        start_index = int(len(dates) * index / segments)
        end_index = int(len(dates) * (index + 1) / segments)
        selected_dates = set(dates[start_index:end_index])
        selected = [
            prediction
            for example, prediction in zip(examples, predictions)
            if str(example["eventDate"]) in selected_dates
        ]
        if not selected:
            continue
        output.append({
            "segment": index + 1,
            "startDate": dates[start_index],
            "endDate": dates[end_index - 1],
            **_metrics(selected, len(selected)),
        })
    return output


def _ledger_signature(conn: sqlite3.Connection) -> str:
    games = int(conn.execute("SELECT COUNT(*) FROM games").fetchone()[0])
    rounds = int(conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0])
    return f"games:{games}:rounds:{rounds}"


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS historical_backtest_snapshots(
          backtest_version TEXT PRIMARY KEY,
          ledger_signature TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          generated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
