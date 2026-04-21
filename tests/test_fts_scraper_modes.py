import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import fts_scraper


class DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestFtsScraperModes(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_incremental_mode_uses_watermark(self) -> None:
        cfg = fts_scraper.Config(base_dir=self.temp_dir, ingest_mode="incremental")
        cfg.ensure_dirs()
        cfg.last_run_file.write_text("2026-04-01T00:00:00+00:00", encoding="utf-8")
        now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)

        plan = fts_scraper.determine_windows(cfg, now)

        self.assertEqual(plan["mode"], "incremental")
        self.assertEqual(plan["windows"][0][0].isoformat(), "2026-04-01T00:00:00+00:00")
        self.assertEqual(plan["windows"][0][1], now)

    def test_recovery_mode_uses_recent_bounded_window(self) -> None:
        cfg = fts_scraper.Config(base_dir=self.temp_dir, ingest_mode="recovery", recovery_days=2)
        cfg.ensure_dirs()
        now = datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc)

        plan = fts_scraper.determine_windows(cfg, now)

        self.assertEqual(plan["mode"], "recovery")
        self.assertEqual(plan["windows"][0][0].isoformat(), "2026-04-03T09:30:00+00:00")
        self.assertEqual(plan["windows"][0][1], now)

    def test_backfill_mode_initializes_deterministic_chunk(self) -> None:
        cfg = fts_scraper.Config(
            base_dir=self.temp_dir,
            ingest_mode="backfill",
            backfill_chunk_days=3,
            backfill_start="2026-03-01T00:00:00+00:00",
            backfill_end="2026-03-10T00:00:00+00:00",
        )
        cfg.ensure_dirs()
        now = datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc)

        plan = fts_scraper.determine_windows(cfg, now)

        self.assertEqual(plan["mode"], "backfill")
        self.assertEqual(len(plan["windows"]), 1)
        self.assertEqual(plan["windows"][0][0].isoformat(), "2026-03-01T00:00:00+00:00")
        self.assertEqual(plan["windows"][0][1].isoformat(), "2026-03-04T00:00:00+00:00")
        self.assertTrue(cfg.backfill_state_file.exists())

    def test_backfill_state_resumes_from_next_chunk(self) -> None:
        cfg = fts_scraper.Config(
            base_dir=self.temp_dir,
            ingest_mode="backfill",
            backfill_chunk_days=2,
            backfill_start="2026-03-01T00:00:00+00:00",
            backfill_end="2026-03-07T00:00:00+00:00",
        )
        cfg.ensure_dirs()
        state = {
            "mode": "backfill",
            "backfill_start": "2026-03-01T00:00:00+00:00",
            "backfill_end": "2026-03-07T00:00:00+00:00",
            "chunk_days": 2,
            "next_chunk_start": "2026-03-05T00:00:00+00:00",
            "active_chunk_start": None,
            "active_chunk_end": None,
            "last_completed_chunk_start": "2026-03-03T00:00:00+00:00",
            "last_completed_chunk_end": "2026-03-05T00:00:00+00:00",
            "chunks_total": 3,
            "chunks_completed": 2,
            "request_count_total": 22,
            "updated_at": "2026-03-05T00:00:00+00:00",
            "completed": False,
        }
        fts_scraper.save_backfill_state(cfg, state)

        plan = fts_scraper.determine_windows(cfg, datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc))

        self.assertEqual(plan["windows"][0][0].isoformat(), "2026-03-05T00:00:00+00:00")
        self.assertEqual(plan["windows"][0][1].isoformat(), "2026-03-07T00:00:00+00:00")

    def test_backfill_manifest_truthful_when_request_cap_hit(self) -> None:
        cfg = fts_scraper.Config(
            base_dir=self.temp_dir,
            ingest_mode="backfill",
            backfill_chunk_days=2,
            backfill_start="2026-03-01T00:00:00+00:00",
            backfill_end="2026-03-05T00:00:00+00:00",
        )
        cfg.ensure_dirs()

        with patch("src.fts_scraper.build_session", return_value=DummySession()), patch(
            "src.fts_scraper.iter_pages",
            return_value={"releases": [{"id": "fat:1"}], "request_count": 200, "hit_request_cap": True},
        ):
            result = fts_scraper.fetch_fts_releases(cfg)

        metadata = result["metadata"]
        self.assertTrue(metadata["fts_hit_request_cap"])
        self.assertTrue(metadata["fts_partial_backfill"])
        self.assertFalse(metadata["fts_backfill_completed"])


if __name__ == "__main__":
    unittest.main()
