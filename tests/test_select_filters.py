import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import select


class TestSelectFilters(unittest.TestCase):
    def test_selection_buckets_and_rejection_reasons(self) -> None:
        now = datetime.now(timezone.utc)
        future_deadline = (now + timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z")
        past_deadline = (now - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        near_deadline = (now + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")

        records = [
            {
                "id": "good",
                "score": 45,
                "deadline": future_deadline,
                "status": "active",
                "release_tags": ["tender"],
            },
            {
                "id": "open-review",
                "score": 18,
                "deadline": future_deadline,
                "status": "open",
                "release_tags": ["tender"],
            },
            {
                "id": "stale",
                "score": 60,
                "deadline": past_deadline,
                "status": "active",
                "release_tags": ["tender"],
            },
            {
                "id": "too-late",
                "score": 55,
                "deadline": near_deadline,
                "status": "active",
                "release_tags": ["tender"],
            },
            {
                "id": "awarded",
                "score": 70,
                "deadline": future_deadline,
                "status": "active",
                "release_tags": ["award"],
            },
            {
                "id": "award-update",
                "score": 70,
                "deadline": future_deadline,
                "status": "active",
                "release_tags": ["awardUpdate"],
            },
            {
                "id": "inactive",
                "score": 70,
                "deadline": future_deadline,
                "status": "closed",
                "release_tags": ["tender"],
            },
            {
                "id": "low",
                "score": 12,
                "deadline": future_deadline,
                "status": "active",
                "release_tags": ["tender"],
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            scored_file = run_dir / "scored_tenders.jsonl"
            with open(scored_file, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")

            context = {"run_dir": run_dir, "scored_file": scored_file}
            with patch.dict(
                os.environ,
                {"TENDER_MIN_SCORE": "20", "TENDER_SHORTLIST_N": "10"},
                clear=False,
            ):
                result = select.run(context)

            self.assertEqual(result["shortlist_count"], 1)
            self.assertEqual(result["review_count"], 1)
            self.assertEqual(result["market_intelligence_count"], 2)
            self.assertEqual(result["rejected_count"], 4)
            with open(result["shortlist_file"], encoding="utf-8") as f:
                shortlist = json.load(f)["opportunities"]

            self.assertEqual(len(shortlist), 1)
            self.assertEqual(shortlist[0]["id"], "good")
            self.assertEqual(shortlist[0]["selection_bucket"], "shortlist")
            self.assertEqual(
                result["rejection_reason_counts"],
                {
                    "inactive_status": 1,
                    "award": 1,
                    "awardUpdate": 1,
                    "below_threshold": 1,
                    "stale_deadline": 2,
                },
            )

            review_lines = (run_dir / "review_candidates.jsonl").read_text(encoding="utf-8").splitlines()
            review = [json.loads(line) for line in review_lines]
            self.assertEqual(review, [{**records[1], "selection_bucket": "review"}])

            market_lines = (run_dir / "market_intelligence.jsonl").read_text(encoding="utf-8").splitlines()
            market = [json.loads(line) for line in market_lines]
            self.assertEqual(
                market,
                [
                    {**records[4], "selection_bucket": "market_intelligence", "rejection_reasons": ["award"]},
                    {**records[5], "selection_bucket": "market_intelligence", "rejection_reasons": ["awardUpdate"]},
                ],
            )

            rejected_lines = (run_dir / "rejected_tenders.jsonl").read_text(encoding="utf-8").splitlines()
            rejected = [json.loads(line) for line in rejected_lines]
            self.assertEqual(
                rejected,
                [
                    {
                        **records[2],
                        "selection_bucket": "rejected",
                        "rejection_reasons": ["stale_deadline"],
                    },
                    {
                        **records[3],
                        "selection_bucket": "rejected",
                        "rejection_reasons": ["stale_deadline"],
                    },
                    {
                        **records[6],
                        "selection_bucket": "rejected",
                        "rejection_reasons": ["inactive_status"],
                    },
                    {
                        **records[7],
                        "selection_bucket": "rejected",
                        "rejection_reasons": ["below_threshold"],
                    },
                ],
            )

            shortlist_jsonl = (run_dir / "shortlist.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                [json.loads(line) for line in shortlist_jsonl],
                [
                    {
                        "id": "good",
                        "score": 45,
                        "deadline": future_deadline,
                        "status": "active",
                        "release_tags": ["tender"],
                        "selection_bucket": "shortlist",
                    }
                ],
            )

    def test_fallback_promotes_top_review_when_shortlist_empty(self) -> None:
        now = datetime.now(timezone.utc)
        future_deadline = (now + timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z")
        records = [
            {
                "id": "review-1",
                "score": 19,
                "deadline": future_deadline,
                "status": "active",
                "release_tags": ["tender"],
            },
            {
                "id": "review-2",
                "score": 17,
                "deadline": future_deadline,
                "status": "active",
                "release_tags": ["tender"],
            },
            {
                "id": "low",
                "score": 10,
                "deadline": future_deadline,
                "status": "active",
                "release_tags": ["tender"],
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            scored_file = run_dir / "scored_tenders.jsonl"
            with open(scored_file, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")

            context = {"run_dir": run_dir, "scored_file": scored_file}
            with patch.dict(
                os.environ,
                {"TENDER_MIN_SCORE": "20", "TENDER_REVIEW_MIN_SCORE": "15", "TENDER_SHORTLIST_N": "10"},
                clear=False,
            ):
                result = select.run(context)

            self.assertEqual(result["shortlist_count"], 2)
            self.assertEqual(result["review_count"], 0)
            self.assertEqual(result["select_fallback_promoted_count"], 2)
            shortlist = json.loads((run_dir / "shortlist.json").read_text(encoding="utf-8"))["opportunities"]
            self.assertEqual([rec["id"] for rec in shortlist], ["review-1", "review-2"])
            self.assertTrue(all(rec["selection_fallback"] == "review_promotion" for rec in shortlist))


if __name__ == "__main__":
    unittest.main()
