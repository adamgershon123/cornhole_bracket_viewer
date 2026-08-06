import json
import os
import tempfile
import unittest

from bracket_templates import infer_bracket_layout, repository_bracket_templates


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


if __name__ == "__main__":
    unittest.main()
