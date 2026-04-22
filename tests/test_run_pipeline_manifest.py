import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import run_pipeline
import src
import src.outreach_state


def _base_pipeline_module_map(run_dir: Path, shortlist: Path, deduped: Path) -> dict[str, object]:
    return {
        "src.ingest": types.SimpleNamespace(
            run=lambda context: {
                "raw_count": 0,
                "raw_file": run_dir / "raw_tenders.jsonl",
                "ingest_mode": "incremental",
            }
        ),
        "src.normalize": types.SimpleNamespace(
            run=lambda context: {"norm_count": 0, "norm_file": run_dir / "normalized_tenders.jsonl"}
        ),
        "src.match": types.SimpleNamespace(
            run=lambda context: {"scored_count": 0, "scored_file": run_dir / "scored_tenders.jsonl"}
        ),
        "src.context": types.SimpleNamespace(
            run=lambda context: {"context_file": run_dir / "context_tenders.jsonl", "context_count": 0}
        ),
        "src.buyer_intel": types.SimpleNamespace(
            run=lambda context: {
                "buyer_intel_status": "ok_no_shortlist",
                "buyer_intel_accumulated": 0,
                "buyer_intel_briefs": {},
                "buyer_intel_briefs_attached": 0,
            },
            attach_briefs=lambda context: {"buyer_intel_briefs_attached": 0},
        ),
        "src.tender_forecast": types.SimpleNamespace(
            run=lambda context: {
                "forecast_status": "ok",
                "forecast_count": 0,
                "forecast_due_soon": 0,
                "forecast_file": run_dir / "tender_forecast.json",
            }
        ),
        "src.buyer_timing": types.SimpleNamespace(
            run=lambda context: {
                "buyer_timing_status": "ok",
                "buyer_timing_count": 0,
                "buyer_timing_due_soon": 0,
                "buyer_timing_due": 0,
                "buyer_timing_overdue": 0,
                "buyer_timing_slipped": 0,
                "buyer_timing_file": run_dir / "buyer_timing_signals.json",
                "buyer_timing_csv": run_dir / "buyer_timing_signals.csv",
                "buyer_timing_backtest_file": run_dir / "buyer_timing_backtest.json",
                "buyer_timing_backtest_sample_count": 0,
            }
        ),
        "src.patterns": types.SimpleNamespace(run=lambda context: {}),
        "src.select": types.SimpleNamespace(
            run=lambda context: {
                "shortlist_count": 0,
                "shortlist_file": shortlist,
                "shortlist_jsonl_file": run_dir / "shortlist.jsonl",
                "review_count": 0,
                "review_candidates_file": run_dir / "review_candidates.jsonl",
                "market_intelligence_count": 0,
                "market_intelligence_file": run_dir / "market_intelligence.jsonl",
                "rejected_count": 0,
                "rejected_tenders_count": 0,
                "rejected_tenders_file": run_dir / "rejected_tenders.jsonl",
                "select_rejection_reason_counts": {},
                "rejection_reason_counts": {},
                "select_eligible_count": 0,
                "select_stale_filtered_count": 0,
                "select_excluded_filtered_count": 0,
            }
        ),
        "src.decision": types.SimpleNamespace(
            run=lambda context: {
                "shortlist_file": shortlist,
                "decision_total_count": 0,
                "decision_pass_count": 0,
                "decision_verdict_counts": {},
                "decision_event_count": 0,
                "risk_signal_count": 0,
                "shortlist_count": 0,
            }
        ),
        "src.supplier_runner": types.SimpleNamespace(
            run=lambda context: {
                "supplier_match_status": "skipped",
                "supplier_match_tenders_processed": 0,
                "supplier_match_suppliers_evaluated": 0,
                "supplier_match_matches_total": 0,
                "supplier_match_matches_included": 0,
                "supplier_match_suppliers_excluded": 0,
                "supplier_match_market_profile": "construction",
                "supplier_match_market_profile_version": None,
                "supplier_match_source_file": "tests/fixtures/suppliers_construction.csv",
                "supplier_matches_file": None,
            }
        ),
        "src.dedupe": types.SimpleNamespace(
            run=lambda context: {
                "new_count": 0,
                "deduped_file": deduped,
                "dedupe_input_count": 0,
                "dedupe_new_count": 0,
                "dedupe_already_seen_count": 0,
                "dedupe_previously_seen_count": 0,
                "dedupe_batch_duplicate_count": 0,
                "dedupe_missing_key_count": 0,
            }
        ),
        "src.product_runner": types.SimpleNamespace(
            run_all_products=lambda *args, **kwargs: {
                "status": "ok",
                "enabled_count": 0,
                "generated_count": 0,
                "outputs": {},
            }
        ),
        "src.client_runner": types.SimpleNamespace(
            run_clients=lambda *args, **kwargs: {
                "status": "no_clients",
                "enabled_count": 0,
                "notified_count": 0,
                "outputs": {},
            }
        ),
        "src.outreach_queue": types.SimpleNamespace(
            build_and_write=lambda *args, **kwargs: {
                "outreach_queue_count": 0,
                "outreach_hot_count": 0,
                "outreach_follow_up_due_count": 0,
                "outreach_status": "ok",
            }
        ),
    }


class TestRunPipelineManifest(unittest.TestCase):
    def test_apply_manifest_fields_includes_fts_and_pattern_metadata(self) -> None:
        manifest = {}
        context = {
            "raw_count": 120,
            "ingest_counts_by_source": {"find_a_tender": 100, "contracts_finder": 20},
            "source_freshness": {"find_a_tender": "2026-04-01T00:00:00+00:00"},
            "ingest_mode": "backfill",
            "fts_window_start": "2026-03-01T00:00:00+00:00",
            "fts_window_end": "2026-03-04T00:00:00+00:00",
            "fts_chunk_count": 1,
            "fts_chunks_completed": 0,
            "fts_backfill_state_file": "C:\\temp\\fts_backfill_state.json",
            "fts_backfill_completed": False,
            "fts_request_count": 200,
            "fts_hit_request_cap": True,
            "fts_partial_backfill": True,
            "pattern_module_status": "ok",
            "pattern_signal_count": 2,
            "pattern_adjusted_count": 1,
            "pattern_artifacts": {"pattern_signals_file": "signals.json"},
            "shortlist_count": 3,
            "review_count": 4,
            "market_intelligence_count": 5,
            "rejected_count": 6,
            "rejection_reason_counts": {
                "inactive_status": 1,
                "award": 2,
                "awardUpdate": 3,
                "stale_deadline": 4,
                "below_threshold": 5,
            },
            "shortlist_jsonl_file": "shortlist.jsonl",
            "review_candidates_file": "review_candidates.jsonl",
            "market_intelligence_file": "market_intelligence.jsonl",
            "rejected_tenders_file": "rejected_tenders.jsonl",
            "lead_activation_state_file": "state.json",
            "lead_activation_state_created": False,
            "forecast_file": "tender_forecast.json",
            "buyer_timing_file": "buyer_timing_signals.json",
            "buyer_timing_csv": "buyer_timing_signals.csv",
            "buyer_timing_backtest_file": "buyer_timing_backtest.json",
            "forecast_due": 2,
            "forecast_overdue": 1,
            "buyer_timing_due": 3,
            "buyer_timing_overdue": 4,
            "buyer_timing_slipped": 1,
            "buyer_timing_backtest_sample_count": 7,
        }

        out = run_pipeline.apply_manifest_fields(manifest, context, {"removed_files": 0})

        self.assertEqual(out["ingest_mode"], "backfill")
        self.assertTrue(out["fts_hit_request_cap"])
        self.assertTrue(out["fts_partial_backfill"])
        self.assertEqual(out["pattern_module_status"], "ok")
        self.assertEqual(out["shortlist_count"], 3)
        self.assertEqual(out["review_count"], 4)
        self.assertEqual(out["market_intelligence_count"], 5)
        self.assertEqual(out["rejected_count"], 6)
        self.assertEqual(out["rejection_reason_counts"]["below_threshold"], 5)
        self.assertEqual(out["artifacts"]["shortlist_jsonl_file"], "shortlist.jsonl")
        self.assertEqual(out["artifacts"]["review_candidates_file"], "review_candidates.jsonl")
        self.assertEqual(out["artifacts"]["market_intelligence_file"], "market_intelligence.jsonl")
        self.assertEqual(out["artifacts"]["rejected_tenders_file"], "rejected_tenders.jsonl")
        self.assertEqual(out["artifacts"]["forecast_file"], "tender_forecast.json")
        self.assertEqual(out["artifacts"]["buyer_timing_backtest_file"], "buyer_timing_backtest.json")
        self.assertEqual(out["artifacts"]["pattern_artifacts"]["pattern_signals_file"], "signals.json")
        self.assertEqual(out["supplier_match_status"], "not_run")
        self.assertEqual(out["supplier_match_matches_included"], 0)
        self.assertIsNone(out["artifacts"]["supplier_matches_file"])
        self.assertEqual(out["forecast_due"], 2)
        self.assertEqual(out["buyer_timing_slipped"], 1)

    def test_apply_manifest_fields_includes_supplier_match_metadata(self) -> None:
        manifest = {}
        context = {
            "supplier_match_status": "ok",
            "supplier_match_tenders_processed": 3,
            "supplier_match_suppliers_evaluated": 45,
            "supplier_match_matches_total": 18,
            "supplier_match_matches_included": 9,
            "supplier_match_suppliers_excluded": 2,
            "supplier_match_market_profile": "construction",
            "supplier_match_market_profile_version": "1.0",
            "supplier_match_source_file": "tests/fixtures/suppliers_construction.csv",
            "supplier_matches_file": "supplier_matches.json",
            "lead_activation_state_file": "state.json",
            "lead_activation_state_created": False,
        }

        out = run_pipeline.apply_manifest_fields(manifest, context, {"removed_files": 0})

        self.assertEqual(out["supplier_match_status"], "ok")
        self.assertEqual(out["supplier_match_tenders_processed"], 3)
        self.assertEqual(out["supplier_match_suppliers_evaluated"], 45)
        self.assertEqual(out["supplier_match_matches_total"], 18)
        self.assertEqual(out["supplier_match_matches_included"], 9)
        self.assertEqual(out["supplier_match_suppliers_excluded"], 2)
        self.assertEqual(out["supplier_match_market_profile"], "construction")
        self.assertEqual(out["supplier_match_market_profile_version"], "1.0")
        self.assertEqual(out["supplier_match_source_file"], "tests/fixtures/suppliers_construction.csv")
        self.assertEqual(out["artifacts"]["supplier_matches_file"], "supplier_matches.json")

    def test_pattern_failure_is_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            deduped = run_dir / "new_tenders.json"
            deduped.write_text(json.dumps({"opportunities": []}), encoding="utf-8")
            shortlist = run_dir / "shortlist.json"
            shortlist.write_text(json.dumps({"opportunities": []}), encoding="utf-8")

            module_map = _base_pipeline_module_map(run_dir, shortlist, deduped)
            module_map["src.buyer_intel"] = types.SimpleNamespace(
                run=lambda context: {
                    "buyer_intel_status": "ok_no_shortlist",
                    "buyer_intel_accumulated": 0,
                    "buyer_intel_briefs": {},
                    "buyer_intel_briefs_attached": 0,
                },
                attach_briefs=lambda context: {"buyer_intel_briefs_attached": 1},
            )
            module_map["src.tender_forecast"] = types.SimpleNamespace(
                run=lambda context: {
                    "forecast_status": "ok",
                    "forecast_count": 3,
                    "forecast_due_soon": 1,
                    "forecast_file": run_dir / "tender_forecast.json",
                }
            )
            module_map["src.buyer_timing"] = types.SimpleNamespace(
                run=lambda context: {
                    "buyer_timing_status": "ok",
                    "buyer_timing_count": 3,
                    "buyer_timing_due_soon": 1,
                    "buyer_timing_due": 1,
                    "buyer_timing_overdue": 1,
                    "buyer_timing_slipped": 0,
                    "buyer_timing_file": run_dir / "buyer_timing_signals.json",
                    "buyer_timing_csv": run_dir / "buyer_timing_signals.csv",
                    "buyer_timing_backtest_file": run_dir / "buyer_timing_backtest.json",
                    "buyer_timing_backtest_sample_count": 2,
                }
            )
            module_map["src.patterns"] = types.SimpleNamespace(
                run=lambda context: (_ for _ in ()).throw(RuntimeError("pattern boom"))
            )
            module_map["src.select"] = types.SimpleNamespace(
                run=lambda context: {
                    "shortlist_count": 0,
                    "shortlist_file": shortlist,
                    "shortlist_jsonl_file": run_dir / "shortlist.jsonl",
                    "review_count": 1,
                    "review_candidates_file": run_dir / "review_candidates.jsonl",
                    "market_intelligence_count": 2,
                    "market_intelligence_file": run_dir / "market_intelligence.jsonl",
                    "rejected_count": 2,
                    "rejected_tenders_count": 2,
                    "rejected_tenders_file": run_dir / "rejected_tenders.jsonl",
                    "select_rejection_reason_counts": {"award": 1, "inactive_status": 1, "below_threshold": 2},
                    "rejection_reason_counts": {"award": 1, "inactive_status": 1, "below_threshold": 2},
                    "select_eligible_count": 0,
                    "select_stale_filtered_count": 0,
                    "select_excluded_filtered_count": 0,
                }
            )

            saved_manifests: list[dict] = []

            def fake_import(name: str):
                return module_map[name]

            def fake_save_manifest(_run_dir: Path, manifest: dict) -> None:
                saved_manifests.append(json.loads(json.dumps(manifest)))

            with patch("run_pipeline.make_run_dir", return_value=run_dir), patch(
                "run_pipeline.cleanup_old_run_artifacts", return_value={"removed_files": 0}
            ), patch(
                "run_pipeline.save_manifest", side_effect=fake_save_manifest
            ), patch(
                "src.outreach_state.ensure_lead_activation_state", return_value=False
            ):
                run_pipeline.run_pipeline(
                    check_cooldown_fn=lambda _: {"run_mode": "full", "cooldown_reason": "", "force_run": False},
                    import_module_fn=fake_import,
                    notifier_runner_fn=lambda *_a, **_k: {"notify_results": {"discord": "skipped (nothing new)"}},
                )

            final_manifest = saved_manifests[-1]
            self.assertEqual(final_manifest["steps"]["patterns"]["status"], "error")
            self.assertEqual(final_manifest["steps"]["buyer_intel_attach"]["status"], "ok")
            self.assertEqual(final_manifest["status"], "success_with_warnings")
            self.assertEqual(final_manifest["rejected_tenders_count"], 2)
            self.assertEqual(final_manifest["review_count"], 1)
            self.assertEqual(final_manifest["market_intelligence_count"], 2)
            self.assertEqual(final_manifest["rejected_count"], 2)
            self.assertEqual(final_manifest["buyer_intel_briefs_attached"], 1)
            self.assertEqual(
                final_manifest["select_rejection_reason_counts"],
                {"award": 1, "inactive_status": 1, "below_threshold": 2},
            )
            self.assertEqual(
                final_manifest["rejection_reason_counts"],
                {"award": 1, "inactive_status": 1, "below_threshold": 2},
            )
            self.assertEqual(
                final_manifest["artifacts"]["review_candidates_file"],
                str(run_dir / "review_candidates.jsonl"),
            )
            self.assertEqual(
                final_manifest["artifacts"]["market_intelligence_file"],
                str(run_dir / "market_intelligence.jsonl"),
            )
            self.assertEqual(
                final_manifest["artifacts"]["rejected_tenders_file"],
                str(run_dir / "rejected_tenders.jsonl"),
            )
            self.assertEqual(
                final_manifest["artifacts"]["buyer_timing_backtest_file"],
                str(run_dir / "buyer_timing_backtest.json"),
            )

    def test_supplier_match_step_ok_is_recorded_and_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            deduped = run_dir / "new_tenders.json"
            deduped.write_text(json.dumps({"opportunities": []}), encoding="utf-8")
            shortlist = run_dir / "decision_shortlist.json"
            shortlist.write_text(json.dumps({"opportunities": []}), encoding="utf-8")
            supplier_matches = run_dir / "supplier_matches.json"

            module_map = _base_pipeline_module_map(run_dir, shortlist, deduped)
            module_map["src.select"] = types.SimpleNamespace(
                run=lambda context: {
                    "shortlist_count": 1,
                    "shortlist_file": shortlist,
                    "shortlist_jsonl_file": run_dir / "shortlist.jsonl",
                    "review_count": 0,
                    "review_candidates_file": run_dir / "review_candidates.jsonl",
                    "market_intelligence_count": 0,
                    "market_intelligence_file": run_dir / "market_intelligence.jsonl",
                    "rejected_count": 0,
                    "rejected_tenders_count": 0,
                    "rejected_tenders_file": run_dir / "rejected_tenders.jsonl",
                    "select_rejection_reason_counts": {},
                    "rejection_reason_counts": {},
                    "select_eligible_count": 1,
                    "select_stale_filtered_count": 0,
                    "select_excluded_filtered_count": 0,
                }
            )
            module_map["src.decision"] = types.SimpleNamespace(
                run=lambda context: {
                    "shortlist_file": shortlist,
                    "decision_total_count": 1,
                    "decision_pass_count": 1,
                    "decision_verdict_counts": {"BID": 1},
                    "decision_event_count": 1,
                    "risk_signal_count": 0,
                    "shortlist_count": 1,
                }
            )
            module_map["src.supplier_runner"] = types.SimpleNamespace(
                run=lambda context: {
                    "supplier_match_status": "ok",
                    "supplier_match_tenders_processed": 1,
                    "supplier_match_suppliers_evaluated": 15,
                    "supplier_match_matches_total": 6,
                    "supplier_match_matches_included": 3,
                    "supplier_match_suppliers_excluded": 2,
                    "supplier_match_market_profile": "construction",
                    "supplier_match_market_profile_version": "1.0",
                    "supplier_match_source_file": "tests/fixtures/suppliers_construction.csv",
                    "supplier_matches_file": supplier_matches,
                }
            )
            module_map["src.dedupe"] = types.SimpleNamespace(
                run=lambda context: {
                    "new_count": 0,
                    "deduped_file": deduped,
                    "dedupe_input_count": 1,
                    "dedupe_new_count": 0,
                    "dedupe_already_seen_count": 1,
                    "dedupe_previously_seen_count": 1,
                    "dedupe_batch_duplicate_count": 0,
                    "dedupe_missing_key_count": 0,
                }
            )

            def fake_import(name: str):
                return module_map[name]

            with patch("run_pipeline.make_run_dir", return_value=run_dir), patch(
                "run_pipeline.cleanup_old_run_artifacts", return_value={"removed_files": 0}
            ), patch(
                "src.outreach_state.ensure_lead_activation_state", return_value=False
            ):
                run_pipeline.run_pipeline(
                    check_cooldown_fn=lambda _: {"run_mode": "full", "cooldown_reason": "", "force_run": False},
                    import_module_fn=fake_import,
                    notifier_runner_fn=lambda *_a, **_k: {"notify_results": {"discord": "skipped (nothing new)"}},
                )

            final_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(final_manifest["steps"]["supplier_match"]["status"], "ok")
            self.assertEqual(final_manifest["steps"]["supplier_match"]["matches_included"], 3)
            self.assertEqual(final_manifest["supplier_match_status"], "ok")
            self.assertEqual(final_manifest["supplier_match_matches_included"], 3)
            self.assertEqual(final_manifest["artifacts"]["supplier_matches_file"], str(supplier_matches))
            self.assertEqual(final_manifest["steps"]["dedupe"]["status"], "ok")

    def test_supplier_match_step_skipped_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            deduped = run_dir / "new_tenders.json"
            deduped.write_text(json.dumps({"opportunities": []}), encoding="utf-8")
            shortlist = run_dir / "decision_shortlist.json"
            shortlist.write_text(json.dumps({"opportunities": []}), encoding="utf-8")

            module_map = _base_pipeline_module_map(run_dir, shortlist, deduped)

            def fake_import(name: str):
                return module_map[name]

            with patch("run_pipeline.make_run_dir", return_value=run_dir), patch(
                "run_pipeline.cleanup_old_run_artifacts", return_value={"removed_files": 0}
            ), patch(
                "src.outreach_state.ensure_lead_activation_state", return_value=False
            ):
                run_pipeline.run_pipeline(
                    check_cooldown_fn=lambda _: {"run_mode": "full", "cooldown_reason": "", "force_run": False},
                    import_module_fn=fake_import,
                    notifier_runner_fn=lambda *_a, **_k: {"notify_results": {"discord": "skipped (nothing new)"}},
                )

            final_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(final_manifest["steps"]["supplier_match"]["status"], "skipped")
            self.assertEqual(final_manifest["supplier_match_status"], "skipped")
            self.assertIsNone(final_manifest["artifacts"]["supplier_matches_file"])
            self.assertEqual(final_manifest["steps"]["dedupe"]["status"], "ok")

    def test_supplier_match_failure_is_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            deduped = run_dir / "new_tenders.json"
            deduped.write_text(json.dumps({"opportunities": []}), encoding="utf-8")
            shortlist = run_dir / "decision_shortlist.json"
            shortlist.write_text(json.dumps({"opportunities": []}), encoding="utf-8")

            module_map = _base_pipeline_module_map(run_dir, shortlist, deduped)
            module_map["src.select"] = types.SimpleNamespace(
                run=lambda context: {
                    "shortlist_count": 1,
                    "shortlist_file": shortlist,
                    "shortlist_jsonl_file": run_dir / "shortlist.jsonl",
                    "review_count": 0,
                    "review_candidates_file": run_dir / "review_candidates.jsonl",
                    "market_intelligence_count": 0,
                    "market_intelligence_file": run_dir / "market_intelligence.jsonl",
                    "rejected_count": 0,
                    "rejected_tenders_count": 0,
                    "rejected_tenders_file": run_dir / "rejected_tenders.jsonl",
                    "select_rejection_reason_counts": {},
                    "rejection_reason_counts": {},
                    "select_eligible_count": 1,
                    "select_stale_filtered_count": 0,
                    "select_excluded_filtered_count": 0,
                }
            )
            module_map["src.decision"] = types.SimpleNamespace(
                run=lambda context: {
                    "shortlist_file": shortlist,
                    "decision_total_count": 1,
                    "decision_pass_count": 1,
                    "decision_verdict_counts": {"BID": 1},
                    "decision_event_count": 1,
                    "risk_signal_count": 0,
                    "shortlist_count": 1,
                }
            )
            module_map["src.supplier_runner"] = types.SimpleNamespace(
                run=lambda context: (_ for _ in ()).throw(RuntimeError("supplier boom"))
            )
            module_map["src.dedupe"] = types.SimpleNamespace(
                run=lambda context: {
                    "new_count": 0,
                    "deduped_file": deduped,
                    "dedupe_input_count": 1,
                    "dedupe_new_count": 0,
                    "dedupe_already_seen_count": 1,
                    "dedupe_previously_seen_count": 1,
                    "dedupe_batch_duplicate_count": 0,
                    "dedupe_missing_key_count": 0,
                }
            )

            def fake_import(name: str):
                return module_map[name]

            with patch("run_pipeline.make_run_dir", return_value=run_dir), patch(
                "run_pipeline.cleanup_old_run_artifacts", return_value={"removed_files": 0}
            ), patch(
                "src.outreach_state.ensure_lead_activation_state", return_value=False
            ):
                run_pipeline.run_pipeline(
                    check_cooldown_fn=lambda _: {"run_mode": "full", "cooldown_reason": "", "force_run": False},
                    import_module_fn=fake_import,
                    notifier_runner_fn=lambda *_a, **_k: {"notify_results": {"discord": "skipped (nothing new)"}},
                )

            final_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(final_manifest["steps"]["supplier_match"]["status"], "failed")
            self.assertEqual(final_manifest["supplier_match_status"], "failed")
            self.assertEqual(final_manifest["status"], "success_with_warnings")
            self.assertEqual(final_manifest["steps"]["dedupe"]["status"], "ok")
            self.assertIsNone(final_manifest["artifacts"]["supplier_matches_file"])

    def test_dashboard_bundle_runs_after_final_manifest_save(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            run_dir = base_dir / "data" / "runs" / "2026-04-19_090000"
            run_dir.mkdir(parents=True, exist_ok=True)
            scripts_dir = base_dir / "scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)

            (scripts_dir / "build_dashboard_bundle.py").write_text(
                """
import json
import os
from pathlib import Path

def main():
    run_dir = Path(os.environ["TEST_DASHBOARD_RUN_DIR"])
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    probe_path = Path(os.environ["TEST_DASHBOARD_PROBE"])
    probe_path.write_text(
        json.dumps({"run_id": manifest.get("run_id"), "status": manifest.get("status")}),
        encoding="utf-8",
    )
""".strip(),
                encoding="utf-8",
            )

            deduped = run_dir / "new_tenders.json"
            deduped.write_text(json.dumps({"opportunities": []}), encoding="utf-8")
            shortlist = run_dir / "shortlist.json"
            shortlist.write_text(json.dumps({"opportunities": []}), encoding="utf-8")

            module_map = _base_pipeline_module_map(run_dir, shortlist, deduped)

            def fake_import(name: str):
                return module_map[name]

            probe_path = base_dir / "dashboard_probe.json"
            old_base_dir = run_pipeline.BASE_DIR
            old_data_dir = run_pipeline.DATA_DIR
            old_config_dir = run_pipeline.CONFIG_DIR
            old_state_dir = run_pipeline.STATE_DIR
            old_runs_dir = run_pipeline.RUNS_DIR

            env_patch = patch.dict(
                os.environ,
                {
                    "TEST_DASHBOARD_RUN_DIR": str(run_dir),
                    "TEST_DASHBOARD_PROBE": str(probe_path),
                },
                clear=False,
            )

            with env_patch, patch("run_pipeline.make_run_dir", return_value=run_dir), patch(
                "run_pipeline.cleanup_old_run_artifacts", return_value={"removed_files": 0}
            ), patch(
                "src.outreach_state.ensure_lead_activation_state", return_value=False
            ):
                run_pipeline.BASE_DIR = base_dir
                run_pipeline.DATA_DIR = base_dir / "data"
                run_pipeline.CONFIG_DIR = base_dir / "config"
                run_pipeline.STATE_DIR = base_dir / "state"
                run_pipeline.RUNS_DIR = base_dir / "data" / "runs"
                try:
                    run_pipeline.run_pipeline(
                        check_cooldown_fn=lambda _: {"run_mode": "full", "cooldown_reason": "", "force_run": False},
                        import_module_fn=fake_import,
                        notifier_runner_fn=lambda *_a, **_k: {"notify_results": {"discord": "skipped (nothing new)"}},
                    )
                finally:
                    run_pipeline.BASE_DIR = old_base_dir
                    run_pipeline.DATA_DIR = old_data_dir
                    run_pipeline.CONFIG_DIR = old_config_dir
                    run_pipeline.STATE_DIR = old_state_dir
                    run_pipeline.RUNS_DIR = old_runs_dir

            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            final_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(probe["run_id"], "2026-04-19_090000")
            self.assertEqual(probe["status"], "success_empty")
            self.assertEqual(final_manifest["steps"]["dashboard"]["status"], "ok")
            self.assertEqual(final_manifest["status"], "success_empty")


if __name__ == "__main__":
    unittest.main()
