import sqlite3
import unittest

from automated_pattern_discovery import (
    _apply_definition,
    _candidate_definitions,
    discovery_status,
)


class AutomatedPatternDiscoveryTests(unittest.TestCase):
    def test_status_is_read_only_before_worker_initializes_registry(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        result = discovery_status(conn)
        self.assertEqual(result["status"], "WAITING")
        self.assertFalse(result["safety"]["productionWeightsChanged"])
        tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        self.assertEqual(tables, 0)

    def test_candidates_are_generated_from_development_data_only(self):
        rows = [{"features": {name: 0.2 for name in (
            "pprDelta", "fourBaggerDelta", "bagsInDelta", "adjustedPprDelta",
            "recentFormDelta", "roundLossRateDelta", "recentRoundLossDelta",
            "teamSkillGapDelta", "venueEffectDelta", "formatEffectDelta",
        )}}]
        definitions = _candidate_definitions(rows)
        self.assertEqual(len(definitions), 36)
        self.assertTrue(all("source" in row for row in definitions))

    def test_discovered_transform_preserves_side_orientation(self):
        definition = {
            "key": "auto_test", "family": "PPR_CONTEXT", "source": "recentFormDelta"
        }
        rows = [
            {"features": {"pprDelta": 0.5, "recentFormDelta": -0.2}},
            {"features": {"pprDelta": -0.5, "recentFormDelta": 0.2}},
        ]
        transformed = _apply_definition(rows, definition)
        self.assertAlmostEqual(transformed[0]["features"]["auto_test"], 0.1)
        self.assertAlmostEqual(transformed[1]["features"]["auto_test"], -0.1)


if __name__ == "__main__":
    unittest.main()
