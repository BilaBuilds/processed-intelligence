from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class OpenClawContextTests(unittest.TestCase):
    def test_package_buyer_context_uses_dossier_timing_label_when_signal_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            buyers_dir = root / "openclaw_workspace" / "buyers"
            buyers_dir.mkdir(parents=True, exist_ok=True)
            memory_dir = root / "openclaw_workspace" / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            state_dir = root / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            run_dir = root / "data" / "runs" / "2026-04-18_120000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (buyers_dir / "acme_council.md").write_text(
                "# Buyer Dossier — Acme Council\n\n"
                "## Timing intelligence\n\n"
                "- **Timing label:** 🟢 Actionable\n"
                "- **Confidence:** High — regular procurement cadence.\n"
                "- **Status:** due_soon\n"
                "- **Predicted window:** 2026-04-23 → 2026-05-04\n"
                "- **Action note:** Prepare outreach now.\n\n"
                "## Commercial intelligence\n\n"
                "- **Outreach status:** not_started\n",
                encoding="utf-8",
            )
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"run_id": run_dir.name, "status": "success"}),
                encoding="utf-8",
            )
            (run_dir / "buyer_timing_signals.json").write_text(
                json.dumps({"signals": []}),
                encoding="utf-8",
            )
            (state_dir / "buyer_history.jsonl").write_text(
                json.dumps({"buyer_name": "Acme Council", "tenders": [{"title": "Drainage Package", "published": "2026-03-15"}]}) + "\n",
                encoding="utf-8",
            )

            scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
            sys.path.insert(0, str(scripts_dir))
            try:
                with patch.dict(os.environ, {"TENDER_BASE_DIR": str(root)}, clear=False):
                    import importlib
                    import openclaw_context

                    importlib.reload(openclaw_context)
                    package = openclaw_context.package_buyer_context("Acme Council", mode="outreach")
            finally:
                sys.path.pop(0)

            self.assertEqual(package["timing"]["label"], "Actionable")


if __name__ == "__main__":
    unittest.main()
