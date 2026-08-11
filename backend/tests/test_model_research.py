import json
import sqlite3
import unittest

from model_research import cached_model_research_inputs, model_research_report


class ModelResearchReportTests(unittest.TestCase):
    def test_cached_inputs_recover_saved_evidence_without_schema_setup(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE historical_backtest_snapshots(payload_json TEXT, generated_at TEXT);
            CREATE TABLE historical_tournament_replay_state(
              state_id INTEGER, status TEXT, candidates_remaining INTEGER,
              created INTEGER, failed INTEGER, last_event_id INTEGER,
              last_error TEXT, updated_at TEXT
            );
            CREATE TABLE bracket_prediction_snapshots(snapshot_type TEXT, payload_json TEXT);
            CREATE TABLE prediction_learning_examples(id INTEGER);
            """
        )
        conn.execute(
            "INSERT INTO historical_backtest_snapshots VALUES(?, '2026-08-11')",
            (json.dumps({"holdoutMatchups": 4590, "models": []}),),
        )
        conn.execute(
            "INSERT INTO historical_tournament_replay_state VALUES(1,'RUNNING',12,345,0,99,NULL,'now')"
        )
        conn.execute(
            "INSERT INTO bracket_prediction_snapshots VALUES('PREGAME', ?)",
            (json.dumps({"snapshotOrigin": "HISTORICAL_REPLAY"}),),
        )
        conn.execute("INSERT INTO prediction_learning_examples VALUES(1)")

        performance, learning = cached_model_research_inputs(conn)

        self.assertEqual(performance["historicalBacktest"]["holdoutMatchups"], 4590)
        self.assertEqual(
            performance["historicalTournamentReplay"]["historicalReplaySnapshots"], 1
        )
        self.assertEqual(learning["promotionGate"]["currentExamples"], 1)

    def test_builds_findings_without_overstating_small_gain(self):
        performance = {
            "historicalBacktest": {
                "status": "COMPLETE",
                "archiveMatchups": 1000,
                "eligibleMatchups": 800,
                "holdoutMatchups": 200,
                "models": [
                    {"model": "PPR only", "accuracy": .68, "brierScore": .205, "logLoss": .59, "evaluatedMatchups": 200},
                    {
                        "model": "PPR + form", "accuracy": .685, "brierScore": .203,
                        "logLoss": .588, "evaluatedMatchups": 200,
                        "pairedVsPpr": {"finalTest": {
                            "disagreements": 12, "netAdditionalCorrect": 1,
                            "mcnemarPValueApprox": .7, "statisticallyClearAt95": False,
                        }},
                    },
                ],
            },
            "historicalTournamentReplay": {"complete": 99},
        }
        learning = {"promotionGate": {"currentExamples": 50}, "learningPolicy": "Controlled."}
        collection = {
            "status": "WORKING", "ledger": {"games": 2500, "rounds": 50000},
            "queue": {"pending": 20, "complete": 40},
            "throughput": {"lastHour": {"gamesDownloaded": 12, "roundsAdded": 240}},
        }
        report = model_research_report(performance, learning, collection)
        challenger = next(row for row in report["experiments"] if row["role"] == "CHALLENGER")
        self.assertEqual(challenger["status"], "PROMISING")
        self.assertFalse(challenger["statisticallyClearAt95"])
        self.assertIn("No challenger is conclusive", report["findings"][2]["headline"])
        self.assertEqual(report["pipeline"][3]["status"], "NEXT")
        self.assertEqual(report["activity"]["ledger"]["games"], 2500)
        self.assertEqual(report["activity"]["lastHour"]["roundsAdded"], 240)
        self.assertEqual(report["activity"]["analysis"]["modelMatchEvaluations"], 400)

    def test_marks_only_clear_dual_improvement_as_validated_candidate(self):
        performance = {
            "historicalBacktest": {"models": [
                {"model": "PPR only", "accuracy": .68, "brierScore": .205},
                {"model": "Candidate", "accuracy": .70, "brierScore": .195,
                 "pairedVsPpr": {"finalTest": {"statisticallyClearAt95": True}}},
            ]},
        }
        report = model_research_report(performance, {})
        candidate = next(row for row in report["experiments"] if row["name"] == "Candidate")
        self.assertEqual(candidate["status"], "VALIDATED_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
