import unittest

from src import match


class TestMatchDisqualifiers(unittest.TestCase):
    def test_disqualify_non_construction_keywords(self) -> None:
        rec = {
            "title": "Catering and fitness training services",
            "description": "Facilities and training support for staff wellbeing",
            "region": "London",
            "value": 220000,
        }

        out = match.score_tender(rec)
        self.assertEqual(out["score"], 0)
        self.assertEqual(out["score_breakdown"]["region_matched"], "disqualified")
        self.assertIn("disqualified_by", out["score_breakdown"])

    def test_keep_construction_contracts_scored(self) -> None:
        rec = {
            "title": "Groundworks and civil engineering package",
            "description": "Construction and refurbishment works",
            "region": "West Midlands",
            "value": 350000,
            "cpv_codes": ["45232452"],
            "procurement_category": "works",
        }

        out = match.score_tender(rec)
        self.assertGreater(out["score"], 0)
        self.assertNotIn("disqualified_by", out["score_breakdown"])

    def test_design_only_is_now_hard_disqualified(self) -> None:
        rec = {
            "title": "Design only services for public realm scheme",
            "description": "Detailed design only package",
            "region": "London",
            "value": 220000,
        }

        out = match.score_tender(rec)
        self.assertEqual(out["score"], 0)
        self.assertEqual(out["score_breakdown"]["disqualified_by"], "design only")

    def test_cpv_only_match_can_score_without_keyword_match(self) -> None:
        rec = {
            "title": "Lot 3 package",
            "description": "Specialist package with limited prose",
            "region": "London",
            "value": 400000,
            "cpv_codes": ["45232452"],
            "procurement_category": "works",
            "deadline_at": "2099-05-20T12:00:00Z",
        }

        out = match.score_tender(rec)
        self.assertGreater(out["score"], 0)
        self.assertTrue(out["score_breakdown"]["cpv_match"])
        self.assertFalse(out["score_breakdown"]["cpv_missing"])

    def test_keyword_only_match_allowed_when_cpv_missing(self) -> None:
        rec = {
            "title": "Groundworks package",
            "description": "Civil engineering works",
            "region": "London",
            "value": 400000,
            "cpv_codes": [],
            "procurement_category": "",
        }

        out = match.score_tender(rec)
        self.assertGreater(out["score"], 0)
        self.assertTrue(out["score_breakdown"]["cpv_missing"])
        self.assertFalse(out["score_breakdown"]["cpv_match"])

    def test_missing_keyword_and_cpv_signal_scores_zero(self) -> None:
        rec = {
            "title": "General package",
            "description": "Limited information provided",
            "region": "London",
            "value": 400000,
            "cpv_codes": [],
            "procurement_category": "",
        }

        out = match.score_tender(rec)
        self.assertEqual(out["score"], 0)
        self.assertTrue(out["score_breakdown"]["cpv_missing"])
        self.assertEqual(
            out["score_breakdown"]["disqualified_by"],
            "missing_keyword_and_cpv_signal",
        )


if __name__ == "__main__":
    unittest.main()
