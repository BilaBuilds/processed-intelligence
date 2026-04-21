import json
import tempfile
import unittest
from pathlib import Path

from outreach.samples import build_sample_bundle, latest_successful_run_id


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class OutreachSampleTests(unittest.TestCase):
    def test_sample_generation_is_deterministic_and_includes_intelligence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            run_dir = runs_dir / "2026-04-11_165252"
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run_manifest.json", {"run_id": run_dir.name, "status": "success"})
            write_json(
                run_dir / "shortlist.json",
                {
                    "opportunities": [
                        {"id": "s1", "title": "North East Retrofit", "region": "North East", "buyer_name": "Buyer A", "score": 40, "source_url": "https://example.com/s1"},
                        {"id": "s2", "title": "Midlands Civils", "region": "Midlands", "buyer_name": "Buyer B", "score": 39, "source_url": "https://example.com/s2"},
                    ]
                },
            )
            write_jsonl(
                run_dir / "review_candidates.jsonl",
                [
                    {"id": "r1", "title": "North East Maintenance", "region": "North East", "buyer_name": "Buyer C", "score": 18, "source_url": "https://example.com/r1"},
                    {"id": "r2", "title": "South Works", "region": "South", "buyer_name": "Buyer D", "score": 17, "source_url": "https://example.com/r2"},
                ],
            )
            write_jsonl(
                run_dir / "market_intelligence.jsonl",
                [
                    {"id": "m1", "title": "Awarded North East Retrofit", "region": "North East", "buyer_name": "Buyer E", "rejection_reasons": ["award"], "source_url": "https://example.com/m1"},
                    {"id": "m2", "title": "Award update South", "region": "South", "buyer_name": "Buyer F", "rejection_reasons": ["awardUpdate"], "source_url": "https://example.com/m2"},
                ],
            )
            write_jsonl(
                run_dir / "rejected_tenders.jsonl",
                [
                    {"id": "x1", "title": "Rejected", "rejection_reasons": ["inactive_status"]},
                ],
            )

            contact = {
                "id": 1,
                "company_name": "North Build",
                "contact_name": "Sam",
                "region": "North East",
                "sectors": "retrofit, maintenance",
            }
            sample = build_sample_bundle(run_id=run_dir.name, contact=contact, runs_dir=runs_dir)

            self.assertEqual(sample["counts"], {"shortlist": 2, "review": 2, "market_intelligence": 2})
            self.assertEqual(sample["shortlist"][0]["id"], "s1")
            self.assertEqual(sample["review_candidates"][0]["id"], "r1")
            self.assertEqual(sample["market_intelligence"][0]["id"], "m1")
            self.assertNotIn("Rejected", json.dumps(sample, sort_keys=True))

    def test_latest_successful_run_resolution_works(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            old_run = runs_dir / "2026-04-10_100000"
            new_run = runs_dir / "2026-04-11_100000"
            old_run.mkdir(parents=True, exist_ok=True)
            new_run.mkdir(parents=True, exist_ok=True)
            write_json(old_run / "run_manifest.json", {"status": "failed"})
            write_json(new_run / "run_manifest.json", {"status": "success"})
            self.assertEqual(latest_successful_run_id(runs_dir), "2026-04-11_100000")


if __name__ == "__main__":
    unittest.main()
