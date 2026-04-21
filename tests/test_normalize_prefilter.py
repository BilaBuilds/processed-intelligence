import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import normalize


class TestNormalizePrefilter(unittest.TestCase):
    def _raw_record(
        self,
        notice_id: str,
        *,
        status: str = "active",
        tag: str = "tender",
        deadline: str | None = None,
        value: float | None = 500000,
        title: str = "Drainage improvement works",
    ) -> dict:
        return {
            "_source": "contracts_finder",
            "ocid": f"ocds-b5fd17-{notice_id}",
            "id": notice_id,
            "date": "2026-04-18T10:00:00+00:00",
            "tag": [tag],
            "tender": {
                "id": notice_id,
                "title": title,
                "description": "Civil engineering works",
                "status": status,
                "classification": {"scheme": "CPV", "id": "45232452"},
                "additionalClassifications": [{"scheme": "CPV", "id": "45112000"}],
                "value": {"amount": value, "currency": "GBP"} if value is not None else {"amount": None, "currency": "GBP"},
                "tenderPeriod": {"endDate": deadline},
                "mainProcurementCategory": "works",
            },
            "parties": [
                {
                    "name": "Croydon Council",
                    "roles": ["buyer"],
                    "address": {"region": "London"},
                }
            ],
        }

    def test_normalize_prefilters_status_deadline_and_value_and_keeps_cpv_codes(self) -> None:
        now = datetime.now(timezone.utc)
        keep_deadline = (now + timedelta(days=10)).isoformat()
        near_deadline = (now + timedelta(days=1)).isoformat()

        raw_records = [
            self._raw_record("good-1", deadline=keep_deadline, value=500000),
            self._raw_record("award-1", status="complete", tag="award", deadline=keep_deadline, value=500000),
            self._raw_record("late-1", deadline=near_deadline, value=500000),
            self._raw_record("small-1", deadline=keep_deadline, value=50000),
            self._raw_record("large-1", deadline=keep_deadline, value=2000000),
        ]

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_dir = base / "run"
            state_dir = base / "state"
            run_dir.mkdir(parents=True, exist_ok=True)
            state_dir.mkdir(parents=True, exist_ok=True)

            (state_dir / "job_history.json").write_text(
                json.dumps(
                    [
                        {"value": 850000},
                        {"value": 350000},
                        {"value": 500000},
                        {"value": 620000},
                        {"value": 280000},
                    ]
                ),
                encoding="utf-8",
            )

            raw_file = run_dir / "raw_tenders.jsonl"
            with open(raw_file, "w", encoding="utf-8") as handle:
                for rec in raw_records:
                    handle.write(json.dumps(rec) + "\n")

            result = normalize.run({"raw_file": raw_file, "run_dir": run_dir, "state_dir": state_dir})

            self.assertEqual(result["norm_count"], 3)
            self.assertEqual(result["norm_status_filtered_count"], 1)
            self.assertEqual(result["norm_deadline_filtered_count"], 1)
            self.assertEqual(result["norm_value_filtered_count"], 0)
            self.assertEqual(result["value_filter_mode"], "soft")

            normalized_rows = [
                json.loads(line)
                for line in (run_dir / "normalized_tenders.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(normalized_rows), 3)
            self.assertEqual(normalized_rows[0]["raw_id"], "good-1")
            self.assertEqual(normalized_rows[0]["cpv_codes"], ["45232452", "45112000"])
            self.assertEqual(normalized_rows[0]["procurement_category"], "works")
            penalties = {row["raw_id"]: row.get("soft_value_penalty", 0) for row in normalized_rows}
            self.assertEqual(penalties["good-1"], 0)
            self.assertEqual(penalties["small-1"], normalize.SOFT_VALUE_PENALTY)
            self.assertEqual(penalties["large-1"], normalize.SOFT_VALUE_PENALTY)

    def test_normalize_uses_hard_value_filter_with_enough_job_history(self) -> None:
        now = datetime.now(timezone.utc)
        keep_deadline = (now + timedelta(days=10)).isoformat()
        raw_records = [
            self._raw_record("good-1", deadline=keep_deadline, value=500000),
            self._raw_record("small-1", deadline=keep_deadline, value=50000),
            self._raw_record("large-1", deadline=keep_deadline, value=2000000),
        ]

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_dir = base / "run"
            state_dir = base / "state"
            run_dir.mkdir(parents=True, exist_ok=True)
            state_dir.mkdir(parents=True, exist_ok=True)

            (state_dir / "job_history.json").write_text(
                json.dumps(
                    [
                        {"value": 850000},
                        {"value": 350000},
                        {"value": 500000},
                        {"value": 620000},
                        {"value": 280000},
                        {"value": 450000},
                        {"value": 560000},
                        {"value": 410000},
                    ]
                ),
                encoding="utf-8",
            )

            raw_file = run_dir / "raw_tenders.jsonl"
            with open(raw_file, "w", encoding="utf-8") as handle:
                for rec in raw_records:
                    handle.write(json.dumps(rec) + "\n")

            result = normalize.run({"raw_file": raw_file, "run_dir": run_dir, "state_dir": state_dir})

            self.assertEqual(result["value_filter_mode"], "hard")
            self.assertEqual(result["norm_value_filtered_count"], 2)
            normalized_rows = [
                json.loads(line)
                for line in (run_dir / "normalized_tenders.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([row["raw_id"] for row in normalized_rows], ["good-1"])


if __name__ == "__main__":
    unittest.main()
