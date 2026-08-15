from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from statistic_observations import eligible_observations, normalize_timestamp


FEATURE_VERSION = "stage-a-v1"


def _cutoff(cutoff_at: str) -> tuple[str, datetime]:
    original_text = str(cutoff_at).strip()
    parse_text = f"{original_text[:-1]}+00:00" if original_text.endswith("Z") else original_text
    try:
        original = datetime.fromisoformat(parse_text)
    except ValueError as exc:
        raise ValueError(f"Invalid cutoff timestamp: {cutoff_at}") from exc
    if original.tzinfo is None:
        original = original.replace(tzinfo=timezone.utc)
    normalized, valid = normalize_timestamp(cutoff_at)
    if not valid or normalized is None:
        raise ValueError(f"Invalid cutoff timestamp: {cutoff_at}")
    parsed = datetime.fromisoformat(normalized)
    return original.date().isoformat(), parsed


def _safe_div(numerator: float | int, denominator: float | int) -> float | None:
    return float(numerator) / float(denominator) if denominator else None


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def _history_rows(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    cutoff_date: str,
    window_days: int | None,
) -> list[dict[str, Any]]:
    clauses = [
        "pr.player_id=?",
        "pr.event_date IS NOT NULL",
        "pr.event_date < ?",
        "g.completed=1",
    ]
    params: list[Any] = [int(player_id), cutoff_date]
    if window_days is not None:
        if window_days <= 0:
            raise ValueError("window_days must be positive")
        start = date.fromisoformat(cutoff_date) - timedelta(days=window_days)
        clauses.append("pr.event_date >= ?")
        params.append(start.isoformat())
    cursor = conn.execute(
        f"""
        SELECT pr.*
        FROM player_rounds pr
        JOIN games g
          ON g.event_id=pr.event_id
         AND g.match_id=pr.match_id
         AND g.game_id=pr.game_id
        WHERE {' AND '.join(clauses)}
        ORDER BY pr.event_date, pr.event_id, pr.match_id, pr.game_id, pr.round_no
        """,
        params,
    )
    columns = [description[0] for description in cursor.description or []]
    return [
        dict(row) if isinstance(row, sqlite3.Row) else dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


def _latest_acl_snapshot(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    statistic_types: Iterable[str],
    cutoff_at: str,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for statistic_type in statistic_types:
        candidates.extend(
            eligible_observations(
                conn,
                player_id=player_id,
                statistic_type=statistic_type,
                cutoff_at=cutoff_at,
            )
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            row.get("source_effective_at") or row.get("retrieved_at") or "",
            row.get("retrieved_at") or "",
        ),
        reverse=True,
    )
    row = candidates[0]
    return {
        "observationId": row["statistic_observation_id"],
        "type": row["statistic_type"],
        "value": row["numeric_value"],
        "sourceEndpoint": row["source_endpoint"],
        "scopeType": row["scope_type"],
        "scopeId": row["scope_id"],
        "effectiveAt": row["source_effective_at"],
        "retrievedAt": row["retrieved_at"],
    }


def _expected_games(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    cutoff_date: str,
    window_days: int | None,
) -> list[tuple[int, str, int]]:
    clauses = ["tm.player_id=?", "e.event_date IS NOT NULL", "e.event_date < ?"]
    params: list[Any] = [int(player_id), cutoff_date]
    if window_days is not None:
        start = date.fromisoformat(cutoff_date) - timedelta(days=window_days)
        clauses.append("e.event_date >= ?")
        params.append(start.isoformat())
    rows = conn.execute(
        f"""
        SELECT DISTINCT g.event_id, g.match_id, g.game_id
        FROM team_members tm
        JOIN events e ON e.event_id=tm.event_id
        JOIN games g
          ON g.event_id=tm.event_id
         AND (g.home_team_id=tm.team_id OR g.away_team_id=tm.team_id)
        WHERE {' AND '.join(clauses)} AND g.completed=1
        """,
        params,
    ).fetchall()
    return [(int(row[0]), str(row[1]), int(row[2])) for row in rows]


def _coverage(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    rows: list[dict[str, Any]],
    cutoff_date: str,
    window_days: int | None,
) -> dict[str, Any]:
    retrieved_keys = {
        (int(row["event_id"]), str(row["match_id"]), int(row["game_id"]))
        for row in rows
    }
    expected_keys = set(
        _expected_games(
            conn,
            player_id=player_id,
            cutoff_date=cutoff_date,
            window_days=window_days,
        )
    )
    coverage_known = bool(expected_keys) and retrieved_keys.issubset(expected_keys)
    relevant_keys = expected_keys or retrieved_keys
    latest_outcome: dict[tuple[int, str, int], str] = {}
    if relevant_keys:
        lookup = {
            f"match-stats:{event_id}:{match_id}:{game_id}": (event_id, match_id, game_id)
            for event_id, match_id, game_id in relevant_keys
        }
        entity_keys = list(lookup)
        for offset in range(0, len(entity_keys), 800):
            batch = entity_keys[offset:offset + 800]
            placeholders = ",".join("?" for _ in batch)
            attempts = conn.execute(
                f"""
                SELECT ingestion_attempt_id, entity_key, outcome
                FROM ingestion_attempts
                WHERE source_endpoint='match-stats'
                  AND entity_key IN ({placeholders})
                ORDER BY ingestion_attempt_id
                """,
                batch,
            ).fetchall()
            for attempt in attempts:
                key = lookup.get(str(attempt[1]))
                if key is not None:
                    latest_outcome[key] = str(attempt[2])

    outcome_counts = Counter(latest_outcome.values())
    expected = len(expected_keys) if coverage_known else None
    retrieved = len(retrieved_keys)
    return {
        "expectedGames": expected,
        "indexedExpectedGames": len(expected_keys),
        "retrievedGames": retrieved,
        "blockedGames": outcome_counts["auth_blocked"],
        "httpErrorGames": outcome_counts["http_error"],
        "networkErrorGames": outcome_counts["network_error"],
        "unattemptedGames": (
            max(len(expected_keys) - len(latest_outcome), 0) if coverage_known else None
        ),
        "coverageRatio": (
            _rounded(_safe_div(retrieved, len(expected_keys)))
            if coverage_known
            else None
        ),
        "coverageKnown": coverage_known,
    }


def build_player_features(
    conn: sqlite3.Connection,
    *,
    player_id: int,
    cutoff_at: str,
    window_days: int | None = 365,
    include_acl_snapshots: bool = False,
) -> dict[str, Any]:
    cutoff_date, cutoff_dt = _cutoff(cutoff_at)
    rows = _history_rows(
        conn,
        player_id=player_id,
        cutoff_date=cutoff_date,
        window_days=window_days,
    )
    games = {
        (row["event_id"], row["match_id"], row["game_id"])
        for row in rows
    }
    events = {row["event_id"] for row in rows}
    gross = sum(int(row.get("gross_points") or 0) for row in rows)
    opponent = sum(int(row.get("opponent_points") or 0) for row in rows)
    net = sum(int(row.get("net_points") or 0) for row in rows)
    bags_in = sum(int(row.get("bags_in") or 0) for row in rows)
    bags_on = sum(int(row.get("bags_on") or 0) for row in rows)
    bags_off = sum(int(row.get("bags_off") or 0) for row in rows)
    total_bags = bags_in + bags_on + bags_off
    four_baggers = sum(int(row.get("four_bagger") or 0) for row in rows)
    result_counts = Counter(str(row.get("round_result") or "") for row in rows)
    format_counts = Counter(
        f"{str(row.get('match_type') or 'UNKNOWN').upper()}:"
        f"{str(row.get('bracket_type') or 'UNKNOWN').upper()}"
        for row in rows
    )
    last_date = max((str(row["event_date"]) for row in rows), default=None)
    recency_days = (
        (cutoff_dt.date() - date.fromisoformat(last_date)).days if last_date else None
    )
    rounds = len(rows)
    recent_start = cutoff_dt.date() - timedelta(days=90)
    recent_rows = [
        row for row in rows
        if date.fromisoformat(str(row["event_date"])) >= recent_start
    ]
    recent_rounds = len(recent_rows)
    recent_ppr = _safe_div(
        sum(int(row.get("gross_points") or 0) for row in recent_rows),
        recent_rounds,
    )
    calculated_ppr = _safe_div(gross, rounds)
    recent_reliability = recent_rounds / (recent_rounds + 30) if recent_rounds else 0.0
    features: dict[str, Any] = {
        "featureVersion": FEATURE_VERSION,
        "playerId": int(player_id),
        "dataCutoffAt": cutoff_dt.isoformat(),
        "cutoffEventDate": cutoff_date,
        "cutoffPolicy": "STRICTLY_PRIOR_EVENT_DATE",
        "windowDays": window_days,
        "events": len(events),
        "games": len(games),
        "rounds": rounds,
        "grossPoints": gross,
        "opponentPoints": opponent,
        "netPoints": net,
        "calculatedPpr": _rounded(calculated_ppr),
        "recent90Ppr": _rounded(recent_ppr),
        "recent90Rounds": recent_rounds,
        "recent90PprEffect": _rounded(
            recent_reliability * (recent_ppr - calculated_ppr)
            if recent_ppr is not None and calculated_ppr is not None else 0.0
        ),
        "calculatedOpponentPpr": _rounded(_safe_div(opponent, rounds)),
        "calculatedDpr": _rounded(_safe_div(net, rounds)),
        "ceilingRate": _rounded(_safe_div(
            sum(int(row.get("gross_points") or 0) >= 10 for row in rows),
            rounds,
        )),
        "floorAvoidance": _rounded(1.0 - _safe_div(
            sum(int(row.get("gross_points") or 0) <= 5 for row in rows),
            rounds,
        )) if rounds else None,
        "bagsInRate": _rounded(_safe_div(bags_in, total_bags)),
        "bagsOnRate": _rounded(_safe_div(bags_on, total_bags)),
        "bagsOffRate": _rounded(_safe_div(bags_off, total_bags)),
        "fourBaggerRate": _rounded(_safe_div(four_baggers, rounds)),
        "roundWinRate": _rounded(_safe_div(result_counts["W"], rounds)),
        "roundLossRate": _rounded(_safe_div(result_counts["L"], rounds)),
        "roundTieRate": _rounded(_safe_div(result_counts["T"], rounds)),
        "lastEventDate": last_date,
        "recencyDays": recency_days,
        "formatRoundCounts": dict(sorted(format_counts.items())),
        "coverage": _coverage(
            conn,
            player_id=player_id,
            rows=rows,
            cutoff_date=cutoff_date,
            window_days=window_days,
        ),
        "missing": {
            "matchHistory": rounds == 0,
            "coverageUnknown": False,
        },
    }
    features["missing"]["coverageUnknown"] = not features["coverage"]["coverageKnown"]

    if include_acl_snapshots:
        features["aclSnapshots"] = {
            "cpi": _latest_acl_snapshot(
                conn,
                player_id=player_id,
                statistic_types=["ACL_REPORTED_CPI"],
                cutoff_at=cutoff_at,
            ),
            "ppr": _latest_acl_snapshot(
                conn,
                player_id=player_id,
                statistic_types=[
                    "ACL_REPORTED_SEASON_PPR",
                    "ACL_REPORTED_PROFILE_PPR",
                ],
                cutoff_at=cutoff_at,
            ),
        }
    acl_ppr = (features.get("aclSnapshots") or {}).get("ppr")
    if features["calculatedPpr"] is not None:
        features["predictivePpr"] = features["calculatedPpr"]
        features["predictivePprSource"] = "INTERNAL_CALCULATED_PPR"
        features["predictivePprSampleConfidence"] = _rounded(
            rounds / (rounds + 30)
        )
    elif acl_ppr and acl_ppr.get("value") is not None:
        features["predictivePpr"] = float(acl_ppr["value"])
        features["predictivePprSource"] = acl_ppr["type"]
        features["predictivePprSampleConfidence"] = 0.45
    else:
        features["predictivePpr"] = None
        features["predictivePprSource"] = "UNAVAILABLE"
        features["predictivePprSampleConfidence"] = 0.0
    return features


def build_partnership_features(
    conn: sqlite3.Connection,
    *,
    player_ids: Iterable[int],
    cutoff_at: str,
    window_days: int | None = 365,
) -> dict[str, Any]:
    ids = sorted({int(player_id) for player_id in player_ids})
    if len(ids) < 2:
        return {
            "playerIds": ids,
            "sharedGames": 0,
            "sharedEvents": 0,
            "knownPartnership": False,
        }
    cutoff_date, cutoff_dt = _cutoff(cutoff_at)
    clauses = ["event_date IS NOT NULL", "event_date < ?"]
    params: list[Any] = [cutoff_date]
    if window_days is not None:
        start = date.fromisoformat(cutoff_date) - timedelta(days=window_days)
        clauses.append("event_date >= ?")
        params.append(start.isoformat())
    placeholders = ",".join("?" for _ in ids)
    params.extend(ids)
    rows = conn.execute(
        f"""
        SELECT
            event_id, match_id, game_id, team_id,
            COUNT(DISTINCT player_id) AS players_present
        FROM player_rounds
        WHERE {' AND '.join(clauses)}
          AND player_id IN ({placeholders})
          AND team_id IS NOT NULL
        GROUP BY event_id, match_id, game_id, team_id
        HAVING COUNT(DISTINCT player_id)=?
        """,
        [*params, len(ids)],
    ).fetchall()
    return {
        "playerIds": ids,
        "dataCutoffAt": cutoff_dt.isoformat(),
        "windowDays": window_days,
        "sharedGames": len(rows),
        "sharedEvents": len({int(row[0]) for row in rows}),
        "knownPartnership": bool(rows),
    }


def _weighted_side_metric(
    player_features: list[dict[str, Any]],
    metric: str,
) -> float | None:
    available = [
        (feature.get(metric), int(feature.get("rounds") or 0))
        for feature in player_features
        if feature.get(metric) is not None and int(feature.get("rounds") or 0) > 0
    ]
    total_rounds = sum(rounds for _, rounds in available)
    if not total_rounds:
        return None
    return _rounded(
        sum(float(value) * rounds for value, rounds in available) / total_rounds
    )


def _equal_player_metric(
    player_features: list[dict[str, Any]],
    metric: str,
) -> float | None:
    available = [
        float(feature[metric])
        for feature in player_features
        if feature.get(metric) is not None
    ]
    if len(available) != len(player_features) or not available:
        return None
    return _rounded(sum(available) / len(available))


def build_side_features(
    conn: sqlite3.Connection,
    *,
    player_ids: Iterable[int],
    cutoff_at: str,
    window_days: int | None = 365,
    include_acl_snapshots: bool = False,
) -> dict[str, Any]:
    ids = sorted({int(player_id) for player_id in player_ids})
    players = [
        build_player_features(
            conn,
            player_id=player_id,
            cutoff_at=cutoff_at,
            window_days=window_days,
            include_acl_snapshots=include_acl_snapshots,
        )
        for player_id in ids
    ]
    metrics = (
        "calculatedPpr",
        "calculatedOpponentPpr",
        "calculatedDpr",
        "ceilingRate",
        "floorAvoidance",
        "bagsInRate",
        "bagsOnRate",
        "bagsOffRate",
        "fourBaggerRate",
        "roundWinRate",
        "roundLossRate",
    )
    aggregate = {
        metric: _weighted_side_metric(players, metric)
        for metric in metrics
    }
    aggregate["predictivePpr"] = _equal_player_metric(players, "predictivePpr")
    aggregate["roundLossRate"] = _equal_player_metric(players, "roundLossRate")
    aggregate["recent90PprEffect"] = _equal_player_metric(players, "recent90PprEffect")
    total_rounds = sum(int(player["rounds"]) for player in players)
    retrieved = sum(int(player["coverage"]["retrievedGames"]) for player in players)
    expected_values = [
        player["coverage"]["expectedGames"]
        for player in players
        if player["coverage"]["expectedGames"] is not None
    ]
    expected = sum(int(value) for value in expected_values) if len(expected_values) == len(players) else None
    return {
        "featureVersion": FEATURE_VERSION,
        "playerIds": ids,
        "dataCutoffAt": players[0]["dataCutoffAt"] if players else _cutoff(cutoff_at)[1].isoformat(),
        "players": players,
        "aggregate": aggregate,
        "partnership": build_partnership_features(
            conn,
            player_ids=ids,
            cutoff_at=cutoff_at,
            window_days=window_days,
        ),
        "coverage": {
            "rounds": total_rounds,
            "retrievedPlayerGames": retrieved,
            "expectedPlayerGames": expected,
            "coverageRatio": _rounded(_safe_div(retrieved, expected)) if expected else None,
        },
        "missing": {
            "anyPlayerWithoutHistory": any(player["rounds"] == 0 for player in players),
            "anyPlayerWithoutPredictivePpr": any(
                player.get("predictivePpr") is None for player in players
            ),
            "anyAclAssistedPpr": any(
                player.get("predictivePprSource") != "INTERNAL_CALCULATED_PPR"
                and player.get("predictivePpr") is not None
                for player in players
            ),
            "anyCoverageUnknown": any(
                not player["coverage"]["coverageKnown"] for player in players
            ),
        },
    }


def build_matchup_features(
    conn: sqlite3.Connection,
    *,
    side_a_player_ids: Iterable[int],
    side_b_player_ids: Iterable[int],
    cutoff_at: str,
    window_days: int | None = 365,
    include_acl_snapshots: bool = False,
) -> dict[str, Any]:
    side_a = build_side_features(
        conn,
        player_ids=side_a_player_ids,
        cutoff_at=cutoff_at,
        window_days=window_days,
        include_acl_snapshots=include_acl_snapshots,
    )
    side_b = build_side_features(
        conn,
        player_ids=side_b_player_ids,
        cutoff_at=cutoff_at,
        window_days=window_days,
        include_acl_snapshots=include_acl_snapshots,
    )
    deltas: dict[str, float | None] = {}
    for metric, a_value in side_a["aggregate"].items():
        b_value = side_b["aggregate"].get(metric)
        deltas[metric] = (
            _rounded(float(a_value) - float(b_value))
            if a_value is not None and b_value is not None
            else None
        )
    return {
        "featureVersion": FEATURE_VERSION,
        "dataCutoffAt": side_a["dataCutoffAt"],
        "windowDays": window_days,
        "sideA": side_a,
        "sideB": side_b,
        "deltasAminusB": deltas,
        "modelReady": (
            bool(side_a["playerIds"])
            and bool(side_b["playerIds"])
            and not side_a["missing"]["anyPlayerWithoutPredictivePpr"]
            and not side_b["missing"]["anyPlayerWithoutPredictivePpr"]
        ),
    }
