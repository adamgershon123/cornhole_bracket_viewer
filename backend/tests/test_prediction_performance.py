from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import patch

from bracket_prediction_snapshots import _init_schema
from prediction_performance import prediction_performance_report
from season_platform import init_db


class PredictionPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        _init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_scores_frozen_champion_distribution_by_field_size(self) -> None:
        self.conn.execute(
            """
            INSERT INTO events(event_id, event_name, event_date)
            VALUES (500, 'Test Tournament', '2026-07-30')
            """
        )
        teams = [
            {
                "teamId": str(index),
                "teamName": f"Team {index}",
                "playerIds": [1000 + index],
                "players": [{"playerId": 1000 + index, "playerName": f"Player {index}"}],
                "winEventProbability": probability,
            }
            for index, probability in enumerate(
                [0.40, 0.25, 0.15, 0.08, 0.05, 0.03, 0.02, 0.02],
                start=1,
            )
        ]
        self.conn.execute(
            """
            INSERT INTO bracket_prediction_snapshots(
              event_id, snapshot_type, state_key, completed_matches,
              payload_json, created_at
            ) VALUES (500, 'PREGAME', 'PREGAME', 0, ?, '2026-07-30T10:00:00+00:00')
            """,
            (json.dumps({"teams": teams, "coverage": {"modelCoverageRate": 1.0}}),),
        )
        self.conn.execute(
            """
            INSERT INTO event_results(
              event_id, player_id, place, points, team_id, team_name,
              wins, losses, player_ppr
            ) VALUES (500, 1002, 1, 0, '2', 'Team 2', 4, 0, 8.2)
            """
        )
        self.conn.commit()

        report = prediction_performance_report(self.conn)
        tournament = report["tournamentPerformance"]

        self.assertEqual(tournament["overall"]["resolvedTournaments"], 1)
        self.assertEqual(tournament["overall"]["favoriteAccuracy"], 0.0)
        self.assertEqual(tournament["overall"]["topThreeHitRate"], 1.0)
        self.assertEqual(tournament["overall"]["averageChampionRank"], 2)
        self.assertEqual(tournament["overall"]["sampleStatus"], "TOO_EARLY")
        self.assertIsNotNone(tournament["overall"]["favoriteAccuracy95"])
        self.assertLess(
            tournament["overall"]["multiclassBrierScore"],
            tournament["overall"]["equalOddsBrierScore"],
        )
        self.assertEqual(tournament["byBracketSize"][0]["group"], "2–8 teams")
        self.assertEqual(tournament["events"][0]["championProbability"], 0.25)
        self.assertEqual(tournament["calibration"][0]["sampleStatus"], "TOO_EARLY")
        self.assertEqual(tournament["modelComparison"][0]["model"], "Equal odds")
        self.assertEqual(
            tournament["modelComparison"][2]["status"],
            "PROSPECTIVE_NOT_YET_FROZEN",
        )

    def test_bye_team_is_not_part_of_field_size(self) -> None:
        self.conn.execute(
            "INSERT INTO events(event_id, event_name, event_date) VALUES (501, 'Bye Test', '2026-07-30')"
        )
        payload = {
            "teams": [
                {
                    "teamId": "1", "teamName": "Real One", "playerIds": [2001],
                    "winEventProbability": 0.6,
                },
                {
                    "teamId": "2", "teamName": "Real Two", "playerIds": [2002],
                    "winEventProbability": 0.3,
                },
                {
                    "teamId": "3", "teamName": "Team 3", "playerIds": [2999],
                    "players": [{"playerId": 2999, "playerName": "Bye User 121"}],
                    "winEventProbability": 0.1,
                },
            ]
        }
        self.conn.execute(
            """
            INSERT INTO bracket_prediction_snapshots(
              event_id, snapshot_type, state_key, completed_matches,
              payload_json, created_at
            ) VALUES (501, 'PREGAME', 'PREGAME', 0, ?, '2026-07-30T11:00:00+00:00')
            """,
            (json.dumps(payload),),
        )
        self.conn.execute(
            """
            INSERT INTO event_results(
              event_id, player_id, place, points, team_id, team_name,
              wins, losses, player_ppr
            ) VALUES (501, 2001, 1, 0, '1', 'Real One', 1, 0, 8)
            """
        )
        self.conn.commit()

        event = prediction_performance_report(self.conn)["tournamentPerformance"]["events"][0]

        self.assertEqual(event["teamCount"], 2)
        self.assertEqual(event["championProbability"], round(0.6 / 0.9, 6))

    def test_completed_bracket_final_overrides_ambiguous_standings(self) -> None:
        self.conn.execute(
            "INSERT INTO events(event_id, event_name, event_date) VALUES (502, 'Final Test', '2026-07-30')"
        )
        teams = [
            {
                "teamId": "1", "teamName": "Alpha", "playerIds": [3001, 3002],
                "winEventProbability": 0.7,
            },
            {
                "teamId": "2", "teamName": "Bravo", "playerIds": [3003, 3004],
                "winEventProbability": 0.3,
            },
        ]
        self.conn.execute(
            """
            INSERT INTO bracket_prediction_snapshots(
              event_id, snapshot_type, state_key, completed_matches,
              payload_json, created_at
            ) VALUES (502, 'PREGAME', 'PREGAME', 0, ?, '2026-07-30T12:00:00+00:00')
            """,
            (json.dumps({"teams": teams}),),
        )
        for team_id, player_id in (("1", 3001), ("2", 3003)):
            self.conn.execute(
                """
                INSERT INTO event_results(
                  event_id, player_id, place, points, team_id, team_name,
                  wins, losses, player_ppr
                ) VALUES (502, ?, 1, 0, ?, ?, 1, 0, 8)
                """,
                (player_id, team_id, f"Team {team_id}"),
            )
        self.conn.commit()
        bracket = {
            "bracketDetails": [
                {
                    "rounddesc": "FINAL", "bracketmatchid": 9,
                    "bracketpos": "M9T", "matchStatusID": 5,
                    "player_info": [{"playerid": 3001}, {"playerid": 3002}],
                    "gameResults": [
                        {"gameID": 1, "matchStatusID": 5, "scoreHome": 15, "scoreAway": 21},
                        {"gameID": 2, "matchStatusID": 5, "scoreHome": 21, "scoreAway": 12},
                    ],
                },
                {
                    "rounddesc": "FINAL", "bracketmatchid": 9,
                    "bracketpos": "M9B", "matchStatusID": 5,
                    "player_info": [{"playerid": 3003}, {"playerid": 3004}],
                },
            ]
        }

        with patch("prediction_performance._cached_bracket_payload", return_value=bracket):
            events = prediction_performance_report(self.conn)["tournamentPerformance"]["events"]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["championTeamId"], "1")
        self.assertEqual(events[0]["championResolutionSource"], "COMPLETED_BRACKET_FINAL")


if __name__ == "__main__":
    unittest.main()
