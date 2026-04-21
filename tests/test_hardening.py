"""
tests/test_hardening.py
=======================
T7 — Tests for all hardening changes (T1-T6).

Coverage:
  T1: Scheduler cooldown guard (src/run_guard.py)
  T2: CF release tag counting (src/ingest.py)
  T3: Buyer intel 5-field attachment (src/buyer_intel.py)
  T4: Timing visibility field logic (src/buyer_timing.py)
  T5: Timing label + marketing text fields (src/buyer_timing.py)
  T6: Manifest new fields + status codes (run_pipeline.py)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# T1 — Scheduler cooldown guard
# ---------------------------------------------------------------------------


class TestRunGuard:
    """Tests for src/run_guard.py — batch-aware cooldown guard."""

    def test_no_prior_run_returns_full(self, tmp_path: Path) -> None:
        """No state files → always run."""
        from src.run_guard import check_cooldown

        result = check_cooldown(tmp_path)
        assert result["run_mode"] == "full"
        assert result["cooldown_reason"] == ""

    def test_last_batch_zero_returns_full(self, tmp_path: Path) -> None:
        """Last FTS batch was 0 records → don't apply cooldown (quiet window)."""
        from src.run_guard import check_cooldown

        (tmp_path / "last_fts_run.txt").write_text(
            (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            encoding="utf-8",
        )
        (tmp_path / "last_fts_batch_count.txt").write_text("0", encoding="utf-8")

        result = check_cooldown(tmp_path)
        assert result["run_mode"] == "full"

    def test_within_cooldown_window_returns_skip(self, tmp_path: Path) -> None:
        """Last FTS batch had records and run was < cooldown_hours ago → cooldown_skip."""
        from src.run_guard import check_cooldown

        (tmp_path / "last_fts_run.txt").write_text(
            (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            encoding="utf-8",
        )
        (tmp_path / "last_fts_batch_count.txt").write_text("42", encoding="utf-8")

        with patch.dict(os.environ, {"TENDER_RUN_COOLDOWN_HOURS": "6"}):
            result = check_cooldown(tmp_path)

        assert result["run_mode"] == "cooldown_skip"
        assert "42" in result["cooldown_reason"]
        assert result["force_run"] is False

    def test_outside_cooldown_window_returns_full(self, tmp_path: Path) -> None:
        """Last run was > cooldown_hours ago → proceed normally."""
        from src.run_guard import check_cooldown

        (tmp_path / "last_fts_run.txt").write_text(
            (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(),
            encoding="utf-8",
        )
        (tmp_path / "last_fts_batch_count.txt").write_text("25", encoding="utf-8")

        with patch.dict(os.environ, {"TENDER_RUN_COOLDOWN_HOURS": "6"}):
            result = check_cooldown(tmp_path)

        assert result["run_mode"] == "full"

    def test_force_run_bypasses_cooldown(self, tmp_path: Path) -> None:
        """TENDER_FORCE_RUN=true always returns full, even within cooldown window."""
        from src.run_guard import check_cooldown

        (tmp_path / "last_fts_run.txt").write_text(
            (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
            encoding="utf-8",
        )
        (tmp_path / "last_fts_batch_count.txt").write_text("100", encoding="utf-8")

        with patch.dict(os.environ, {"TENDER_FORCE_RUN": "true", "TENDER_RUN_COOLDOWN_HOURS": "6"}):
            result = check_cooldown(tmp_path)

        assert result["run_mode"] == "full"
        assert result["force_run"] is True

    def test_force_run_true_variants(self, tmp_path: Path) -> None:
        """TENDER_FORCE_RUN accepts 1, true, yes."""
        from src.run_guard import check_cooldown

        (tmp_path / "last_fts_run.txt").write_text(
            (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            encoding="utf-8",
        )
        (tmp_path / "last_fts_batch_count.txt").write_text("10", encoding="utf-8")

        for value in ("1", "true", "yes", "True", "YES"):
            with patch.dict(os.environ, {"TENDER_FORCE_RUN": value}):
                result = check_cooldown(tmp_path)
            assert result["run_mode"] == "full", f"TENDER_FORCE_RUN={value!r} should bypass"

    def test_custom_cooldown_hours_env(self, tmp_path: Path) -> None:
        """TENDER_RUN_COOLDOWN_HOURS configures the window size."""
        from src.run_guard import check_cooldown

        # Last run 2h ago, batch count 50
        (tmp_path / "last_fts_run.txt").write_text(
            (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            encoding="utf-8",
        )
        (tmp_path / "last_fts_batch_count.txt").write_text("50", encoding="utf-8")

        # 1h cooldown → should NOT skip (2h > 1h)
        with patch.dict(os.environ, {"TENDER_RUN_COOLDOWN_HOURS": "1", "TENDER_FORCE_RUN": ""}):
            result_short = check_cooldown(tmp_path)

        # 12h cooldown → should skip (2h < 12h)
        with patch.dict(os.environ, {"TENDER_RUN_COOLDOWN_HOURS": "12", "TENDER_FORCE_RUN": ""}):
            result_long = check_cooldown(tmp_path)

        assert result_short["run_mode"] == "full"
        assert result_long["run_mode"] == "cooldown_skip"

    def test_save_fts_batch_count(self, tmp_path: Path) -> None:
        """save_fts_batch_count writes a readable integer file."""
        from src.run_guard import save_fts_batch_count

        save_fts_batch_count(tmp_path, 77)
        raw = (tmp_path / "last_fts_batch_count.txt").read_text(encoding="utf-8").strip()
        assert raw == "77"

    def test_cooldown_reason_contains_remaining_minutes(self, tmp_path: Path) -> None:
        """Cooldown reason includes remaining time so operators know when to next run."""
        from src.run_guard import check_cooldown

        (tmp_path / "last_fts_run.txt").write_text(
            (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            encoding="utf-8",
        )
        (tmp_path / "last_fts_batch_count.txt").write_text("30", encoding="utf-8")

        with patch.dict(os.environ, {"TENDER_RUN_COOLDOWN_HOURS": "6", "TENDER_FORCE_RUN": ""}):
            result = check_cooldown(tmp_path)

        assert result["run_mode"] == "cooldown_skip"
        assert "remaining" in result["cooldown_reason"].lower()


# ---------------------------------------------------------------------------
# T2 — CF release tag counting
# ---------------------------------------------------------------------------


class TestCFTagCounting:
    """Tests for CF release-tag visibility in src/ingest.py."""

    def test_fetch_contracts_finder_returns_tag_counts(self) -> None:
        """fetch_contracts_finder returns a dict with cf_release_tag_counts."""
        from src.ingest import fetch_contracts_finder

        mock_releases = [
            {"ocid": "ocds-1", "tag": ["tender"], "tender": {}, "parties": []},
            {"ocid": "ocds-2", "tag": ["tender"], "tender": {}, "parties": []},
            {"ocid": "ocds-3", "tag": ["award"], "tender": {}, "parties": []},
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"releases": mock_releases}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.ingest.requests.get", return_value=mock_resp):
            result = fetch_contracts_finder()

        assert isinstance(result, dict)
        assert "records" in result
        assert "cf_release_tag_counts" in result
        tag_counts = result["cf_release_tag_counts"]
        assert tag_counts.get("tender") == 2
        assert tag_counts.get("award") == 1

    def test_fetch_contracts_finder_records_include_source_prefix(self) -> None:
        """Each record has _source=contracts_finder."""
        from src.ingest import fetch_contracts_finder

        mock_releases = [{"ocid": "ocds-1", "tag": ["tender"], "tender": {}, "parties": []}]

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"releases": mock_releases}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.ingest.requests.get", return_value=mock_resp):
            result = fetch_contracts_finder()

        assert result["records"][0]["_source"] == "contracts_finder"

    def test_tag_counts_empty_when_no_tags(self) -> None:
        """Releases with no tags produce an empty tag count dict."""
        from src.ingest import fetch_contracts_finder

        mock_releases = [{"ocid": "ocds-1", "tag": [], "tender": {}, "parties": []}]

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"releases": mock_releases}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.ingest.requests.get", return_value=mock_resp):
            result = fetch_contracts_finder()

        assert result["cf_release_tag_counts"] == {}

    def test_ingest_run_returns_cf_release_tag_counts(self, tmp_path: Path) -> None:
        """ingest.run() propagates cf_release_tag_counts into its return dict."""
        from src.ingest import run as ingest_run

        run_dir = tmp_path / "runs" / "test-run"
        run_dir.mkdir(parents=True)

        mock_cf_result = {
            "records": [
                {"_source": "contracts_finder", "ocid": "ocds-1", "tag": ["tender"],
                 "tender": {"title": "Test Tender"}, "parties": []},
            ],
            "cf_release_tag_counts": {"tender": 1},
        }
        mock_fts_result = {"records": [], "metadata": {}}

        with patch("src.ingest.fetch_contracts_finder", return_value=mock_cf_result), \
             patch("src.ingest.fetch_find_a_tender", return_value=mock_fts_result):
            context = ingest_run({"run_dir": run_dir, "data_dir": tmp_path})

        assert "cf_release_tag_counts" in context
        assert context["cf_release_tag_counts"].get("tender") == 1


# ---------------------------------------------------------------------------
# T3 — Buyer intel 5-field attachment
# ---------------------------------------------------------------------------


class TestBuyerIntelAttachment:
    """Tests for buyer_intel dual-surface enrichment (5 fields per tender)."""

    def test_attach_briefs_injects_buyer_intel_summary(self, tmp_path: Path) -> None:
        """brief text from cache → buyer_intel_summary on tender."""
        from src.buyer_intel import attach_briefs

        state_dir = tmp_path / "state"
        run_dir = tmp_path / "run"
        state_dir.mkdir(parents=True)
        run_dir.mkdir(parents=True)

        (state_dir / "buyer_briefs.json").write_text(
            json.dumps({
                "environment agency": {
                    "buyer_name": "Environment Agency",
                    "brief": "Flood defence commissioning authority.",
                    "record_count": 5,
                    "synthesised_at": "2026-04-01T00:00:00+00:00",
                }
            }),
            encoding="utf-8",
        )

        deduped_file = run_dir / "new_tenders.json"
        deduped_file.write_text(
            json.dumps({"opportunities": [
                {"buyer_name": "Environment Agency", "title": "Flood works"}
            ]}),
            encoding="utf-8",
        )

        attach_briefs({"state_dir": state_dir, "deduped_file": deduped_file})
        payload = json.loads(deduped_file.read_text(encoding="utf-8"))
        opp = payload["opportunities"][0]

        assert opp["buyer_intel_summary"] == "Flood defence commissioning authority."

    def test_attach_briefs_injects_all_five_fields_when_history_available(self, tmp_path: Path) -> None:
        """When buyer history exists, all 5 enrichment fields are injected."""
        from src.buyer_intel import attach_briefs

        state_dir = tmp_path / "state"
        run_dir = tmp_path / "run"
        state_dir.mkdir(parents=True)
        run_dir.mkdir(parents=True)

        now = datetime.now(timezone.utc)
        history_rows = [
            {"buyer_name": "Test Council", "seen_at": (now - timedelta(days=90)).isoformat(),
             "cpv_codes": ["civils"], "value_amount": 300000},
            {"buyer_name": "Test Council", "seen_at": (now - timedelta(days=60)).isoformat(),
             "cpv_codes": ["civils"], "value_amount": 350000},
            {"buyer_name": "Test Council", "seen_at": (now - timedelta(days=30)).isoformat(),
             "cpv_codes": ["civils"], "value_amount": 400000},
        ]
        (state_dir / "buyer_history.jsonl").write_text(
            "\n".join(json.dumps(r) for r in history_rows) + "\n",
            encoding="utf-8",
        )
        (state_dir / "buyer_briefs.json").write_text(json.dumps({}), encoding="utf-8")

        deduped_file = run_dir / "new_tenders.json"
        deduped_file.write_text(
            json.dumps({"opportunities": [
                {"buyer_name": "Test Council", "title": "Roads contract"}
            ]}),
            encoding="utf-8",
        )

        result = attach_briefs({"state_dir": state_dir, "deduped_file": deduped_file})
        payload = json.loads(deduped_file.read_text(encoding="utf-8"))
        opp = payload["opportunities"][0]

        # History-derived fields always injected when records exist
        assert "buyer_pattern" in opp
        assert "buyer_activity_90d" in opp
        assert "buyer_avg_value" in opp
        assert "buyer_category_bias" in opp
        # buyer_intel_summary only injected when a brief exists in briefs_cache
        # (not present here since the cache is empty)

    def test_attach_briefs_activity_90d_count(self, tmp_path: Path) -> None:
        """buyer_activity_90d counts only records within last 90 days."""
        from src.buyer_intel import attach_briefs

        state_dir = tmp_path / "state"
        run_dir = tmp_path / "run"
        state_dir.mkdir(parents=True)
        run_dir.mkdir(parents=True)

        now = datetime.now(timezone.utc)
        history_rows = [
            {"buyer_name": "Buyer A", "seen_at": (now - timedelta(days=30)).isoformat(),
             "cpv_codes": [], "value_amount": 100000},
            {"buyer_name": "Buyer A", "seen_at": (now - timedelta(days=200)).isoformat(),
             "cpv_codes": [], "value_amount": 100000},  # older than 90d
        ]
        (state_dir / "buyer_history.jsonl").write_text(
            "\n".join(json.dumps(r) for r in history_rows) + "\n",
            encoding="utf-8",
        )
        (state_dir / "buyer_briefs.json").write_text(json.dumps({}), encoding="utf-8")

        deduped_file = run_dir / "new_tenders.json"
        deduped_file.write_text(
            json.dumps({"opportunities": [
                {"buyer_name": "Buyer A", "title": "Test"}
            ]}),
            encoding="utf-8",
        )

        attach_briefs({"state_dir": state_dir, "deduped_file": deduped_file})
        payload = json.loads(deduped_file.read_text(encoding="utf-8"))
        opp = payload["opportunities"][0]

        assert opp["buyer_activity_90d"] == 1

    def test_attach_briefs_returns_count(self, tmp_path: Path) -> None:
        """Return dict includes buyer_intel_briefs_attached count."""
        from src.buyer_intel import attach_briefs

        state_dir = tmp_path / "state"
        run_dir = tmp_path / "run"
        state_dir.mkdir(parents=True)
        run_dir.mkdir(parents=True)

        (state_dir / "buyer_briefs.json").write_text(json.dumps({}), encoding="utf-8")

        deduped_file = run_dir / "new_tenders.json"
        deduped_file.write_text(
            json.dumps({"opportunities": [
                {"buyer_name": "Some Council", "title": "Tender 1"},
                {"buyer_name": "Some Council", "title": "Tender 2"},
            ]}),
            encoding="utf-8",
        )

        result = attach_briefs({"state_dir": state_dir, "deduped_file": deduped_file})
        assert "buyer_intel_briefs_attached" in result
        assert isinstance(result["buyer_intel_briefs_attached"], int)

    def test_attach_briefs_no_deduped_file_returns_zero(self, tmp_path: Path) -> None:
        """Missing deduped_file → attach count 0, no crash."""
        from src.buyer_intel import attach_briefs

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "buyer_briefs.json").write_text(json.dumps({}), encoding="utf-8")

        result = attach_briefs({"state_dir": state_dir, "deduped_file": None})
        assert result.get("buyer_intel_briefs_attached", 0) == 0


# ---------------------------------------------------------------------------
# T4 — Timing visibility field
# ---------------------------------------------------------------------------


class TestTimingVisibility:
    """Tests for timing_visibility: full / limited / hidden rules."""

    def _make_history(self, count: int, gap_days: int) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "test buyer": [
                {
                    "buyer_name": "Test Buyer",
                    "seen_at": (now - timedelta(days=gap_days * i)).isoformat(),
                    "cpv_codes": ["civils"],
                }
                for i in range(1, count + 1)
            ]
        }

    def test_high_confidence_gives_full_visibility(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        # 6 very regular records → High confidence
        history = {
            "regular": [
                {"buyer_name": "Regular", "seen_at": (now - timedelta(days=14 * i)).isoformat(),
                 "cpv_codes": []}
                for i in range(1, 7)
            ]
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        assert rec["timing_confidence"] == "High"
        assert rec["timing_visibility"] == "full"

    def test_weak_confidence_gives_limited_visibility(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        # 2 records → Weak confidence
        history = {
            "weak": [
                {"buyer_name": "Weak", "seen_at": (now - timedelta(days=60)).isoformat(), "cpv_codes": []},
                {"buyer_name": "Weak", "seen_at": (now - timedelta(days=30)).isoformat(), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        assert rec["timing_confidence"] == "Weak"
        assert rec["timing_visibility"] == "limited"

    def test_none_confidence_gives_hidden_visibility(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        # 1 record → None confidence
        history = {
            "sparse": [
                {"buyer_name": "Sparse", "seen_at": (now - timedelta(days=100)).isoformat(), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        assert rec["timing_confidence"] == "None"
        assert rec["timing_visibility"] == "hidden"

    def test_medium_confidence_gives_full_visibility(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        # 4 moderately regular records → Medium confidence
        history = {
            "medium": [
                {"buyer_name": "Medium", "seen_at": (now - timedelta(days=95)).isoformat(), "cpv_codes": []},
                {"buyer_name": "Medium", "seen_at": (now - timedelta(days=65)).isoformat(), "cpv_codes": []},
                {"buyer_name": "Medium", "seen_at": (now - timedelta(days=38)).isoformat(), "cpv_codes": []},
                {"buyer_name": "Medium", "seen_at": (now - timedelta(days=10)).isoformat(), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        # Medium or High both get full visibility
        assert rec["timing_confidence"] in {"High", "Medium"}
        assert rec["timing_visibility"] == "full"

    def test_timing_visibility_field_always_present(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        history = {
            "a": [{"buyer_name": "A", "seen_at": (now - timedelta(days=30)).isoformat(), "cpv_codes": []}],
            "b": [
                {"buyer_name": "B", "seen_at": (now - timedelta(days=60)).isoformat(), "cpv_codes": []},
                {"buyer_name": "B", "seen_at": (now - timedelta(days=30)).isoformat(), "cpv_codes": []},
            ],
        }
        results = compute_buyer_timing(history, {}, now=now)
        for rec in results:
            assert "timing_visibility" in rec
            assert rec["timing_visibility"] in {"full", "limited", "hidden"}


# ---------------------------------------------------------------------------
# T5 — Timing label + marketing text
# ---------------------------------------------------------------------------


class TestTimingLabel:
    """Tests for timing_label and timing_marketing_text fields."""

    def _high_confidence_history(self) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "regular": [
                {"buyer_name": "Regular", "seen_at": (now - timedelta(days=14 * i)).isoformat(),
                 "cpv_codes": []}
                for i in range(1, 7)
            ]
        }

    def test_timing_label_always_present(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        history = {
            "sparse": [{"buyer_name": "Sparse", "seen_at": (now - timedelta(days=100)).isoformat(),
                        "cpv_codes": []}],
        }
        results = compute_buyer_timing(history, {}, now=now)
        for rec in results:
            assert "timing_label" in rec
            assert rec["timing_label"] in {"Actionable", "Watch", "Tracking"}

    def test_timing_marketing_text_always_present(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        history = {
            "sparse": [{"buyer_name": "Sparse", "seen_at": (now - timedelta(days=100)).isoformat(),
                        "cpv_codes": []}],
        }
        results = compute_buyer_timing(history, {}, now=now)
        for rec in results:
            assert "timing_marketing_text" in rec
            assert isinstance(rec["timing_marketing_text"], str)
            assert len(rec["timing_marketing_text"]) > 0

    def test_none_confidence_gives_tracking_label(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        history = {
            "sparse": [{"buyer_name": "Sparse", "seen_at": (now - timedelta(days=100)).isoformat(),
                        "cpv_codes": []}],
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        assert rec["timing_confidence"] == "None"
        assert rec["timing_label"] == "Tracking"

    def test_weak_confidence_gives_watch_label(self) -> None:
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        history = {
            "weak": [
                {"buyer_name": "Weak", "seen_at": (now - timedelta(days=60)).isoformat(), "cpv_codes": []},
                {"buyer_name": "Weak", "seen_at": (now - timedelta(days=30)).isoformat(), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        assert rec["timing_confidence"] == "Weak"
        assert rec["timing_label"] == "Watch"

    def test_due_soon_high_or_medium_confidence_gives_actionable_label(self) -> None:
        """Buyer whose predicted window is imminent → due_soon + Actionable label."""
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        # 3 records at ~30d gap, last seen 20 days ago → predicted central ~10d from now → due_soon
        history = {
            "imminent": [
                {"buyer_name": "Imminent", "seen_at": (now - timedelta(days=80)).isoformat(), "cpv_codes": []},
                {"buyer_name": "Imminent", "seen_at": (now - timedelta(days=50)).isoformat(), "cpv_codes": []},
                {"buyer_name": "Imminent", "seen_at": (now - timedelta(days=20)).isoformat(), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        assert rec["timing_status"] in {"due_soon", "overdue"}
        assert rec["timing_confidence"] in {"High", "Medium"}
        assert rec["timing_label"] == "Actionable"

    def test_high_confidence_upcoming_not_actionable(self) -> None:
        """High confidence but distant/upcoming window → Tracking, not Actionable."""
        from src.buyer_timing import compute_buyer_timing

        now = datetime.now(timezone.utc)
        # Very regular buyer last seen 2 days ago (next window is far off)
        history = {
            "fresh": [
                {"buyer_name": "Fresh", "seen_at": (now - timedelta(days=14 * i - 2)).isoformat(),
                 "cpv_codes": []}
                for i in range(1, 7)
            ]
        }
        results = compute_buyer_timing(history, {}, now=now)
        rec = results[0]
        if rec["timing_status"] in {"upcoming", "distant"}:
            assert rec["timing_label"] == "Tracking"


# ---------------------------------------------------------------------------
# T6 — Manifest new fields + status codes
# ---------------------------------------------------------------------------


class TestManifestFields:
    """Tests for apply_manifest_fields and new status codes."""

    def _make_base_manifest(self) -> dict:
        return {
            "run_id": "test-run-001",
            "status": "success",
            "steps": {},
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_duration_s": 1.5,
        }

    def test_apply_manifest_fields_includes_run_mode(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        context = {"run_mode": "full"}
        apply_manifest_fields(manifest, context, {})
        assert manifest["run_mode"] == "full"

    def test_apply_manifest_fields_includes_cooldown_skip_mode(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        context = {"run_mode": "cooldown_skip", "cooldown_reason": "Cooldown active."}
        apply_manifest_fields(manifest, context, {})
        assert manifest["run_mode"] == "cooldown_skip"

    def test_apply_manifest_fields_includes_cf_release_tag_counts(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        context = {"cf_release_tag_counts": {"tender": 85, "award": 5}}
        apply_manifest_fields(manifest, context, {})
        assert manifest["cf_release_tag_counts"] == {"tender": 85, "award": 5}

    def test_apply_manifest_fields_cf_tag_counts_defaults_empty(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        apply_manifest_fields(manifest, {}, {})
        assert manifest["cf_release_tag_counts"] == {}

    def test_apply_manifest_fields_includes_buyer_intel_count(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        context = {"buyer_intel_briefs_attached": 12}
        apply_manifest_fields(manifest, context, {})
        assert manifest["buyer_intel_attached_count"] == 12

    def test_apply_manifest_fields_includes_timing_visible_count(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        context = {"timing_visible_count": 8, "timing_actionable_count": 3}
        apply_manifest_fields(manifest, context, {})
        assert manifest["timing_visible_count"] == 8
        assert manifest["timing_actionable_count"] == 3

    def test_apply_manifest_fields_timing_counts_default_zero(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        apply_manifest_fields(manifest, {}, {})
        assert manifest["timing_visible_count"] == 0
        assert manifest["timing_actionable_count"] == 0

    def test_success_empty_status_when_shortlist_and_new_both_zero(self) -> None:
        """shortlist_count=0 + new_count=0 + no warnings → success_empty."""
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        manifest["status"] = "success_empty"  # as set by run_pipeline logic
        context = {"shortlist_count": 0, "new_count": 0}
        apply_manifest_fields(manifest, context, {})
        assert manifest["status"] == "success_empty"

    def test_manifest_run_mode_defaults_to_full(self) -> None:
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        apply_manifest_fields(manifest, {}, {})  # no run_mode in context
        assert manifest["run_mode"] == "full"

    def test_norm_filter_counts_in_manifest(self) -> None:
        """Manifest includes status/deadline/value filter counts from normalize."""
        from run_pipeline import apply_manifest_fields

        manifest = self._make_base_manifest()
        context = {
            "norm_status_filtered_count": 10,
            "norm_deadline_filtered_count": 5,
            "norm_value_filtered_count": 2,
            "value_filter_mode": "soft",
        }
        apply_manifest_fields(manifest, context, {})
        assert manifest["norm_status_filtered_count"] == 10
        assert manifest["norm_deadline_filtered_count"] == 5
        assert manifest["norm_value_filtered_count"] == 2
        assert manifest["value_filter_mode"] == "soft"
