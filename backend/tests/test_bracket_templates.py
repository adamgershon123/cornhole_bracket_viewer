import json
import os
import tempfile
import unittest

from bracket_templates import (
    infer_bracket_layout,
    repository_bracket_templates,
    select_template,
    validate_published_layout,
)


def completed_four_team_event(event_id):
    rows = []
    for match_id, top, bottom, home, away, round_desc in (
        (1, "A", "B", 21, 10, "Semifinal"),
        (2, "C", "D", 12, 21, "Semifinal"),
        (3, "A", "D", 21, 18, "Final"),
    ):
        for position, team in (("T", top), ("B", bottom)):
            rows.append({
                "bracketmatchid": match_id,
                "bracketpos": position,
                "bracketteamid": team,
                "rounddesc": round_desc,
                "bracketside": "W",
                "scores": [{"scorehome": home, "scoreaway": away}],
            })
    return {
        "eventInfo": {
            "eventID": event_id,
            "bracketType": "S",
        },
        "bracketDetails": rows,
    }


def completed_four_team_double_elimination(event_id):
    rows = []
    for match_id, top, bottom, home, away, round_desc, side in (
        (1, "A", "B", 21, 10, "Round 1", "W"),
        (2, "C", "D", 21, 12, "Round 1", "W"),
        (3, "B", "D", 21, 12, "Round 1", "L"),
        (4, "A", "C", 21, 17, "Semi-Finals", "W"),
        (5, "C", "B", 21, 14, "Semi-Finals", "L"),
        (6, "A", "C", 21, 19, "FINAL", "L"),
    ):
        for position, team in (("T", top), ("B", bottom)):
            rows.append({
                "bracketmatchid": match_id,
                "bracketpos": f"M{match_id}{position}",
                "bracketteamid": team,
                "rounddesc": round_desc,
                "bracketside": side,
                "scores": [{"scorehome": home, "scoreaway": away}],
            })
    rows.append({
        "bracketmatchid": 7,
        "bracketpos": "M7T",
        "bracketteamid": None,
        "rounddesc": "Champion",
        "bracketside": "W",
        "scores": [],
    })
    return {
        "eventInfo": {"eventID": event_id, "bracketType": "D"},
        "bracketDetails": rows,
    }


class BracketTemplateTests(unittest.TestCase):
    def test_completed_results_reveal_winner_routes(self):
        layout = infer_bracket_layout(completed_four_team_event(1))
        self.assertEqual(
            layout["edges"]["1:W"],
            {"matchId": 3, "position": "T"},
        )
        self.assertEqual(
            layout["edges"]["2:W"],
            {"matchId": 3, "position": "B"},
        )

    def test_repeated_layout_becomes_validated_template(self):
        with tempfile.TemporaryDirectory() as directory:
            for event_id in (1, 2):
                with open(
                    os.path.join(directory, f"event_{event_id}.json"),
                    "w",
                    encoding="utf-8",
                ) as target:
                    json.dump(completed_four_team_event(event_id), target)
            repository = repository_bracket_templates(directory)
        template = repository["templates"]["4:S:W"]
        self.assertEqual(template["status"], "VALIDATED_TEMPLATE")
        self.assertEqual(template["edgeCoverageRate"], 1.0)

    def test_complete_published_double_elimination_graph_is_authoritative(self):
        layout = infer_bracket_layout(completed_four_team_double_elimination(7))
        validation = validate_published_layout(layout)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["observedEdges"], 8)
        self.assertEqual(layout["edges"]["4:L"], {"matchId": 5, "position": "T"})
        self.assertEqual(layout["edges"]["4:W"], {"matchId": 6, "position": "T"})

    def test_one_complete_published_graph_can_map_a_new_frozen_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            raw_dir = os.path.join(
                directory, "season_platform", "raw", "brackets"
            )
            os.makedirs(raw_dir)
            with open(
                os.path.join(raw_dir, "event_7.json"), "w", encoding="utf-8"
            ) as target:
                json.dump(completed_four_team_double_elimination(7), target)
            repository = repository_bracket_templates(directory)
        frozen = completed_four_team_double_elimination(8)
        for row in frozen["bracketDetails"]:
            if int(row["bracketmatchid"]) > 2:
                row["bracketteamid"] = -1
                row["scores"] = []
        template = select_template(repository, frozen)
        self.assertIsNotNone(template)
        self.assertEqual(template["status"], "VALIDATED_TEMPLATE")
        self.assertTrue(template["validation"]["valid"])


if __name__ == "__main__":
    unittest.main()
