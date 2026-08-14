import sqlite3
import unittest

from tournament_report_cards import _GAME_CALIBRATION_CACHE, _apply_event_relative_scores, _apply_game_scores, _apply_tournament_resume_scores, _grade, apply_current_grade_labels, build_game_report_card, build_tournament_report_cards


class TournamentReportCardsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE events(event_id INTEGER PRIMARY KEY,event_name TEXT,event_date TEXT,status TEXT,match_type TEXT,bracket_type TEXT,blind_draw INTEGER,location_name TEXT);
            CREATE TABLE players(player_id INTEGER PRIMARY KEY,display_name TEXT);
            CREATE TABLE games(event_id INTEGER,match_id TEXT,game_id INTEGER,completed INTEGER);
            CREATE TABLE player_rounds(event_id INTEGER,match_id TEXT,game_id INTEGER,round_no INTEGER,player_id INTEGER,player_name TEXT,team_id TEXT,opponent_player_id INTEGER,opponent_team_id TEXT,team_side TEXT,court_id TEXT,gross_points INTEGER,opponent_points INTEGER,net_points INTEGER,scored_points INTEGER,bags_in INTEGER,bags_on INTEGER,bags_off INTEGER,four_bagger INTEGER,round_result TEXT,event_date TEXT,location_id TEXT,location_name TEXT,match_type TEXT,bracket_type TEXT,blind_draw INTEGER);
        """)
        self.conn.execute("INSERT INTO events VALUES(99,'Test Doubles','2026-08-01','C','D','W',0,'Test Hall')")
        self.conn.execute("INSERT INTO games VALUES(99,'1',1,1)")
        for player_id, name, team, ppr in ((1,'Alpha','A',8),(2,'Partner','A',7),(3,'Bravo','B',6),(4,'Other','B',6)):
            for round_no in range(1, 7):
                opponent = 3 if team == 'A' else 1
                opponent_points = 6 if team == 'A' else 8
                net = ppr - opponent_points
                self.conn.execute(
                    "INSERT INTO player_rounds VALUES(99,'1',1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (round_no,player_id,name,team,opponent,'B' if team=='A' else 'A','HOME' if team=='A' else 'AWAY','1',ppr,opponent_points,net,max(net,0),4 if ppr>=8 else 2,0,0,1 if ppr>=8 else 0,'W' if net>0 else 'L' if net<0 else 'T','2026-08-01','10','Test Hall','D','W',0),
                )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_generates_player_and_team_mvp_with_match_cards(self):
        result = build_tournament_report_cards(self.conn, 99)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["playerMvp"]["playerName"], "Alpha")
        self.assertIsNotNone(result["teamMvp"])
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(len(result["players"]), 4)
        self.assertIn("performance", result["playerMvp"]["categoryScores"])
        self.assertEqual(result["gradingModelVersion"], "tournament-report-cards-v9-double-elimination-placement")

    def test_letter_grades_use_familiar_academic_thresholds(self):
        self.assertEqual(_grade(100), "A+")
        self.assertEqual(_grade(93), "A")
        self.assertEqual(_grade(81.6), "B")
        self.assertEqual(_grade(78), "C+")
        self.assertEqual(_grade(59.9), "F")

    def test_saved_numeric_scores_can_be_relabelled_without_recalculation(self):
        report = {
            "players": [{"overallScore": 78, "grade": "B+"}],
            "playerMvp": {"overallScore": 81.6, "grade": "B+"},
        }
        relabelled = apply_current_grade_labels(report)
        self.assertEqual(relabelled["players"][0]["overallScore"], 78)
        self.assertEqual(relabelled["players"][0]["grade"], "C+")
        self.assertEqual(relabelled["playerMvp"]["grade"], "B")

    def test_expectation_category_materially_affects_performance_grade(self):
        players = [
            {"playerId": 1, "playerName": "Expected", "rounds": 24, "ppr": 8, "pprVsExpected": 0,
             "consistencyRaw": -1, "clutchNet": 0, "dpr": 0, "recoveryNet": 0, "largeSwingsConceded": 0,
             "matchReportCards": []},
            {"playerId": 2, "playerName": "Outperformed", "rounds": 24, "ppr": 8, "pprVsExpected": 2,
             "consistencyRaw": -1, "clutchNet": 0, "dpr": 0, "recoveryNet": 0, "largeSwingsConceded": 0,
             "matchReportCards": []},
        ]
        _apply_event_relative_scores(players)
        self.assertGreater(players[1]["performanceGrade"], players[0]["performanceGrade"])
        self.assertGreater(players[1]["categoryWeightedScore"], players[0]["categoryWeightedScore"])

    def test_event_percentiles_are_normalized_before_academic_letter_grade(self):
        players = [
            {"playerId": 1, "playerName": "Only player", "rounds": 24, "ppr": 7.5, "pprVsExpected": 0,
             "consistencyRaw": 0, "clutchNet": 0, "dpr": 0, "recoveryNet": 0, "largeSwingsConceded": 0,
             "matchReportCards": []},
        ]
        _apply_event_relative_scores(players)
        self.assertEqual(players[0]["categoryWeightedScore"], 50.0)
        self.assertEqual(players[0]["performanceGrade"], 75.0)
        self.assertEqual(players[0]["performanceGradeLetter"], "C")

    def test_single_game_grade_does_not_build_tournament_resume(self):
        result = build_game_report_card(self.conn, 99, "1", 1)
        self.assertEqual(result["scope"], "SINGLE_GAME")
        self.assertEqual(result["matchId"], "1")
        self.assertEqual(result["gameId"], 1)
        self.assertEqual(len(result["players"]), 4)
        self.assertNotIn("playerMvp", result)
        self.assertNotIn("teams", result)
        self.assertEqual(result["calculationMode"], "USER_INITIATED_SINGLE_GAME")

    def test_same_name_history_is_flagged_but_not_merged(self):
        self.conn.execute("INSERT INTO players(player_id,display_name) VALUES(100,'Alpha')")
        self.conn.execute(
            "INSERT INTO player_rounds VALUES(98,'9',1,1,100,'Alpha','X',3,'Y','HOME','1',6,7,-1,0,1,1,2,0,'L','2026-07-01','10','Test Hall','D','W',0)"
        )
        self.conn.commit()
        result = build_tournament_report_cards(self.conn, 99)
        alpha = next(player for player in result["players"] if player["playerId"] == 1)
        self.assertEqual(alpha["expectationSource"], "NO_PRIOR_HISTORY_NEUTRAL")
        self.assertEqual(alpha["possibleHistoricalAccounts"][0]["playerId"], 100)
        self.assertFalse(alpha["possibleHistoricalAccounts"][0]["usedInGrade"])

    def test_future_rounds_do_not_change_completed_event_grades(self):
        first = build_tournament_report_cards(self.conn, 99)
        for round_no in range(1, 7):
            self.conn.execute(
                "INSERT INTO player_rounds VALUES(100,'1',1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (round_no,1,'Alpha','A',3,'B','HOME','1',0,12,-12,0,0,0,4,0,'L','2026-08-02','10','Test Hall','D','W',0),
            )
        self.conn.commit()
        _GAME_CALIBRATION_CACHE.clear()
        second = build_tournament_report_cards(self.conn, 99)
        first_scores = [(player["playerId"], player["overallScore"]) for player in first["players"]]
        second_scores = [(player["playerId"], player["overallScore"]) for player in second["players"]]
        self.assertEqual(first_scores, second_scores)

    def test_match_awards_identify_the_opponent(self):
        result = build_tournament_report_cards(self.conn, 99)
        dominant = next(item for item in result["highlights"] if item["title"] == "Most dominant game")
        self.assertEqual(dominant["opponentName"], "Bravo / Other")

    def test_comeback_awards_require_distinct_evidence(self):
        result = build_tournament_report_cards(self.conn, 99)
        titles = [item["title"] for item in result["highlights"]]
        self.assertNotIn("Comeback player", titles)
        self.assertNotIn("Largest comeback", titles)

    def test_game_grade_uses_two_round_neutral_prior(self):
        cards = []
        for player_id, rounds, value in ((1, 2, 10), (2, 4, 9), (3, 4, 2)):
            cards.append({
                "playerId": player_id,
                "rounds": rounds,
                "ppr": value,
                "dpr": value,
                "pprVsExpected": value,
                "consistencyRaw": value,
                "clutchNet": value,
                "recoveryNet": value,
                "largeSwingsConceded": 0,
            })
        _apply_game_scores(cards)
        perfect_two_round_sample = cards[0]
        self.assertEqual(perfect_two_round_sample["observedPerformanceScore"], 100.0)
        self.assertEqual(perfect_two_round_sample["overallScore"], 75.0)
        self.assertEqual(perfect_two_round_sample["sampleConfidence"], 0.5)

    def test_equal_performance_grades_separate_on_sustained_evidence(self):
        players = [
            {"playerId": 1, "teamId": "A", "performanceGrade": 78.5, "games": 3, "rounds": 19,
             "matchReportCards": [{"pprVsExpected": 0.5}] * 3},
            {"playerId": 2, "teamId": "B", "performanceGrade": 78.5, "games": 5, "rounds": 20,
             "matchReportCards": [{"pprVsExpected": 0.5}] * 5},
        ]
        _apply_tournament_resume_scores(players, [], event_complete=True)
        self.assertEqual(players[0]["performanceGrade"], players[1]["performanceGrade"])
        self.assertGreater(players[1]["sustainedEvidenceScore"], players[0]["sustainedEvidenceScore"])
        self.assertEqual(players[1]["overallScore"], players[0]["overallScore"])
        self.assertGreater(players[1]["mvpScore"], players[0]["mvpScore"])

    def test_tournament_advancement_does_not_change_player_grade(self):
        players = [
            {"playerId": 1, "teamId": "A", "performanceGrade": 76.5, "games": 7, "rounds": 49,
             "matchReportCards": [{"pprVsExpected": 1.44}] * 7},
        ]
        _apply_tournament_resume_scores(players, [], event_complete=True)
        self.assertEqual(players[0]["overallScore"], 76.5)
        self.assertEqual(players[0]["grade"], "C")
        self.assertNotEqual(players[0]["mvpScore"], players[0]["overallScore"])

    def test_extra_poor_games_do_not_create_a_sustained_bonus(self):
        players = [
            {"playerId": 1, "teamId": "A", "performanceGrade": 70, "games": 3, "rounds": 18,
             "matchReportCards": [{"pprVsExpected": 0.5}] * 3},
            {"playerId": 2, "teamId": "B", "performanceGrade": 70, "games": 5, "rounds": 30,
             "matchReportCards": [{"pprVsExpected": 0.5}] * 2 + [{"pprVsExpected": -0.5}] * 3},
        ]
        _apply_tournament_resume_scores(players, [], event_complete=True)
        self.assertLess(players[1]["sustainedEvidenceScore"], players[0]["sustainedEvidenceScore"])

    def test_completed_double_elimination_final_separates_champion_and_runner_up(self):
        players = [
            {"playerId": 1, "teamId": "champion", "performanceGrade": 80.2, "games": 7, "rounds": 52,
             "matchReportCards": [{"pprVsExpected": 0.5}] * 7},
            {"playerId": 2, "teamId": "runner-up", "performanceGrade": 81.0, "games": 5, "rounds": 32,
             "matchReportCards": [{"pprVsExpected": 0.5}] * 5},
        ]
        matches = [
            {"matchId": "29", "gameId": 1, "winnerTeamId": "runner-up", "players": [
                {"teamId": "runner-up"}, {"teamId": "champion"},
            ]},
            {"matchId": "30", "gameId": 1, "winnerTeamId": "champion", "players": [
                {"teamId": "runner-up"}, {"teamId": "champion"},
            ]},
            {"matchId": "30", "gameId": 2, "winnerTeamId": "champion", "players": [
                {"teamId": "runner-up"}, {"teamId": "champion"},
            ]},
        ]

        _apply_tournament_resume_scores(players, matches, event_complete=True, bracket_type="W")

        champion, runner_up = players
        self.assertEqual(champion["depthScore"], 100.0)
        self.assertEqual(runner_up["depthScore"], 0.0)
        self.assertGreater(champion["mvpScore"], runner_up["mvpScore"])


if __name__ == "__main__":
    unittest.main()
