from __future__ import annotations

from typing import Any


def model_research_report(
    performance: dict[str, Any],
    learning: dict[str, Any],
    collection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn model-evaluation output into an honest, readable research snapshot."""
    backtest = performance.get("historicalBacktest") or {}
    replay = performance.get("historicalTournamentReplay") or {}
    models = [dict(row) for row in (backtest.get("models") or [])]
    ppr = next((row for row in models if row.get("model") == "PPR only"), None)
    challengers = [
        row for row in models
        if row.get("model") not in {"Equal odds", "PPR only"}
    ]

    experiments = [_experiment(row, ppr) for row in models if row.get("model") != "Equal odds"]
    experiments.sort(key=lambda row: (row["role"] != "CONTROL", -(row.get("accuracy") or 0)))

    best_accuracy = _best(challengers, "accuracy", higher=True)
    best_brier = _best(challengers, "brierScore", higher=False)
    conclusive = [
        row for row in challengers
        if bool(((row.get("pairedVsPpr") or {}).get("finalTest") or {}).get("statisticallyClearAt95"))
    ]
    findings: list[dict[str, Any]] = []
    if ppr and best_accuracy:
        delta = _number(best_accuracy.get("accuracy")) - _number(ppr.get("accuracy"))
        findings.append({
            "title": "Best accuracy challenger",
            "headline": str(best_accuracy.get("model") or "Unknown"),
            "detail": (
                f"{_pct(best_accuracy.get('accuracy'))} holdout accuracy, "
                f"{_signed_points(delta)} versus PPR only."
            ),
            "tone": "POSITIVE" if delta > 0 else "CAUTION",
        })
    if ppr and best_brier:
        delta = _number(ppr.get("brierScore")) - _number(best_brier.get("brierScore"))
        findings.append({
            "title": "Best probability quality",
            "headline": str(best_brier.get("model") or "Unknown"),
            "detail": (
                f"Brier {_decimal(best_brier.get('brierScore'))}; "
                f"{_signed_decimal(delta)} improvement versus PPR. Lower is better."
            ),
            "tone": "POSITIVE" if delta > 0 else "CAUTION",
        })
    findings.append({
        "title": "Promotion confidence",
        "headline": (
            f"{len(conclusive)} challenger{'s' if len(conclusive) != 1 else ''} statistically clear"
            if conclusive else "No challenger is conclusive yet"
        ),
        "detail": (
            "A result must improve accuracy and probability quality across time before replacing PPR."
        ),
        "tone": "POSITIVE" if conclusive else "CAUTION",
    })
    findings.append({
        "title": "Evidence analyzed",
        "headline": f"{int(backtest.get('holdoutMatchups') or 0):,} held-out matches",
        "detail": (
            f"{_replay_count(replay):,} cutoff-safe tournament "
            "replays support tournament-level evaluation."
        ),
        "tone": "INFO",
    })

    gate = learning.get("promotionGate") or {}
    collection = collection or {}
    ledger = collection.get("ledger") or {}
    queue = collection.get("queue") or {}
    hourly = (collection.get("throughput") or {}).get("lastHour") or {}
    daily = (collection.get("throughput") or {}).get("last24Hours") or {}
    refresh_state = backtest.get("refreshState") or {}
    model_evaluations = sum(int(row.get("evaluatedMatchups") or 0) for row in experiments)
    return {
        "status": backtest.get("status") or "NOT_READY",
        "generatedAt": backtest.get("generatedAt"),
        "mission": "Find repeatable predictive signal beyond PPR without leaking future results.",
        "findings": findings,
        "activity": {
            "collectionStatus": collection.get("status") or "UNKNOWN",
            "currentWork": collection.get("current") or {},
            "lastActivityAt": (collection.get("timestamps") or {}).get("lastActivityAt"),
            "lastSuccessAt": (collection.get("timestamps") or {}).get("lastSuccessAt"),
            "ledger": {
                "events": int(ledger.get("events") or 0),
                "games": int(ledger.get("games") or 0),
                "rounds": int(ledger.get("rounds") or 0),
                "players": int(ledger.get("players") or 0),
            },
            "queue": {
                "pending": int(queue.get("pending") or 0),
                "processing": int(queue.get("processing") or 0),
                "complete": int(queue.get("complete") or 0),
                "failed": int(queue.get("failed") or 0),
            },
            "lastHour": _throughput(hourly),
            "last24Hours": _throughput(daily),
            "analysis": {
                "resolvedMatchupsFound": int(backtest.get("archiveMatchups") or 0),
                "cutoffSafeMatchups": int(backtest.get("eligibleMatchups") or 0),
                "developmentMatchups": int(backtest.get("developmentMatchups") or 0),
                "validationMatchups": int(backtest.get("validationMatchups") or 0),
                "holdoutMatchups": int(backtest.get("holdoutMatchups") or 0),
                "modelConfigurations": len(experiments),
                "modelMatchEvaluations": model_evaluations,
                "tournamentReplays": _replay_count(replay),
                "tournamentReplaysRemaining": int(replay.get("candidatesRemaining") or 0),
                "forwardFrozenExamples": int(gate.get("currentExamples") or 0),
            },
            "backtestRefresh": {
                "status": backtest.get("cacheStatus") or backtest.get("status") or "UNKNOWN",
                "generatedAt": backtest.get("generatedAt"),
                "due": bool(refresh_state.get("due")),
                "newGamesSinceRun": int(refresh_state.get("gameDelta") or 0),
                "newRoundsSinceRun": int(refresh_state.get("roundDelta") or 0),
            },
            "replay": {
                "status": replay.get("status") or "UNKNOWN",
                "updatedAt": replay.get("updatedAt"),
            },
        },
        "baseline": _experiment(ppr, ppr) if ppr else None,
        "experiments": experiments,
        "tracks": [
            {
                "name": "Player and director intelligence",
                "status": "ACTIVE",
                "description": "Turns domain knowledge into measurable candidates such as form, round-loss exposure, venue effects, partner fit, clutch play, and swing response.",
                "output": f"{len(challengers)} challenger configurations currently scored.",
            },
            {
                "name": "Data-discovered intelligence",
                "status": "NEXT_BUILD",
                "description": "Searches the round archive for nonlinear interactions, player and venue cohorts, thresholds, and patterns that were not proposed in advance.",
                "output": "Discovery engine and candidate registry are the next research-layer milestone.",
            },
        ],
        "pipeline": [
            _stage("1", "Data foundation", "COMPLETE", f"{int(backtest.get('archiveMatchups') or 0):,} resolved matchups available."),
            _stage("2", "Cutoff-safe feature construction", "COMPLETE", f"{int(backtest.get('eligibleMatchups') or 0):,} matchups use only prior evidence."),
            _stage("3", "Domain-guided candidate tests", "ACTIVE", f"{len(challengers)} challengers compared with PPR."),
            _stage("4", "Automated pattern discovery", "NEXT", "Mine interactions and cohorts, then register reproducible candidate features."),
            _stage("5", "Historical validation", "ACTIVE", f"{int(backtest.get('holdoutMatchups') or 0):,} untouched holdout matchups."),
            _stage("6", "Tournament-level bake-off", "PARTIAL", f"{_replay_count(replay):,} tournament replays exist; every candidate still needs the same tournament simulation."),
            _stage("7", "Prospective confirmation", "ACTIVE", f"{int(gate.get('currentExamples') or 0):,} frozen forward examples."),
            _stage("8", "Production promotion", "GATED", "No automatic weight changes; promotion requires accuracy, Brier, log-loss, and temporal stability gains."),
        ],
        "nextExperiments": [
            "Run nonlinear interaction discovery on the development period only, then lock candidates before validation.",
            "Test separate models by format, field strength, venue, and player-history depth where sample sizes support it.",
            "Run every serious match challenger through the same historical tournament replay and bracket-size evaluation.",
            "Measure lift by time segment and cohort so aggregate gains cannot hide regressions.",
        ],
        "methodology": {
            "cutoffPolicy": backtest.get("cutoffPolicy"),
            "split": backtest.get("methodology"),
            "holdoutStartDate": backtest.get("holdoutStartDate"),
            "promotionRule": learning.get("learningPolicy"),
        },
    }


def _experiment(row: dict[str, Any] | None, baseline: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    comparison = ((row.get("pairedVsPpr") or {}).get("finalTest") or {})
    role = "CONTROL" if row.get("model") == "PPR only" else "CHALLENGER"
    accuracy_delta = None
    brier_delta = None
    if baseline and row:
        accuracy_delta = _number(row.get("accuracy")) - _number(baseline.get("accuracy"))
        brier_delta = _number(baseline.get("brierScore")) - _number(row.get("brierScore"))
    conclusive = bool(comparison.get("statisticallyClearAt95"))
    improves_both = bool((accuracy_delta or 0) > 0 and (brier_delta or 0) > 0)
    status = "CONTROL" if role == "CONTROL" else "PROMISING" if improves_both else "MIXED" if (accuracy_delta or 0) > 0 or (brier_delta or 0) > 0 else "BEHIND"
    if conclusive and improves_both:
        status = "VALIDATED_CANDIDATE"
    return {
        "name": row.get("model") or "Unknown",
        "role": role,
        "status": status,
        "features": row.get("features") or [],
        "accuracy": row.get("accuracy"),
        "accuracyDelta": accuracy_delta,
        "brierScore": row.get("brierScore"),
        "brierImprovement": brier_delta,
        "logLoss": row.get("logLoss"),
        "coverageRate": row.get("coverageRate"),
        "evaluatedMatchups": row.get("evaluatedMatchups"),
        "changedDecisions": comparison.get("disagreements"),
        "netAdditionalCorrect": comparison.get("netAdditionalCorrect"),
        "pValue": comparison.get("mcnemarPValueApprox"),
        "statisticallyClearAt95": conclusive,
    }


def _stage(order: str, name: str, status: str, detail: str) -> dict[str, str]:
    return {"order": order, "name": name, "status": status, "detail": detail}


def _best(rows: list[dict[str, Any]], key: str, *, higher: bool) -> dict[str, Any] | None:
    usable = [row for row in rows if row.get(key) is not None]
    if not usable:
        return None
    return sorted(usable, key=lambda row: _number(row.get(key)), reverse=higher)[0]


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _replay_count(replay: dict[str, Any]) -> int:
    return int(
        replay.get("historicalReplaySnapshots")
        or replay.get("created")
        or replay.get("complete")
        or replay.get("completed")
        or 0
    )


def _throughput(source: dict[str, Any]) -> dict[str, int]:
    return {
        key: int(source.get(key) or 0)
        for key in (
            "attempts", "completed", "productive", "gamesDownloaded",
            "roundsAdded", "eventsDiscovered", "playersDiscovered",
        )
    }


def _pct(value: Any) -> str:
    return f"{_number(value) * 100:.1f}%"


def _signed_points(value: float) -> str:
    return f"{value * 100:+.2f} percentage points"


def _decimal(value: Any) -> str:
    return f"{_number(value):.3f}"


def _signed_decimal(value: float) -> str:
    return f"{value:+.3f}"
