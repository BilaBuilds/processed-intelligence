import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import select


class TestSelectFilters(unittest.TestCase):
    def test_deadline_and_status_filters(self) -> None:
        now = datetime.now(timezone.utc)
        future_deadline = (now + timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z")
        past_deadline = (now - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")

        records = [
            {
                "id": "good",
                "score": 45,
                "deadline": future_deadline,
                "status": "active",
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
                "id": "awarded",
                "score": 70,
                "deadline": future_deadline,
                "status": "complete",
                "release_tags": ["award"],
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
                {"TENDER_MIN_SCORE": "20", "TENDER_SHORTLIST_N": "10"},
                clear=False,
            ):
                result = select.run(context)

            self.assertEqual(result["shortlist_count"], 1)
            with open(result["shortlist_file"], encoding="utf-8") as f:
                shortlist = json.load(f)["opportunities"]

            self.assertEqual(len(shortlist), 1)
            self.assertEqual(shortlist[0]["id"], "good")


if __name__ == "__main__":
    unittest.main()

