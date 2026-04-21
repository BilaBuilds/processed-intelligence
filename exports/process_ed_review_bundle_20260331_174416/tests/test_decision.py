import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import decision


class TestDecisionEngine(unittest.TestCase):
    def test_build_decision_is_deterministic_for_same_input(self) -> None:
        now = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)
        rec = {
            "id": "cf:123",
            "score": 48,
            "buyer": "Test Buyer",
            "value": 350000,
            "deadline": "2026-04-20T00:00:00Z",
            "score_breakdown": {"value": 25, "region": 10},
        }

        with patch.dict(
            os.environ,
            {
                "TENDER_DECISION_BID_MIN_SCORE": "40",
                "TENDER_DECISION_REVIEW_MIN_SCORE": "28",
                "TENDER_DECISION_TIGHT_DEADLINE_DAYS": "10",
            },
            clear=False,
        ):
            a = decision.build_decision(rec, now)
            b = decision.build_decision(rec, now)

        self.assertEqual(a["decision_verdict"], "BID")
        self.assertEqual(a["decision_verdict"], b["decision_verdict"])
        self.assertEqual(a["decision_confidence"], b["decision_confidence"])
        self.assertEqual(a["decision_reasons"], b["decision_reasons"])
        self.assertEqual(a["risk_flags"], b["risk_flags"])

    def test_run_passes_only_bid_and_review_by_default(self) -> None:
        now = datetime.now(timezone.utc)
        future = (now + timedelta(days=20)).strftime("%Y-%m-%dT00:00:00Z")
        near = (now + timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")

        payload = {
            "opportunities": [
                {
                    "id": "bid",
                    "score": 50,
                    "buyer": "Buyer A",
                    "value": 500000,
                    "deadline": future,
                    "score_breakdown": {"value": 25, "region": 10},
                },
                {
                    "id": "review",
                    "score": 30,
                    "buyer": "Buyer B",
                    "value": None,
                    "deadline": near,
                    "score_breakdown": {"value": 5, "region": 0},
                },
                {
                    "id": "no_bid",
                    "score": 12,
                    "buyer": "Buyer C",
                    "value": 10000,
                    "deadline": future,
                    "score_breakdown": {"value": 2, "region": 0},
                },
            ]
        }

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            shortlist_file = run_dir / "shortlist.json"
            shortlist_file.write_text(json.dumps(payload), encoding="utf-8")

            with patch.dict(
                os.environ,
                {"TENDER_DECISION_INCLUDE": "BID,REVIEW"},
                clear=False,
            ):
                result = decision.run({"run_dir": run_dir, "shortlist_file": shortlist_file})

            self.assertEqual(result["decision_total_count"], 3)
            self.assertEqual(result["decision_pass_count"], 2)

            with open(result["shortlist_file"], encoding="utf-8") as f:
                passed = json.load(f)["opportunities"]

            passed_ids = {rec["id"] for rec in passed}
            self.assertIn("bid", passed_ids)
            self.assertIn("review", passed_ids)
            self.assertNotIn("no_bid", passed_ids)


if __name__ == "__main__":
    unittest.main()

