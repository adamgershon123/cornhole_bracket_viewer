import json
import sqlite3
import unittest

from outcome_ingestion import initialize_outcome_schema
from prediction_evaluation import prediction_evaluation_report
from shadow_predictions import initialize_shadow_schema


class PredictionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        initialize_shadow_schema(self.conn)
        initialize_outcome_schema(self.conn)
        self.conn.execute(
            """
            INSERT INTO prediction_records(
                model_version, feature_version, data_cutoff_at, event_id, match_id,
                side_a_player_ids_json, side_b_player_ids_json, evidence_tier,
                prediction_status, side_a_probability, side_b_probability,
                raw_side_a_probability, shrinkage_factor, feature_hash,
                features_json, created_at
            ) VALUES ('fitted-ppr-logistic-v1', 'test', '2026-01-01T00:00:00+00:00',
                      '1', '2', '[10,11]', '[20,21]', 'A', 'PREDICTED',
                      .7, .3, .7, 1, 'hash', ?, '2026-01-01T00:00:00+00:00')
            """,
            (json.dumps({"modelReady": True, "deltasAminusB": {"predictivePpr": 0.8}}),),
        )
        prediction_id = self.conn.execute(
            "SELECT prediction_id FROM prediction_records"
        ).fetchone()[0]
        self.conn.execute(
            """
            INSERT INTO shadow_prediction_runs(
                prediction_id,event_id,match_id,model_version,status,
                scheduled_start_at,recorded_at,timing_basis
            ) VALUES (?, '1','2','fitted-ppr-logistic-v1','PREDICTED',
                      '2026-01-01T01:00:00+00:00','2026-01-01T00:00:00+00:00',
                      'SCHEDULED_MATCH_START')
            """,
            (prediction_id,),
        )
        self.conn.execute(
            """
            INSERT INTO normalized_match_outcomes(
                event_id,match_id,home_score,away_score,home_won,source_endpoint,
                resolved_at,recorded_at
            ) VALUES ('1','2',15,21,0,'test',
                      '2026-01-01T02:00:00+00:00','2026-01-01T02:00:00+00:00')
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_reports_final_score_probability_error_and_miss_explanation(self):
        report = prediction_evaluation_report(self.conn)
        item = report["evaluations"][0]
        self.assertFalse(item["correct"])
        self.assertEqual(item["actualWinner"], "SIDE_B")
        self.assertEqual(item["actualMargin"], 6)
        self.assertEqual(item["probabilityError"], 0.7)
        self.assertEqual(item["brierScore"], 0.49)
        self.assertEqual(
            item["explanation"]["classification"],
            "UPSET_OR_MODEL_MISS",
        )
        self.assertEqual(item["featureSummary"]["predictivePprDelta"], 0.8)


if __name__ == "__main__":
    unittest.main()
