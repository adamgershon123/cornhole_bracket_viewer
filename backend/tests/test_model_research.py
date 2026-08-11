import unittest

from model_research import model_research_report


class ModelResearchReportTests(unittest.TestCase):
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
