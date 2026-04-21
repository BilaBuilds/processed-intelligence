import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src import dedupe


class TestDedupeIdempotency(unittest.TestCase):
    def test_same_shortlist_only_sends_once(self) -> None:
        original_state_dir = dedupe.STATE_DIR
        original_db_path = dedupe.SENT_LOG_DB

        td_path = Path(tempfile.mkdtemp())
        try:
            run_dir = td_path / "run"
            run_dir.mkdir(parents=True, exist_ok=True)

            shortlist_file = run_dir / "shortlist.json"
            payload = {
                "opportunities": [
                    {"id": "cf:1", "title": "Tender A", "source": "cf"},
                    {"id": "cf:1", "title": "Tender A duplicate", "source": "cf"},
                    {"id": "fat:2", "title": "Tender B", "source": "fat"},
                ]
            }
            shortlist_file.write_text(json.dumps(payload), encoding="utf-8")

            dedupe.STATE_DIR = td_path / "state"
            dedupe.SENT_LOG_DB = dedupe.STATE_DIR / "sent_log.sqlite"

            try:
                context = {"run_dir": run_dir, "shortlist_file": shortlist_file}
                first = dedupe.run(context)
                second = dedupe.run(context)
            finally:
                dedupe.STATE_DIR = original_state_dir
                dedupe.SENT_LOG_DB = original_db_path

            self.assertEqual(first["new_count"], 2)
            self.assertEqual(second["new_count"], 0)
        finally:
            shutil.rmtree(td_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
