import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import patterns


class TestPatterns(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.history_run = self.temp_dir / "data" / "runs" / "2026-04-01_120000"
        self.current_run = self.temp_dir / "data" / "runs" / "2026-04-02_120000"
        self.history_run.mkdir(parents=True, exist_ok=True)
        self.current_run.mkdir(parents=True, exist_ok=True)

        (self.history_run / "decision_all.json").write_text(
            json.dumps(
                {
                    "opportunities": [
                        {
                            "id": "h1",
                            "title": "Civil engineering refurbishment package",
                            "buyer": "Example Borough Council",
                            "region": "London",
                            "value": 250000,
                            "deadline_days": 14,
                            "decision_verdict": "REVIEW",
                        },
                        {
                            "id": "h2",
                            "title": "Civil engineering refurbishment programme",
                            "buyer": "Example Borough Council",
                            "region": "London",
                            "value": 260000,
                            "deadline_days": 15,
                            "decision_verdict": "BID",
                        },
                        {
                            "id": "h3",
                            "title": "Cleaning services framework",
                            "buyer": "Risk Buyer Ltd",
                            "region": "London",
                            "value": 100000,
                            "deadline_days": 5,
                            "decision_verdict": "NO_BID",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        (self.current_run / "scored_tenders.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "c1",
                            "title": "Civil engineering refurbishment contract",
                            "buyer": "Example Borough Council",
                            "region": "London",
                            "value": 255000,
                            "deadline": "2099-04-15T00:00:00Z",
                            "score": 40,
                        }
                    ),
                    json.dumps(
                        {
                            "id": "c2",
                            "title": "Cleaning services support",
                            "buyer": "Risk Buyer Ltd",
                            "region": "London",
                            "value": 100000,
                            "deadline": "2099-04-10T00:00:00Z",
                            "score": 30,
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pattern_outputs_are_deterministic(self) -> None:
        context = {"run_dir": self.current_run, "scored_file": self.current_run / "scored_tenders.jsonl"}
        with patch.dict(
            os.environ,
            {
                "TENDER_PATTERN_MODE": "enabled_no_score_adjustment",
                "TENDER_PATTERN_HISTORY_RUN_LIMIT": "10",
                "TENDER_PATTERN_MAX_ADJUSTMENT": "5",
            },
            clear=False,
        ):
            first = patterns.run(dict(context))
            second = patterns.run(dict(context))

        self.assertEqual(first["pattern_signal_count"], second["pattern_signal_count"])
        self.assertEqual(first["pattern_adjusted_count"], second["pattern_adjusted_count"])

        first_signals = json.loads(Path(first["pattern_artifacts"]["pattern_signals_file"]).read_text(encoding="utf-8"))
        second_signals = json.loads(Path(second["pattern_artifacts"]["pattern_signals_file"]).read_text(encoding="utf-8"))
        self.assertEqual(first_signals, second_signals)

    def test_bounded_score_adjustment_is_enforced(self) -> None:
        context = {"run_dir": self.current_run, "scored_file": self.current_run / "scored_tenders.jsonl"}
        with patch.dict(
            os.environ,
            {
                "TENDER_PATTERN_MODE": "enabled_with_bounded_adjustment",
                "TENDER_PATTERN_HISTORY_RUN_LIMIT": "10",
                "TENDER_PATTERN_MAX_ADJUSTMENT": "1",
            },
            clear=False,
        ):
            result = patterns.run(dict(context))

        enriched_file = Path(result["pattern_artifacts"]["pattern_enriched_file"])
        rows = [json.loads(line) for line in enriched_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            self.assertLessEqual(abs(int(row["pattern_score_adjustment"])), 1)
            self.assertLessEqual(abs(int(row["score"]) - int(row["score_original"])), 1)


if __name__ == "__main__":
    unittest.main()
