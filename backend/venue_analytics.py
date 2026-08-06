from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any


def venue_catalog(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            CAST(location_id AS TEXT) AS location_id,
            MAX(location_name) AS location_name,
            MAX(location_city) AS location_city,
            MAX(location_state) AS location_state,
            MAX(location_country) AS location_country,
            AVG(location_lat) AS location_lat,
            AVG(location_lng) AS location_lng,
            COUNT(*) AS event_count,
            MIN(event_date) AS first_event_date,
            MAX(event_date) AS latest_event_date
        FROM events
        WHERE location_id IS NOT NULL
        GROUP BY CAST(location_id AS TEXT)
        ORDER BY event_count DESC, location_name
        """
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        lat = row["location_lat"]
        lng = row["location_lng"]
        key = (
            f"geo:{float(lat):.3f}:{float(lng):.3f}"
            if lat is not None and lng is not None
            else f"id:{row['location_id']}"
        )
        venue = grouped.setdefault(
            key,
            {
                "venueKey": key,
                "displayName": row["location_name"] or f"Venue {row['location_id']}",
                "city": row["location_city"],
                "state": row["location_state"],
                "country": row["location_country"],
                "latitude": lat,
                "longitude": lng,
                "locationIds": [],
                "aliases": [],
                "eventCount": 0,
                "firstEventDate": row["first_event_date"],
                "latestEventDate": row["latest_event_date"],
            },
        )
        venue["locationIds"].append(str(row["location_id"]))
        if row["location_name"] and row["location_name"] not in venue["aliases"]:
            venue["aliases"].append(row["location_name"])
        venue["eventCount"] += int(row["event_count"] or 0)
        if row["first_event_date"] and (
            not venue["firstEventDate"]
            or row["first_event_date"] < venue["firstEventDate"]
        ):
            venue["firstEventDate"] = row["first_event_date"]
        if row["latest_event_date"] and (
            not venue["latestEventDate"]
            or row["latest_event_date"] > venue["latestEventDate"]
        ):
            venue["latestEventDate"] = row["latest_event_date"]
    return sorted(
        grouped.values(),
        key=lambda item: (-item["eventCount"], item["displayName"].lower()),
    )


def venue_for_key(conn, venue_key: str) -> dict[str, Any] | None:
    return next(
        (venue for venue in venue_catalog(conn) if venue["venueKey"] == venue_key),
        None,
    )


def venue_event_schedule(
    conn,
    *,
    venue_key: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    venue = venue_for_key(conn, venue_key)
    if venue is None:
        raise ValueError("Venue was not found")
    placeholders = ",".join("?" for _ in venue["locationIds"])
    rows = conn.execute(
        f"""
        SELECT
            e.*,
            q.status AS event_queue_status,
            q.priority AS event_queue_priority,
            (
                SELECT COUNT(*) FROM historical_backfill_queue gq
                WHERE gq.item_type='GAME' AND gq.event_id=e.event_id
                  AND gq.status IN ('PENDING', 'PROCESSING')
            ) AS games_queued
        FROM events e
        LEFT JOIN historical_backfill_queue q
          ON q.item_type='EVENT' AND q.item_key=CAST(e.event_id AS TEXT)
        WHERE CAST(e.location_id AS TEXT) IN ({placeholders})
          AND e.event_date BETWEEN ? AND ?
        ORDER BY e.event_date, e.event_id
        """,
        (*venue["locationIds"], start_date, end_date),
    ).fetchall()
    event_ids = [int(row["event_id"]) for row in rows]
    event_stats: dict[int, dict[str, Any]] = {}
    if event_ids:
        event_placeholders = ",".join("?" for _ in event_ids)
        stat_rows = conn.execute(
            f"""
            SELECT
                pr.event_id,
                COUNT(DISTINCT CAST(pr.match_id AS TEXT) || ':' || CAST(pr.game_id AS TEXT)) AS games,
                COUNT(DISTINCT pr.player_id) AS players,
                COUNT(*) AS player_rounds,
                COUNT(DISTINCT NULLIF(TRIM(pr.court_id), '')) AS courts,
                ROUND(AVG(pr.gross_points), 2) AS ppr,
                ROUND(AVG(ABS(pr.net_points)), 2) AS average_scoring_swing,
                ROUND(100.0 * AVG(CASE WHEN pr.round_result='W' THEN 1.0 ELSE 0.0 END), 1) AS round_win_rate,
                ROUND(100.0 * AVG(CASE WHEN pr.four_bagger=1 THEN 1.0 ELSE 0.0 END), 1) AS four_bagger_rate,
                ROUND(100.0 * SUM(COALESCE(pr.bags_in, 0)) /
                    NULLIF(SUM(COALESCE(pr.bags_in, 0) + COALESCE(pr.bags_on, 0) + COALESCE(pr.bags_off, 0)), 0), 1
                ) AS bags_in_rate
            FROM player_rounds pr
            WHERE pr.event_id IN ({event_placeholders})
            GROUP BY pr.event_id
            """,
            event_ids,
        ).fetchall()
        event_stats = {
            int(stat["event_id"]): {
                "games": int(stat["games"] or 0),
                "players": int(stat["players"] or 0),
                "playerRounds": int(stat["player_rounds"] or 0),
                "courts": int(stat["courts"] or 0),
                "ppr": stat["ppr"],
                "averageScoringSwing": stat["average_scoring_swing"],
                "roundWinRate": stat["round_win_rate"],
                "fourBaggerRate": stat["four_bagger_rate"],
                "bagsInRate": stat["bags_in_rate"],
            }
            for stat in stat_rows
        }
    events: list[dict[str, Any]] = []
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        targets = int(row["match_stats_targets"] or 0)
        downloaded = int(row["match_stats_downloaded"] or 0)
        bracket_downloaded = bool(row["bracket_downloaded"])
        bracket_complete = bool(row["bracket_completed"])
        if bracket_downloaded and bracket_complete and targets > 0 and downloaded >= targets:
            state = "FULLY_DOWNLOADED"
        elif bracket_downloaded and downloaded > 0:
            state = "PARTIAL"
        elif bracket_downloaded:
            state = "BRACKET_DOWNLOADED"
        else:
            state = "NOT_DOWNLOADED"
        queue_status = row["event_queue_status"]
        priority = int(row["event_queue_priority"] or 0)
        counts[state] += 1
        events.append(
            {
                "eventId": int(row["event_id"]),
                "eventName": row["event_name"],
                "eventDate": row["event_date"],
                "matchType": row["match_type"],
                "bracketType": row["bracket_type"],
                "blindDraw": bool(row["blind_draw"]),
                "eventGroup": row["event_group"] or "STANDARD",
                "downloadState": state,
                "bracketDownloaded": bracket_downloaded,
                "bracketComplete": bracket_complete,
                "matchStatsTargets": targets,
                "matchStatsDownloaded": downloaded,
                "queueStatus": queue_status,
                "queuePriority": priority,
                "priorityQueued": (
                    queue_status in {"PENDING", "PROCESSING"} and priority >= 900
                ),
                "gamesQueued": int(row["games_queued"] or 0),
                "statistics": event_stats.get(int(row["event_id"])),
            }
        )
    populated_stats = [stats for stats in event_stats.values() if stats["playerRounds"]]
    total_rounds = sum(stats["playerRounds"] for stats in populated_stats)
    weighted = lambda field: (
        round(
            sum(float(stats[field] or 0) * stats["playerRounds"] for stats in populated_stats)
            / total_rounds,
            2,
        )
        if total_rounds
        else None
    )
    return {
        "venue": venue,
        "startDate": start_date,
        "endDate": end_date,
        "events": events,
        "summary": {
            "events": len(events),
            "sitAndGo": sum(
                1 for event in events if event["eventGroup"] == "SIT_AND_GO"
            ),
            "standardEvents": sum(
                1 for event in events if event["eventGroup"] == "STANDARD"
            ),
            "fullyDownloaded": counts["FULLY_DOWNLOADED"],
            "partial": counts["PARTIAL"],
            "bracketOnly": counts["BRACKET_DOWNLOADED"],
            "notDownloaded": counts["NOT_DOWNLOADED"],
            "priorityQueued": sum(1 for event in events if event["priorityQueued"]),
        },
        "statistics": {
            "eventsWithStatistics": len(populated_stats),
            "games": sum(stats["games"] for stats in populated_stats),
            "players": len(
                {
                    int(row["player_id"])
                    for row in conn.execute(
                        f"""
                        SELECT DISTINCT player_id FROM player_rounds
                        WHERE event_id IN ({','.join('?' for _ in event_ids)})
                        """,
                        event_ids,
                    ).fetchall()
                }
            ) if event_ids else 0,
            "playerRounds": total_rounds,
            "courts": max((stats["courts"] for stats in populated_stats), default=0),
            "ppr": weighted("ppr"),
            "averageScoringSwing": weighted("averageScoringSwing"),
            "roundWinRate": weighted("roundWinRate"),
            "fourBaggerRate": weighted("fourBaggerRate"),
            "bagsInRate": weighted("bagsInRate"),
        },
    }


def venue_court_ppr(
    conn,
    *,
    venue_key: str,
    start_date: str,
    end_date: str,
    player_ids: list[int] | None = None,
) -> dict[str, Any]:
    venue = venue_for_key(conn, venue_key)
    if venue is None:
        raise ValueError("Venue was not found")
    location_placeholders = ",".join("?" for _ in venue["locationIds"])
    player_clause = ""
    params: list[Any] = [*venue["locationIds"], start_date, end_date]
    if player_ids:
        player_placeholders = ",".join("?" for _ in player_ids)
        player_clause = f"AND pr.player_id IN ({player_placeholders})"
        params.extend(player_ids)
    rows = conn.execute(
        f"""
        SELECT
            pr.event_id, e.event_name, e.event_date,
            CASE
                WHEN TRIM(COALESCE(pr.court_id, '')) IN ('', '-1') THEN 'Unknown'
                ELSE TRIM(pr.court_id)
            END AS court_id,
            pr.match_id, pr.game_id, pr.player_id, pr.player_name,
            pr.gross_points, pr.net_points, pr.four_bagger,
            g.home_score, g.away_score
        FROM player_rounds pr
        JOIN events e ON e.event_id=pr.event_id
        LEFT JOIN games g
          ON g.event_id=pr.event_id
         AND CAST(g.match_id AS TEXT)=CAST(pr.match_id AS TEXT)
         AND g.game_id=pr.game_id
        WHERE CAST(e.location_id AS TEXT) IN ({location_placeholders})
          AND e.event_date BETWEEN ? AND ?
          {player_clause}
        ORDER BY e.event_date DESC, pr.event_id DESC, court_id,
                 CAST(pr.match_id AS INTEGER), pr.game_id, pr.round_no, pr.player_id
        """,
        params,
    ).fetchall()
    available_players = conn.execute(
        f"""
        SELECT pr.player_id, MAX(pr.player_name) AS player_name, COUNT(*) AS rounds
        FROM player_rounds pr
        JOIN events e ON e.event_id=pr.event_id
        WHERE CAST(e.location_id AS TEXT) IN ({location_placeholders})
          AND e.event_date BETWEEN ? AND ?
        GROUP BY pr.player_id
        ORDER BY player_name, pr.player_id
        """,
        (*venue["locationIds"], start_date, end_date),
    ).fetchall()
    event_groups: dict[int, dict[str, Any]] = {}
    for row in rows:
        event_id = int(row["event_id"])
        event = event_groups.setdefault(
            event_id,
            {
                "eventId": event_id,
                "eventName": row["event_name"],
                "eventDate": row["event_date"],
                "_points": [],
                "courts": {},
            },
        )
        court_id = str(row["court_id"])
        court = event["courts"].setdefault(
            court_id,
            {"courtId": court_id, "_points": [], "games": {}},
        )
        game_key = f"{row['match_id']}:{row['game_id']}"
        game = court["games"].setdefault(
            game_key,
            {
                "matchId": str(row["match_id"]),
                "gameId": int(row["game_id"]),
                "homeScore": row["home_score"],
                "awayScore": row["away_score"],
                "_points": [],
                "players": {},
            },
        )
        points = float(row["gross_points"] or 0)
        event["_points"].append(points)
        court["_points"].append(points)
        game["_points"].append(points)
        player_id = int(row["player_id"])
        player = game["players"].setdefault(
            player_id,
            {
                "playerId": player_id,
                "playerName": row["player_name"] or f"Player {player_id}",
                "_points": [],
                "fourBaggers": 0,
            },
        )
        player["_points"].append(points)
        player["fourBaggers"] += int(row["four_bagger"] or 0)

    events: list[dict[str, Any]] = []
    for event in event_groups.values():
        courts = []
        for court in event["courts"].values():
            games = []
            for game in court["games"].values():
                players = []
                for player in game["players"].values():
                    player_points = player.pop("_points")
                    players.append({
                        **player,
                        "rounds": len(player_points),
                        "ppr": round(sum(player_points) / len(player_points), 2),
                    })
                game_points = game.pop("_points")
                games.append({
                    **game,
                    "rounds": len(game_points),
                    "ppr": round(sum(game_points) / len(game_points), 2),
                    "players": sorted(players, key=lambda item: item["playerName"]),
                })
            court_points = court.pop("_points")
            courts.append({
                "courtId": court["courtId"],
                "rounds": len(court_points),
                "ppr": round(sum(court_points) / len(court_points), 2),
                "games": games,
            })
        event_points = event.pop("_points")
        events.append({
            "eventId": event["eventId"],
            "eventName": event["eventName"],
            "eventDate": event["eventDate"],
            "rounds": len(event_points),
            "ppr": round(sum(event_points) / len(event_points), 2),
            "courts": sorted(courts, key=lambda item: _court_sort(item["courtId"])),
        })
    all_points = [float(row["gross_points"] or 0) for row in rows]
    court_totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        court_id = str(row["court_id"])
        total = court_totals.setdefault(
            court_id,
            {"courtId": court_id, "_points": [], "_events": set(), "_games": set()},
        )
        total["_points"].append(float(row["gross_points"] or 0))
        total["_events"].add(int(row["event_id"]))
        total["_games"].add(
            (int(row["event_id"]), str(row["match_id"]), int(row["game_id"]))
        )
    court_breakdown = []
    for total in court_totals.values():
        points = total.pop("_points")
        event_ids = total.pop("_events")
        game_ids = total.pop("_games")
        court_breakdown.append({
            **total,
            "ppr": round(sum(points) / len(points), 2),
            "events": len(event_ids),
            "games": len(game_ids),
            "playerRounds": len(points),
        })
    return {
        "venue": venue,
        "startDate": start_date,
        "endDate": end_date,
        "selectedPlayerIds": player_ids or [],
        "players": [
            {
                "playerId": int(row["player_id"]),
                "playerName": row["player_name"] or f"Player {row['player_id']}",
                "rounds": int(row["rounds"] or 0),
            }
            for row in available_players
        ],
        "summary": {
            "events": len(events),
            "courts": len({
                court["courtId"] for event in events for court in event["courts"]
            }),
            "games": sum(
                len(court["games"]) for event in events for court in event["courts"]
            ),
            "playerRounds": len(all_points),
            "ppr": round(sum(all_points) / len(all_points), 2) if all_points else None,
        },
        "courtBreakdown": sorted(
            court_breakdown, key=lambda item: _court_sort(item["courtId"])
        ),
        "events": events,
    }


def _court_sort(value: str) -> tuple[int, Any]:
    try:
        return 0, int(value)
    except (TypeError, ValueError):
        return 1, str(value)


def acl_season_range(start_year: int) -> tuple[str, str]:
    return f"{start_year:04d}-09-01", f"{start_year + 1:04d}-08-31"


def default_season_start_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 9 else today.year - 1
