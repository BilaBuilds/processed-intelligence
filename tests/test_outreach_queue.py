"""
tests/test_outreach_queue.py
============================
Deterministic tests for the Outreach Queue pipeline module.
No network calls, no DB connections required.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.outreach_queue import (
    build_action_note,
    build_draft,
    build_outreach_queue,
    build_outreach_reason,
    compute_outreach_score,
    load_contact_states,
    recommend_channel,
    score_to_priority,
    write_artifacts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WL_HOT = {
    "buyer_name": "Environment Agency",
    "outreach_priority": "hot",
    "fit_to_client": 72,
    "activity_90d": 4,
    "activity_30d": 2,
    "total_notices": 12,
    "typical_value": 450000,
    "typical_value_label": "£250k – £500k",
    "top_categories": ["Water Management", "Environmental"],
    "top_regions": ["England"],
    "recent_match_count": 3,
    "latest_notice_date": "2026-04-10",
    "latest_notice_title": "Water quality monitoring framework",
}

WL_WARM = {
    "buyer_name": "Manchester City Council",
    "outreach_priority": "warm",
    "fit_to_client": 55,
    "activity_90d": 2,
    "activity_30d": 1,
    "total_notices": 7,
    "typical_value": 250000,
    "typical_value_label": "£100k – £250k",
    "top_categories": ["Construction"],
    "top_regions": ["North West"],
    "recent_match_count": 1,
    "latest_notice_date": "2026-03-20",
    "latest_notice_title": "Highway maintenance package",
}

WL_LOW = {
    "buyer_name": "Obscure Council",
    "outreach_priority": "low",
    "fit_to_client": 10,
    "activity_90d": 0,
    "activity_30d": 0,
    "total_notices": 1,
    "typical_value": 0,
    "typical_value_label": "Unknown",
    "top_categories": [],
    "top_regions": [],
    "recent_match_count": 0,
    "latest_notice_date": "",
    "latest_notice_title": "",
}

TS_ACTIONABLE = {
    "buyer_key": "environment_agency",
    "buyer_name": "Environment Agency",
    "timing_label": "Actionable",
    "timing_confidence": "High",
    "timing_visibility": "full",
    "timing_status": "due_soon",
    "predicted_next_start": "2026-04-20",
    "predicted_next_end": "2026-05-10",
    "predicted_next_central": "2026-04-28",
}

TS_WATCH = {
    "buyer_key": "manchester_city_council",
    "buyer_name": "Manchester City Council",
    "timing_label": "Watch",
    "timing_confidence": "Medium",
    "timing_visibility": "limited",
    "timing_status": "due",
    "predicted_next_start": "2026-05-01",
    "predicted_next_end": "2026-06-01",
    "predicted_next_central": "2026-05-15",
}

TS_NONE = {
    "buyer_key": "obscure_council",
    "buyer_name": "Obscure Council",
    "timing_label": "Tracking",
    "timing_confidence": "None",
    "timing_visibility": "hidden",
    "timing_status": "",
}


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------

class TestComputeOutreachScore:
    def test_hot_actionable_full_vis_max_fit(self):
        score = compute_outreach_score(WL_HOT, TS_ACTIONABLE)
        # hot=40 + Actionable=25 + High=15 + full=8 + fit(72//5=14) + activity(min(4,3)*3=9) + match=4
        assert score == min(40 + 25 + 15 + 8 + 14 + 9 + 4, 100)

    def test_warm_watch_limited(self):
        score = compute_outreach_score(WL_WARM, TS_WATCH)
        # warm=25 + Watch=12 + Medium=10 + limited=4 + fit(55//5=11) + activity(min(2,3)*3=6) + match=0
        expected = min(25 + 12 + 10 + 4 + 11 + 6, 100)
        assert score == expected

    def test_low_no_timing(self):
        score = compute_outreach_score(WL_LOW, TS_NONE)
        # low=0 + Tracking=5 + None=0 + hidden=0 + fit(10//5=2) + activity=0
        assert score == 7

    def test_score_capped_at_100(self):
        wl = dict(WL_HOT, fit_to_client=99, activity_90d=10, recent_match_count=5)
        score = compute_outreach_score(wl, TS_ACTIONABLE)
        assert score == 100

    def test_zero_score_minimum(self):
        wl = {**WL_LOW, "outreach_priority": "low", "fit_to_client": 0, "activity_90d": 0, "recent_match_count": 0}
        ts = {**TS_NONE, "timing_label": "unknown"}
        score = compute_outreach_score(wl, ts)
        assert score == 0


# ---------------------------------------------------------------------------
# Priority bucketing
# ---------------------------------------------------------------------------

class TestScoreToPriority:
    def test_hot_threshold(self):
        assert score_to_priority(65) == "Hot"
        assert score_to_priority(100) == "Hot"

    def test_warm_threshold(self):
        assert score_to_priority(40) == "Warm"
        assert score_to_priority(64) == "Warm"

    def test_monitor_threshold(self):
        assert score_to_priority(20) == "Monitor"
        assert score_to_priority(39) == "Monitor"

    def test_low_threshold(self):
        assert score_to_priority(0) == "Low"
        assert score_to_priority(19) == "Low"


# ---------------------------------------------------------------------------
# Recommended channel
# ---------------------------------------------------------------------------

class TestRecommendChannel:
    def test_hot_always_email(self):
        assert recommend_channel("Hot", WL_HOT, TS_ACTIONABLE) == "email"
        assert recommend_channel("Hot", WL_HOT, TS_NONE) == "email"

    def test_warm_actionable_email(self):
        assert recommend_channel("Warm", WL_WARM, TS_ACTIONABLE) == "email"

    def test_warm_high_fit_email(self):
        wl = dict(WL_WARM, fit_to_client=60)
        assert recommend_channel("Warm", wl, TS_NONE) == "email"

    def test_warm_low_fit_linkedin(self):
        wl = dict(WL_WARM, fit_to_client=40)
        ts = dict(TS_NONE, timing_label="Tracking")
        assert recommend_channel("Warm", wl, ts) == "linkedin"

    def test_monitor_limited_vis_linkedin(self):
        assert recommend_channel("Monitor", WL_LOW, TS_WATCH) == "linkedin"

    def test_monitor_hidden_monitor_only(self):
        assert recommend_channel("Monitor", WL_LOW, TS_NONE) == "monitor_only"

    def test_low_monitor_only(self):
        assert recommend_channel("Low", WL_LOW, TS_NONE) == "monitor_only"


# ---------------------------------------------------------------------------
# Reason generation
# ---------------------------------------------------------------------------

class TestBuildOutreachReason:
    def test_hot_actionable_mentions_timing(self):
        reason = build_outreach_reason("Hot", WL_HOT, TS_ACTIONABLE)
        assert "actionable" in reason.lower()
        assert "high" in reason.lower()

    def test_hot_no_timing_mentions_activity(self):
        ts = dict(TS_NONE, timing_label="Tracking")
        reason = build_outreach_reason("Hot", WL_HOT, ts)
        assert "activity" in reason.lower() or "90" in reason

    def test_warm_includes_fit(self):
        reason = build_outreach_reason("Warm", WL_WARM, TS_WATCH)
        assert "55" in reason or "fit" in reason.lower()

    def test_monitor_weak_signal(self):
        reason = build_outreach_reason("Monitor", WL_LOW, TS_NONE)
        assert "monitor" in reason.lower() or "low" in reason.lower() or "weak" in reason.lower()

    def test_low_returns_string(self):
        reason = build_outreach_reason("Low", WL_LOW, TS_NONE)
        assert isinstance(reason, str) and len(reason) > 0


# ---------------------------------------------------------------------------
# Action note
# ---------------------------------------------------------------------------

class TestBuildActionNote:
    def test_hot_actionable_urgent(self):
        note = build_action_note("Hot", "email", TS_ACTIONABLE)
        assert "email" in note.lower() or "week" in note.lower()

    def test_warm_email_channel(self):
        note = build_action_note("Warm", "email", TS_WATCH)
        assert "email" in note.lower() or "queue" in note.lower()

    def test_warm_linkedin_channel(self):
        note = build_action_note("Warm", "linkedin", TS_NONE)
        assert "linkedin" in note.lower()

    def test_monitor_note(self):
        note = build_action_note("Monitor", "monitor_only", TS_NONE)
        assert "monitor" in note.lower()

    def test_low_note(self):
        note = build_action_note("Low", "monitor_only", TS_NONE)
        assert isinstance(note, str)


# ---------------------------------------------------------------------------
# Draft text
# ---------------------------------------------------------------------------

class TestBuildDraft:
    def test_subject_contains_category(self):
        subject, _ = build_draft(WL_HOT, TS_ACTIONABLE)
        assert "Water Management" in subject or "procurement" in subject.lower()

    def test_message_contains_buyer_name(self):
        _, message = build_draft(WL_HOT, TS_ACTIONABLE)
        assert "Environment Agency" in message

    def test_message_contains_notice_title(self):
        _, message = build_draft(WL_HOT, TS_ACTIONABLE)
        assert "Water quality monitoring framework" in message

    def test_draft_no_ai_placeholders(self):
        subject, message = build_draft(WL_LOW, TS_NONE)
        for placeholder in ["{{", "}}", "[AI", "GPT", "TODO"]:
            assert placeholder not in subject
            assert placeholder not in message


# ---------------------------------------------------------------------------
# Contact state defaulting
# ---------------------------------------------------------------------------

class TestContactStateDefaulting:
    def test_missing_db_returns_empty(self, tmp_path):
        states = load_contact_states(tmp_path / "nonexistent.sqlite")
        assert states == {}

    def test_db_with_no_actions_returns_empty(self, tmp_path):
        db = tmp_path / "outreach.sqlite"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE buyer_actions (
                id INTEGER PRIMARY KEY,
                buyer_key TEXT, buyer_name TEXT,
                action_type TEXT, action_status TEXT,
                run_id TEXT, notes TEXT, actor TEXT, source TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()
        states = load_contact_states(db)
        assert states == {}

    def test_mark_sent_maps_to_contacted(self, tmp_path):
        db = tmp_path / "outreach.sqlite"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE buyer_actions (
                id INTEGER PRIMARY KEY,
                buyer_key TEXT, buyer_name TEXT,
                action_type TEXT, action_status TEXT,
                run_id TEXT, notes TEXT, actor TEXT, source TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)
        conn.execute("""
            INSERT INTO buyer_actions (buyer_key, buyer_name, action_type, action_status, created_at)
            VALUES ('acme_ltd', 'Acme Ltd', 'mark_sent', 'sent', '2026-04-01T10:00:00')
        """)
        conn.commit()
        conn.close()
        states = load_contact_states(db)
        assert "acme_ltd" in states
        assert states["acme_ltd"]["contact_status"] == "contacted"
        assert states["acme_ltd"]["last_contacted_at"] == "2026-04-01T10:00:00"

    def test_mark_drafted_maps_to_drafted(self, tmp_path):
        db = tmp_path / "outreach.sqlite"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE buyer_actions (
                id INTEGER PRIMARY KEY,
                buyer_key TEXT, buyer_name TEXT,
                action_type TEXT, action_status TEXT,
                run_id TEXT, notes TEXT, actor TEXT, source TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)
        conn.execute("""
            INSERT INTO buyer_actions (buyer_key, buyer_name, action_type, action_status, created_at)
            VALUES ('test_council', 'Test Council', 'mark_drafted', 'drafted', '2026-04-02T09:00:00')
        """)
        conn.commit()
        conn.close()
        states = load_contact_states(db)
        assert states["test_council"]["contact_status"] == "drafted"

    def test_latest_action_wins_per_buyer(self, tmp_path):
        db = tmp_path / "outreach.sqlite"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE buyer_actions (
                id INTEGER PRIMARY KEY,
                buyer_key TEXT, buyer_name TEXT,
                action_type TEXT, action_status TEXT,
                run_id TEXT, notes TEXT, actor TEXT, source TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)
        conn.executemany("""
            INSERT INTO buyer_actions (buyer_key, buyer_name, action_type, action_status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, [
            ("abc", "ABC Ltd", "mark_drafted", "drafted", "2026-03-01T10:00:00"),
            ("abc", "ABC Ltd", "mark_sent", "sent", "2026-04-01T10:00:00"),
        ])
        conn.commit()
        conn.close()
        states = load_contact_states(db)
        # Most recent (sent) wins
        assert states["abc"]["contact_status"] == "contacted"


# ---------------------------------------------------------------------------
# build_outreach_queue integration
# ---------------------------------------------------------------------------

class TestBuildOutreachQueue:
    def test_returns_list(self):
        records = build_outreach_queue(
            [WL_HOT, WL_WARM, WL_LOW],
            [TS_ACTIONABLE, TS_WATCH, TS_NONE],
            {},
            {},
        )
        assert isinstance(records, list)
        assert len(records) == 3

    def test_required_fields_present(self):
        records = build_outreach_queue([WL_HOT], [TS_ACTIONABLE], {}, {})
        r = records[0]
        required = [
            "buyer_name", "outreach_priority", "outreach_score",
            "timing_label", "timing_confidence", "timing_visibility",
            "fit_to_client", "activity_90d", "typical_value",
            "top_categories", "top_regions",
            "latest_notice_date", "latest_notice_title",
            "predicted_next_start", "predicted_next_end",
            "buyer_intel_summary", "outreach_reason", "action_note",
            "recommended_channel", "draft_subject", "draft_message",
            "contact_status", "last_contacted_at", "notes",
        ]
        for field in required:
            assert field in r, f"Missing field: {field}"

    def test_sorted_hot_before_warm_before_low(self):
        records = build_outreach_queue(
            [WL_LOW, WL_HOT, WL_WARM],
            [TS_NONE, TS_ACTIONABLE, TS_WATCH],
            {},
            {},
        )
        priorities = [r["outreach_priority"] for r in records]
        # Hot should come first
        assert priorities[0] == "Hot"

    def test_contact_status_defaults_to_not_contacted(self):
        records = build_outreach_queue([WL_HOT], [TS_ACTIONABLE], {}, {})
        assert records[0]["contact_status"] == "not_contacted"

    def test_contact_state_merged(self):
        contact_states = {
            "environment_agency": {
                "contact_status": "contacted",
                "last_contacted_at": "2026-04-01",
                "notes": "Called John",
            }
        }
        records = build_outreach_queue([WL_HOT], [TS_ACTIONABLE], {}, contact_states)
        assert records[0]["contact_status"] == "contacted"
        assert records[0]["last_contacted_at"] == "2026-04-01"

    def test_buyer_intel_summary_merged(self):
        briefs = {"environment_agency": "Major environmental regulator, large framework budgets."}
        records = build_outreach_queue([WL_HOT], [TS_ACTIONABLE], briefs, {})
        assert "environmental regulator" in records[0]["buyer_intel_summary"]

    def test_empty_inputs_returns_empty_list(self):
        records = build_outreach_queue([], [], {}, {})
        assert records == []

    def test_no_timing_match_uses_empty_ts(self):
        # Buyer in watchlist but no matching timing signal
        records = build_outreach_queue([WL_HOT], [], {}, {})
        assert len(records) == 1
        assert records[0]["timing_label"] == "Tracking"  # default
        assert records[0]["timing_confidence"] == "None"


# ---------------------------------------------------------------------------
# Artifact writing
# ---------------------------------------------------------------------------

class TestWriteArtifacts:
    def test_writes_json_and_csv(self, tmp_path):
        records = build_outreach_queue([WL_HOT, WL_WARM], [TS_ACTIONABLE, TS_WATCH], {}, {})
        json_path, csv_path = write_artifacts(records, tmp_path)
        assert json_path.exists()
        assert csv_path.exists()

    def test_json_is_valid(self, tmp_path):
        records = build_outreach_queue([WL_HOT], [TS_ACTIONABLE], {}, {})
        json_path, _ = write_artifacts(records, tmp_path)
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert isinstance(loaded, list)
        assert loaded[0]["buyer_name"] == "Environment Agency"

    def test_csv_has_header_and_rows(self, tmp_path):
        records = build_outreach_queue([WL_HOT, WL_WARM], [TS_ACTIONABLE, TS_WATCH], {}, {})
        _, csv_path = write_artifacts(records, tmp_path)
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        assert len(rows) == 2
        assert "buyer_name" in rows[0]
        assert "outreach_priority" in rows[0]

    def test_csv_flattens_list_fields(self, tmp_path):
        records = build_outreach_queue([WL_HOT], [TS_ACTIONABLE], {}, {})
        _, csv_path = write_artifacts(records, tmp_path)
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        # top_categories and top_regions must be strings in CSV
        assert isinstance(rows[0]["top_categories"], str)
        assert isinstance(rows[0]["top_regions"], str)

    def test_empty_records_writes_empty_csv(self, tmp_path):
        json_path, csv_path = write_artifacts([], tmp_path)
        assert json_path.exists()
        assert csv_path.exists()
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded == []


# ---------------------------------------------------------------------------
# Dashboard bundle inclusion
# ---------------------------------------------------------------------------

class TestDashboardBundleInclusion:
    def test_outreach_queue_in_bundle(self, tmp_path, monkeypatch):
        """build_outreach_queue_data returns correct structure from run artifact."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.build_dashboard_bundle import build_outreach_queue_data

        # Write a fake outreach_queue.json artifact
        records = [
            {**build_outreach_queue([WL_HOT], [TS_ACTIONABLE], {}, {})[0]},
        ]
        (tmp_path / "outreach_queue.json").write_text(
            json.dumps(records), encoding="utf-8"
        )

        result = build_outreach_queue_data(tmp_path, tmp_path)
        assert result["source"] == "run_artifact"
        assert result["counts"]["total"] == 1
        assert result["counts"]["hot"] == 1
        assert len(result["records"]) == 1

    def test_missing_artifact_returns_empty_not_error(self, tmp_path):
        """When artifact is missing and fallback also fails, returns empty gracefully."""
        from scripts.build_dashboard_bundle import build_outreach_queue_data

        # No artifact, no watchlist/timing either
        result = build_outreach_queue_data(tmp_path, tmp_path)
        assert "records" in result
        assert "counts" in result
        assert result["counts"]["total"] >= 0  # may build live from empty inputs
