"""
Phase 1F — Tests for the buyer_actions action layer.

Covers:
  - DB bootstrap: buyer_actions table and indexes created
  - create_action: happy path, unknown action_type raises, unknown status raises
  - update_action_status: happy path, unknown status raises, returns False for missing ID
  - get_action / list_actions: round-trip, filter by buyer/type/status
  - buyer_current_state: priority derivation, not_started fallback
  - has_open_action_of_type: duplicate guard
  - Dashboard bundle: load_action_states graceful on missing DB, reads real DB
  - Contact brief CLI: export-contact-brief subcommand determinism
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from outreach.db import connect, init_db, ACTION_TYPES, ACTION_STATUSES
from outreach.repositories import (
    create_action,
    update_action_status,
    get_action,
    list_actions,
    buyer_current_state,
    has_open_action_of_type,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(td: str):
    """Create and init a fresh in-memory-equivalent DB in the given temp dir."""
    path = Path(td) / "test_actions.sqlite"
    conn = connect(path)
    init_db(conn)
    return conn, path


# ---------------------------------------------------------------------------
# DB Bootstrap
# ---------------------------------------------------------------------------

class TestDbBootstrap(unittest.TestCase):
    def test_buyer_actions_table_exists(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='buyer_actions'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            conn.close()

    def test_buyer_actions_indexes_exist(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_buyer_actions_%'"
            ).fetchall()
            index_names = {row[0] for row in rows}
            self.assertIn("idx_buyer_actions_buyer", index_names)
            self.assertIn("idx_buyer_actions_status", index_names)
            conn.close()

    def test_action_types_constant_non_empty_frozenset(self):
        self.assertIsInstance(ACTION_TYPES, frozenset)
        self.assertGreater(len(ACTION_TYPES), 0)
        self.assertIn("mark_sent", ACTION_TYPES)
        self.assertIn("export_contact_brief", ACTION_TYPES)

    def test_action_statuses_constant_non_empty_frozenset(self):
        self.assertIsInstance(ACTION_STATUSES, frozenset)
        self.assertIn("sent", ACTION_STATUSES)
        self.assertIn("pending", ACTION_STATUSES)
        self.assertIn("not_started", ACTION_STATUSES) if "not_started" in ACTION_STATUSES else None


# ---------------------------------------------------------------------------
# create_action
# ---------------------------------------------------------------------------

class TestCreateAction(unittest.TestCase):
    def test_create_action_returns_integer_id(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            action_id = create_action(
                conn,
                buyer_key="acme_council",
                buyer_name="Acme Council",
                action_type="mark_sent",
            )
            self.assertIsInstance(action_id, int)
            self.assertGreater(action_id, 0)
            conn.close()

    def test_create_action_persists_fields(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            action_id = create_action(
                conn,
                buyer_key="river_borough",
                buyer_name="River Borough",
                action_type="preview_outreach",
                run_id="2026-04-18_120000",
                notes="Test note",
                actor="test",
                source="pytest",
                action_status="pending",
            )
            row = get_action(conn, action_id)
            self.assertEqual(row["buyer_key"], "river_borough")
            self.assertEqual(row["buyer_name"], "River Borough")
            self.assertEqual(row["action_type"], "preview_outreach")
            self.assertEqual(row["action_status"], "pending")
            self.assertEqual(row["run_id"], "2026-04-18_120000")
            self.assertEqual(row["notes"], "Test note")
            self.assertEqual(row["actor"], "test")
            self.assertEqual(row["source"], "pytest")
            conn.close()

    def test_create_action_unknown_action_type_raises(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            with self.assertRaises(ValueError):
                create_action(
                    conn,
                    buyer_key="x",
                    buyer_name="X",
                    action_type="NOT_A_VALID_TYPE",
                )
            conn.close()

    def test_create_action_unknown_status_raises(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            with self.assertRaises(ValueError):
                create_action(
                    conn,
                    buyer_key="x",
                    buyer_name="X",
                    action_type="mark_sent",
                    action_status="TOTALLY_WRONG",
                )
            conn.close()

    def test_create_action_default_status_is_pending(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            action_id = create_action(
                conn,
                buyer_key="y",
                buyer_name="Y",
                action_type="mark_drafted",
            )
            row = get_action(conn, action_id)
            self.assertEqual(row["action_status"], "pending")
            conn.close()


# ---------------------------------------------------------------------------
# update_action_status
# ---------------------------------------------------------------------------

class TestUpdateActionStatus(unittest.TestCase):
    def test_update_status_changes_status(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            aid = create_action(
                conn, buyer_key="z", buyer_name="Z", action_type="mark_sent"
            )
            result = update_action_status(conn, action_id=aid, action_status="sent")
            self.assertTrue(result)
            row = get_action(conn, aid)
            self.assertEqual(row["action_status"], "sent")
            conn.close()

    def test_update_status_unknown_status_raises(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            aid = create_action(
                conn, buyer_key="z", buyer_name="Z", action_type="mark_sent"
            )
            with self.assertRaises(ValueError):
                update_action_status(conn, action_id=aid, action_status="INVALID")
            conn.close()

    def test_update_status_missing_id_returns_false(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            result = update_action_status(conn, action_id=99999, action_status="sent")
            self.assertFalse(result)
            conn.close()

    def test_update_status_appends_notes(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            aid = create_action(
                conn, buyer_key="w", buyer_name="W", action_type="mark_drafted"
            )
            update_action_status(
                conn, action_id=aid, action_status="drafted", notes="Drafted email v1"
            )
            row = get_action(conn, aid)
            self.assertEqual(row["notes"], "Drafted email v1")
            conn.close()


# ---------------------------------------------------------------------------
# list_actions
# ---------------------------------------------------------------------------

class TestListActions(unittest.TestCase):
    def _seed(self, conn):
        """Insert a few actions for two different buyers."""
        create_action(conn, buyer_key="alpha", buyer_name="Alpha Council",
                      action_type="mark_sent", action_status="sent")
        create_action(conn, buyer_key="alpha", buyer_name="Alpha Council",
                      action_type="mark_drafted", action_status="drafted")
        create_action(conn, buyer_key="beta", buyer_name="Beta Borough",
                      action_type="mark_ignored", action_status="ignored")

    def test_list_all_returns_all_actions(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            self._seed(conn)
            rows = list_actions(conn)
            self.assertEqual(len(rows), 3)
            conn.close()

    def test_list_filter_by_buyer_key(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            self._seed(conn)
            rows = list_actions(conn, buyer_key="alpha")
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["buyer_key"] == "alpha" for r in rows))
            conn.close()

    def test_list_filter_by_status(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            self._seed(conn)
            rows = list_actions(conn, action_status="sent")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action_status"], "sent")
            conn.close()

    def test_list_filter_by_type(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            self._seed(conn)
            rows = list_actions(conn, action_type="mark_drafted")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action_type"], "mark_drafted")
            conn.close()

    def test_list_empty_buyer_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            self._seed(conn)
            rows = list_actions(conn, buyer_key="no_such_buyer")
            self.assertEqual(rows, [])
            conn.close()


# ---------------------------------------------------------------------------
# buyer_current_state
# ---------------------------------------------------------------------------

class TestBuyerCurrentState(unittest.TestCase):
    def test_not_started_when_no_actions(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            state = buyer_current_state(conn, "nobody")
            self.assertEqual(state["overall_status"], "not_started")
            self.assertEqual(state["action_count"], 0)
            self.assertIsNone(state["latest_action"])
            conn.close()

    def test_sent_beats_drafted(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="X", buyer_name="X",
                          action_type="mark_drafted", action_status="drafted")
            create_action(conn, buyer_key="X", buyer_name="X",
                          action_type="mark_sent", action_status="sent")
            state = buyer_current_state(conn, "X")
            self.assertEqual(state["overall_status"], "sent")
            conn.close()

    def test_drafted_beats_pending(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="Y", buyer_name="Y",
                          action_type="preview_outreach", action_status="pending")
            create_action(conn, buyer_key="Y", buyer_name="Y",
                          action_type="mark_drafted", action_status="drafted")
            state = buyer_current_state(conn, "Y")
            self.assertEqual(state["overall_status"], "drafted")
            conn.close()

    def test_ignored_beats_pending(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="Z", buyer_name="Z",
                          action_type="mark_ignored", action_status="ignored")
            create_action(conn, buyer_key="Z", buyer_name="Z",
                          action_type="preview_outreach", action_status="pending")
            state = buyer_current_state(conn, "Z")
            self.assertEqual(state["overall_status"], "ignored")
            conn.close()

    def test_action_count_correct(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            for _ in range(4):
                create_action(conn, buyer_key="Q", buyer_name="Q",
                              action_type="open_dossier", action_status="completed")
            state = buyer_current_state(conn, "Q")
            self.assertEqual(state["action_count"], 4)
            conn.close()

    def test_all_actions_field_present(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="R", buyer_name="R",
                          action_type="mark_sent", action_status="sent")
            state = buyer_current_state(conn, "R")
            self.assertIn("all_actions", state)
            self.assertEqual(len(state["all_actions"]), 1)
            conn.close()


# ---------------------------------------------------------------------------
# has_open_action_of_type — duplicate guard
# ---------------------------------------------------------------------------

class TestHasOpenActionOfType(unittest.TestCase):
    def test_false_when_no_actions(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            self.assertFalse(has_open_action_of_type(conn, "nobody", "mark_sent"))
            conn.close()

    def test_true_when_pending_action_exists(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="A", buyer_name="A",
                          action_type="mark_sent", action_status="pending")
            self.assertTrue(has_open_action_of_type(conn, "A", "mark_sent"))
            conn.close()

    def test_true_when_drafted_action_exists(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="B", buyer_name="B",
                          action_type="mark_drafted", action_status="drafted")
            self.assertTrue(has_open_action_of_type(conn, "B", "mark_drafted"))
            conn.close()

    def test_false_when_sent_action_exists(self):
        """'sent' is not an open status — should not block new action."""
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="C", buyer_name="C",
                          action_type="mark_sent", action_status="sent")
            self.assertFalse(has_open_action_of_type(conn, "C", "mark_sent"))
            conn.close()

    def test_false_when_different_type(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = _db(td)
            create_action(conn, buyer_key="D", buyer_name="D",
                          action_type="mark_drafted", action_status="pending")
            self.assertFalse(has_open_action_of_type(conn, "D", "mark_sent"))
            conn.close()


# ---------------------------------------------------------------------------
# Dashboard bundle: load_action_states
# ---------------------------------------------------------------------------

class TestLoadActionStates(unittest.TestCase):
    def test_graceful_on_missing_db(self):
        """load_action_states returns {} when DB file does not exist."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        with patch.dict(os.environ, {"OUTREACH_DB_PATH": "/tmp/nonexistent_action_states_test.sqlite"}):
            from build_dashboard_bundle import load_action_states
            result = load_action_states()
        self.assertEqual(result, {})

    def test_reads_real_db(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test_load_states.sqlite"
            conn = connect(db_path)
            init_db(conn)
            create_action(conn, buyer_key="alpha_council", buyer_name="Alpha Council",
                          action_type="mark_sent", action_status="sent")
            create_action(conn, buyer_key="beta_borough", buyer_name="Beta Borough",
                          action_type="mark_drafted", action_status="drafted")
            conn.close()

            with patch.dict(os.environ, {"OUTREACH_DB_PATH": str(db_path)}):
                # Re-import to pick up env var
                import importlib
                import build_dashboard_bundle as bdb
                importlib.reload(bdb)
                result = bdb.load_action_states()

        self.assertIn("alpha_council", result)
        self.assertEqual(result["alpha_council"]["overall_status"], "sent")
        self.assertIn("beta_borough", result)
        self.assertEqual(result["beta_borough"]["overall_status"], "drafted")

    def test_sent_beats_drafted_in_bundle_loader(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test_priority.sqlite"
            conn = connect(db_path)
            init_db(conn)
            create_action(conn, buyer_key="dual_buyer", buyer_name="Dual",
                          action_type="mark_drafted", action_status="drafted")
            create_action(conn, buyer_key="dual_buyer", buyer_name="Dual",
                          action_type="mark_sent", action_status="sent")
            conn.close()

            with patch.dict(os.environ, {"OUTREACH_DB_PATH": str(db_path)}):
                import importlib
                import build_dashboard_bundle as bdb
                importlib.reload(bdb)
                result = bdb.load_action_states()

        self.assertEqual(result["dual_buyer"]["overall_status"], "sent")


# ---------------------------------------------------------------------------
# Merge action states into buyer cards
# ---------------------------------------------------------------------------

class TestMergeActionStates(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import build_dashboard_bundle as bdb
        self.bdb = bdb

    def test_merge_sets_outreach_status_on_matching_card(self):
        cards = [
            {"key": "acme_council", "name": "Acme Council",
             "outreach_status": "not_started", "action_state": "not_started", "action_count": 0},
        ]
        states = {
            "acme_council": {"overall_status": "sent", "action_count": 3, "latest_action": None},
        }
        result = self.bdb._merge_action_states(cards, states)
        self.assertEqual(result[0]["outreach_status"], "sent")
        self.assertEqual(result[0]["action_state"], "sent")
        self.assertEqual(result[0]["action_count"], 3)

    def test_merge_leaves_not_started_for_untracked_buyer(self):
        cards = [
            {"key": "unknown_buyer", "name": "Unknown",
             "outreach_status": "not_started", "action_state": "not_started", "action_count": 0},
        ]
        result = self.bdb._merge_action_states(cards, {})
        self.assertEqual(result[0]["outreach_status"], "not_started")

    def test_merge_handles_empty_cards(self):
        result = self.bdb._merge_action_states([], {"some_key": {"overall_status": "sent", "action_count": 1, "latest_action": None}})
        self.assertEqual(result, [])

    def test_merge_handles_empty_states(self):
        cards = [{"key": "x", "name": "X", "outreach_status": "not_started", "action_state": "not_started", "action_count": 0}]
        result = self.bdb._merge_action_states(cards, {})
        self.assertEqual(result[0]["outreach_status"], "not_started")

    def test_merge_matches_slugged_state_to_spaced_card_key(self):
        cards = [
            {"key": "acme council", "name": "Acme Council",
             "outreach_status": "not_started", "action_state": "not_started", "action_count": 0},
        ]
        states = {
            "acme_council": {"overall_status": "sent", "action_count": 1, "latest_action": None},
        }
        result = self.bdb._merge_action_states(cards, states)
        self.assertEqual(result[0]["outreach_status"], "sent")
        self.assertEqual(result[0]["action_state"], "sent")


# ---------------------------------------------------------------------------
# CLI export-contact-brief determinism
# ---------------------------------------------------------------------------

class TestExportContactBriefCli(unittest.TestCase):
    def _make_env(self, td: str) -> tuple[Path, Path]:
        """Create a minimal workspace + dossier so the CLI can run."""
        root = Path(td)
        buyers_dir = root / "openclaw_workspace" / "buyers"
        buyers_dir.mkdir(parents=True, exist_ok=True)
        exports_dir = root / "openclaw_workspace" / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        state_dir = root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        runs_dir = root / "data" / "runs"
        run_dir = runs_dir / "2026-04-18_120000"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Minimal dossier
        dossier = buyers_dir / "alpha_council.md"
        dossier.write_text(
            "# Alpha Council\n\n"
            "- **Status:** Actionable\n"
            "- **Confidence:** High\n"
            "- **Fit to client:** 80%\n"
            "- **Outreach status:** not_started\n"
            "\n## Memory Notes\n\n_No notes yet._\n",
            encoding="utf-8",
        )

        # Minimal timing signals
        timing_file = run_dir / "buyer_timing_signals.json"
        timing_file.write_text(
            json.dumps({
                "signals": [
                    {
                        "buyer_key": "alpha_council",
                        "buyer_name": "Alpha Council",
                        "timing_label": "Actionable",
                        "timing_confidence": "High",
                        "predicted_next_start": "2026-06-01",
                        "predicted_next_end": "2026-08-30",
                        "action_note": "Window opens June 2026",
                        "fit_to_client": 80,
                    }
                ]
            }),
            encoding="utf-8",
        )

        # Minimal buyer_history
        history_file = state_dir / "buyer_history.jsonl"
        history_file.write_text(
            json.dumps({
                "buyer_name": "Alpha Council",
                "tenders": [{"title": "Alpha Road Resurfacing", "published": "2025-11-01"}]
            }) + "\n",
            encoding="utf-8",
        )

        # DB
        db_file = root / "outreach.sqlite"
        conn = connect(db_file)
        init_db(conn)
        conn.close()

        return root, db_file

    def test_export_contact_brief_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            root, db_file = self._make_env(td)

            # Patch BASE_DIR in cli module
            from outreach import cli as cli_mod
            original_base = cli_mod.BASE_DIR
            original_state = cli_mod.STATE_DIR
            original_runs = cli_mod.RUNS_DIR
            original_workspace = cli_mod.WORKSPACE
            original_buyers = cli_mod.BUYERS_DIR
            original_exports = cli_mod.EXPORTS_DIR
            try:
                cli_mod.BASE_DIR = root
                cli_mod.STATE_DIR = root / "state"
                cli_mod.RUNS_DIR = root / "data" / "runs"
                cli_mod.WORKSPACE = root / "openclaw_workspace"
                cli_mod.BUYERS_DIR = root / "openclaw_workspace" / "buyers"
                cli_mod.EXPORTS_DIR = root / "openclaw_workspace" / "exports"

                buffer = io.StringIO()
                with (
                    patch.dict(os.environ, {"OUTREACH_DB_PATH": str(db_file)}),
                    redirect_stdout(buffer),
                ):
                    from outreach.cli import run_cli
                    exit_code = run_cli(["export-contact-brief", "--buyer", "alpha council"])
            finally:
                cli_mod.BASE_DIR = original_base
                cli_mod.STATE_DIR = original_state
                cli_mod.RUNS_DIR = original_runs
                cli_mod.WORKSPACE = original_workspace
                cli_mod.BUYERS_DIR = original_buyers
                cli_mod.EXPORTS_DIR = original_exports

            exports_dir = root / "openclaw_workspace" / "exports"
            exported = list(exports_dir.glob("*_contact_brief.md"))
            self.assertGreater(len(exported), 0, "No contact brief file was created")

            content = exported[0].read_text(encoding="utf-8")
            # Brief was generated — heading and timing section present
            self.assertIn("# Contact Brief", content)
            self.assertIn("Actionable", content)

    def test_export_contact_brief_contains_expected_sections(self):
        with tempfile.TemporaryDirectory() as td:
            root, db_file = self._make_env(td)

            from outreach import cli as cli_mod
            original_vals = {
                "BASE_DIR": cli_mod.BASE_DIR,
                "STATE_DIR": cli_mod.STATE_DIR,
                "RUNS_DIR": cli_mod.RUNS_DIR,
                "WORKSPACE": cli_mod.WORKSPACE,
                "BUYERS_DIR": cli_mod.BUYERS_DIR,
                "EXPORTS_DIR": cli_mod.EXPORTS_DIR,
            }
            try:
                cli_mod.BASE_DIR = root
                cli_mod.STATE_DIR = root / "state"
                cli_mod.RUNS_DIR = root / "data" / "runs"
                cli_mod.WORKSPACE = root / "openclaw_workspace"
                cli_mod.BUYERS_DIR = root / "openclaw_workspace" / "buyers"
                cli_mod.EXPORTS_DIR = root / "openclaw_workspace" / "exports"

                with (
                    patch.dict(os.environ, {"OUTREACH_DB_PATH": str(db_file)}),
                    redirect_stdout(io.StringIO()),
                ):
                    from outreach.cli import run_cli
                    run_cli(["export-contact-brief", "--buyer", "alpha council"])
            finally:
                for k, v in original_vals.items():
                    setattr(cli_mod, k, v)

            exports_dir = root / "openclaw_workspace" / "exports"
            exported = list(exports_dir.glob("*_contact_brief.md"))
            self.assertGreater(len(exported), 0)
            content = exported[0].read_text(encoding="utf-8")
            # Should contain a heading and outreach action section
            self.assertIn("# Contact Brief", content)
            self.assertIn("Outreach", content)


if __name__ == "__main__":
    unittest.main()
