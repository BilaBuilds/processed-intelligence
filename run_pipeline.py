#!/usr/bin/env python3
"""
Project BigBoi - Tender Engine
==============================
Main pipeline orchestrator.

Run:
    python run_pipeline.py

Env vars:
    TENDER_WEBHOOK_URL   - Discord webhook (required for notifications)
    TENDER_MIN_SCORE     - Minimum score threshold (default 20)
    TENDER_SHORTLIST_N   - Max shortlisted tenders per run (default 10)
    TENDER_NOTIFY_N      - Max tenders sent per notification (default 5)
    TENDER_DECISION_BID_MIN_SCORE - Score threshold for BID (default 40)
    TENDER_DECISION_REVIEW_MIN_SCORE - Score threshold for REVIEW (default 28)
    TENDER_DECISION_SME_VALUE_MAX - Value ceiling before BID is downgraded (default 5000000)
    TENDER_DECISION_INCLUDE - Which verdicts pass downstream (default BID,REVIEW)
    TENDER_RAW_RETENTION_DAYS - Days to keep heavy JSONL run artifacts (default 7)
    TENDER_BASE_DIR      - Base dir override (default: this folder)

Each step is a separate module in /src.
If any core step fails, the run is marked failed and no notifications are sent.
Notifier failures are logged but do NOT fail the run.
Pattern enrichment failures are logged but do NOT fail the run.
"""

import importlib
import json
import logging
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.getenv("TENDER_BASE_DIR", str(SCRIPT_DIR))).expanduser().resolve()
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
CONFIG_DIR = BASE_DIR / "config"
STATE_DIR = BASE_DIR / "state"
LEAD_ACTIVATION_STATE_FILE = STATE_DIR / "lead_activation_state.json"

# Valid run_mode values for manifest
RUN_MODE_FULL = "full"
RUN_MODE_COOLDOWN_SKIP = "cooldown_skip"

HEAVY_RUN_ARTIFACTS = {
    "raw_tenders.jsonl",
    "normalized_tenders.jsonl",
    "scored_tenders.jsonl",
}

sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pipeline")


def make_run_dir() -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    if run_dir.exists():
        run_id = f"{run_id}_{secrets.token_hex(2)}"
        run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_manifest(run_dir: Path, manifest: dict) -> None:
    path = run_dir / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Manifest saved -> %s", path)


def load_env_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def load_env_defaults() -> None:
    loaded = {}
    loaded.update(load_env_file(BASE_DIR / ".env"))
    loaded.update(load_env_file(CONFIG_DIR / ".env"))
    if loaded:
        log.info("Loaded %d env var(s) from local .env files.", len(loaded))


def cleanup_old_run_artifacts() -> dict[str, int]:
    retention_days = int(os.getenv("TENDER_RAW_RETENTION_DAYS", "7"))
    if retention_days < 1:
        return {"removed_files": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed_files = 0
    skipped_files = 0

    if not RUNS_DIR.exists():
        return {"removed_files": 0}

    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        for name in HEAVY_RUN_ARTIFACTS:
            candidate = run_dir / name
            if not candidate.exists():
                continue
            try:
                modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
                if modified < cutoff:
                    candidate.unlink(missing_ok=True)
                    removed_files += 1
            except (PermissionError, OSError) as e:
                log.warning("Could not delete %s: %s (skipping)", candidate, e)
                skipped_files += 1

    return {"removed_files": removed_files, "skipped_files": skipped_files}


def summarize_notify_results(channel_results: dict[str, str]) -> dict[str, int]:
    attempted = 0
    sent = 0
    skipped = 0
    failed = 0

    for status in channel_results.values():
        lowered = status.lower()
        if lowered.startswith("ok"):
            attempted += 1
            sent += 1
        elif lowered.startswith("skipped"):
            skipped += 1
        elif lowered.startswith("failed") or lowered.startswith("error"):
            attempted += 1
            failed += 1
        else:
            attempted += 1
            failed += 1

    return {
        "notify_attempted": attempted,
        "notify_sent": sent,
        "notify_skipped": skipped,
        "notify_failed": failed,
    }


def apply_manifest_fields(manifest: dict, context: dict, cleanup_stats: dict[str, int]) -> dict:
    manifest["ingest_total_count"] = context.get("raw_count", 0)
    manifest["ingest_counts_by_source"] = context.get("ingest_counts_by_source", {})
    manifest["source_freshness"] = context.get("source_freshness", {})
    manifest["ingest_mode"] = context.get("ingest_mode", "incremental")
    manifest["fts_window_start"] = context.get("fts_window_start")
    manifest["fts_window_end"] = context.get("fts_window_end")
    manifest["fts_chunk_count"] = context.get("fts_chunk_count", 0)
    manifest["fts_chunks_completed"] = context.get("fts_chunks_completed", 0)
    manifest["fts_backfill_state_file"] = context.get("fts_backfill_state_file")
    manifest["fts_backfill_completed"] = bool(context.get("fts_backfill_completed", False))
    manifest["fts_request_count"] = context.get("fts_request_count", 0)
    manifest["fts_hit_request_cap"] = bool(context.get("fts_hit_request_cap", False))
    manifest["fts_partial_backfill"] = bool(context.get("fts_partial_backfill", False))
    manifest["normalized_kept_count"] = context.get("norm_count", 0)
    manifest["normalized_dropped_count"] = context.get("norm_dropped_count", 0)
    manifest["pattern_module_status"] = context.get("pattern_module_status", "disabled")
    manifest["pattern_signal_count"] = context.get("pattern_signal_count", 0)
    manifest["pattern_adjusted_count"] = context.get("pattern_adjusted_count", 0)
    manifest["select_eligible_count"] = context.get("select_eligible_count", 0)
    manifest["select_stale_filtered_count"] = context.get("select_stale_filtered_count", 0)
    manifest["select_excluded_filtered_count"] = context.get("select_excluded_filtered_count", 0)
    manifest["rejected_tenders_count"] = context.get("rejected_tenders_count", 0)
    manifest["rejected_count"] = context.get("rejected_count", context.get("rejected_tenders_count", 0))
    manifest["review_count"] = context.get("review_count", 0)
    manifest["market_intelligence_count"] = context.get("market_intelligence_count", 0)
    manifest["select_rejection_reason_counts"] = context.get("select_rejection_reason_counts", {})
    manifest["rejection_reason_counts"] = context.get(
        "rejection_reason_counts",
        context.get("select_rejection_reason_counts", {}),
    )
    manifest["shortlist_count"] = context.get("shortlist_count", 0)
    manifest["dedupe_input_count"] = context.get("dedupe_input_count", 0)
    manifest["dedupe_new_count"] = context.get("dedupe_new_count", 0)
    manifest["dedupe_already_seen_count"] = context.get("dedupe_already_seen_count", 0)
    manifest["dedupe_previously_seen_count"] = context.get("dedupe_previously_seen_count", 0)
    manifest["dedupe_batch_duplicate_count"] = context.get("dedupe_batch_duplicate_count", 0)
    manifest["dedupe_missing_key_count"] = context.get("dedupe_missing_key_count", 0)
    dedupe_input = manifest["dedupe_input_count"]
    dedupe_output_total = (
        manifest["dedupe_new_count"]
        + manifest["dedupe_already_seen_count"]
        + manifest["dedupe_missing_key_count"]
    )
    manifest["dedupe_reconciled"] = dedupe_input == dedupe_output_total
    manifest["new_count"] = context.get("new_count", 0)
    manifest["notify_attempted"] = context.get("notify_attempted", 0)
    manifest["notify_sent"] = context.get("notify_sent", 0)
    manifest["notify_skipped"] = context.get("notify_skipped", 0)
    manifest["notify_failed"] = context.get("notify_failed", 0)
    manifest["notify_opportunity_count"] = context.get("notify_opportunity_count", 0)
    manifest["notify_error_detail"] = context.get("notify_error_detail", {})
    manifest["no_new_tenders"] = manifest["new_count"] == 0
    manifest["operational_state"] = (
        "healthy_no_new_tenders" if manifest["no_new_tenders"] else "healthy_with_new_tenders"
    )
    manifest["source_health"] = context.get("source_health", {})
    manifest["decision_total_count"] = context.get("decision_total_count", 0)
    manifest["decision_pass_count"] = context.get("decision_pass_count", 0)
    manifest["decision_verdict_counts"] = context.get("decision_verdict_counts", {})
    manifest["decision_event_count"] = context.get("decision_event_count", 0)
    manifest["risk_signal_count"] = context.get("risk_signal_count", 0)
    manifest["supplier_match_status"] = context.get("supplier_match_status", "not_run")
    manifest["supplier_match_tenders_processed"] = context.get("supplier_match_tenders_processed", 0)
    manifest["supplier_match_suppliers_evaluated"] = context.get("supplier_match_suppliers_evaluated", 0)
    manifest["supplier_match_matches_total"] = context.get("supplier_match_matches_total", 0)
    manifest["supplier_match_matches_included"] = context.get("supplier_match_matches_included", 0)
    manifest["supplier_match_suppliers_excluded"] = context.get("supplier_match_suppliers_excluded", 0)
    manifest["supplier_match_market_profile"] = context.get("supplier_match_market_profile")
    manifest["supplier_match_market_profile_version"] = context.get("supplier_match_market_profile_version")
    manifest["supplier_match_source_file"] = context.get("supplier_match_source_file")
    manifest["supplier_entity_count"] = context.get("supplier_entity_count", 0)
    manifest["lead_activation_state_file"] = str(context.get("lead_activation_state_file"))
    manifest["lead_activation_state_created"] = bool(context.get("lead_activation_state_created"))
    manifest["artifacts"] = {
        "decision_events_file": str(context.get("decision_events_file"))
        if context.get("decision_events_file")
        else None,
        "risk_signals_file": str(context.get("risk_signals_file"))
        if context.get("risk_signals_file")
        else None,
        "supplier_entities_file": str(context.get("supplier_entities_file"))
        if context.get("supplier_entities_file")
        else None,
        "supplier_matches_file": str(context.get("supplier_matches_file"))
        if context.get("supplier_matches_file")
        else None,
        "deduped_file": str(context.get("deduped_file")) if context.get("deduped_file") else None,
        "shortlist_jsonl_file": str(context.get("shortlist_jsonl_file"))
        if context.get("shortlist_jsonl_file")
        else None,
        "review_candidates_file": str(context.get("review_candidates_file"))
        if context.get("review_candidates_file")
        else None,
        "market_intelligence_file": str(context.get("market_intelligence_file"))
        if context.get("market_intelligence_file")
        else None,
        "rejected_tenders_file": str(context.get("rejected_tenders_file"))
        if context.get("rejected_tenders_file")
        else None,
        "pattern_artifacts": context.get("pattern_artifacts", {}),
        "forecast_file": str(context.get("forecast_file")) if context.get("forecast_file") else None,
        "buyer_timing_file": str(context.get("buyer_timing_file")) if context.get("buyer_timing_file") else None,
        "buyer_timing_csv": str(context.get("buyer_timing_csv")) if context.get("buyer_timing_csv") else None,
        "buyer_timing_backtest_file": str(context.get("buyer_timing_backtest_file"))
        if context.get("buyer_timing_backtest_file")
        else None,
    }
    manifest["buyer_intel_status"] = context.get("buyer_intel_status", "disabled")
    manifest["buyer_intel_accumulated"] = context.get("buyer_intel_accumulated", 0)
    manifest["buyer_intel_unique_buyers"] = context.get("buyer_intel_unique_buyers", 0)
    manifest["buyer_intel_briefs_attached"] = context.get("buyer_intel_briefs_attached", 0)
    manifest["buyer_watchlist_count"] = context.get("buyer_watchlist_count", 0)
    manifest["buyer_watchlist_hot"] = context.get("buyer_watchlist_hot", 0)
    manifest["buyer_watchlist_warm"] = context.get("buyer_watchlist_warm", 0)
    manifest["buyer_watchlist_status"] = context.get("buyer_watchlist_status", "disabled")
    manifest["forecast_status"] = context.get("forecast_status", "disabled")
    manifest["forecast_count"] = context.get("forecast_count", 0)
    manifest["forecast_due_soon"] = context.get("forecast_due_soon", 0)
    manifest["forecast_due"] = context.get("forecast_due", 0)
    manifest["forecast_overdue"] = context.get("forecast_overdue", 0)
    manifest["buyer_timing_status"] = context.get("buyer_timing_status", "disabled")
    manifest["buyer_timing_count"] = context.get("buyer_timing_count", 0)
    manifest["buyer_timing_due_soon"] = context.get("buyer_timing_due_soon", 0)
    manifest["buyer_timing_due"] = context.get("buyer_timing_due", 0)
    manifest["buyer_timing_overdue"] = context.get("buyer_timing_overdue", 0)
    manifest["buyer_timing_slipped"] = context.get("buyer_timing_slipped", 0)
    manifest["buyer_timing_backtest_sample_count"] = context.get("buyer_timing_backtest_sample_count", 0)
    manifest["cleanup"] = cleanup_stats

    # T1: run_mode (full | cooldown_skip)
    manifest["run_mode"] = context.get("run_mode", RUN_MODE_FULL)
    manifest["cooldown_reason"] = context.get("cooldown_reason", "")

    # T2: CF release_tag visibility
    manifest["cf_release_tag_counts"] = context.get("cf_release_tag_counts", {})

    # T3: buyer intel dual-surface attachment count
    manifest["buyer_intel_attached_count"] = context.get("buyer_intel_briefs_attached", 0)

    # T4/T5: timing visibility counts
    manifest["timing_visible_count"] = context.get("timing_visible_count", 0)
    manifest["timing_actionable_count"] = context.get("timing_actionable_count", 0)

    # T6: normalize filter breakdown
    manifest["norm_status_filtered_count"] = context.get("norm_status_filtered_count", 0)
    manifest["norm_deadline_filtered_count"] = context.get("norm_deadline_filtered_count", 0)
    manifest["norm_value_filtered_count"] = context.get("norm_value_filtered_count", 0)
    manifest["value_filter_mode"] = context.get("value_filter_mode", "soft")

    # Outreach Queue
    manifest["outreach_queue_count"]         = context.get("outreach_queue_count", 0)
    manifest["outreach_hot_count"]           = context.get("outreach_hot_count", 0)
    manifest["outreach_follow_up_due_count"] = context.get("outreach_follow_up_due_count", 0)
    manifest["outreach_status"]              = context.get("outreach_status", "not_run")

    return manifest


def run_notifiers(context: dict, run_id: str) -> dict:
    """
    Run all configured notifiers against new_tenders.json.
    Notifier failures are logged but never fail the pipeline.
    """
    from src.notify.discord import DiscordNotifier

    notifiers = [DiscordNotifier()]
    results: dict[str, str] = {}

    deduped_file = context.get("deduped_file")
    if not deduped_file:
        log.warning("No deduped_file in context - skipping notifications.")
        for notifier in notifiers:
            results[notifier.name] = "skipped (missing deduped_file)"
        summary = summarize_notify_results(results)
        return {
            "notify_results": results,
            **summary,
            "notify_opportunity_count": 0,
        }

    with open(deduped_file, encoding="utf-8") as f:
        data = json.load(f)
    opportunities = data.get("opportunities", [])

    if not opportunities:
        log.info("No new opportunities - nothing to notify.")
        for notifier in notifiers:
            results[notifier.name] = "skipped (nothing new)"
        summary = summarize_notify_results(results)
        return {
            "notify_results": results,
            **summary,
            "notify_opportunity_count": 0,
        }

    error_detail: dict[str, str] = {}
    for notifier in notifiers:
        try:
            success = notifier.send(opportunities, run_id)
            results[notifier.name] = "ok" if success else "failed"
        except ValueError as exc:
            log.error("Notifier '%s' config error: %s", notifier.name, exc)
            results[notifier.name] = f"error: {exc}"
            error_detail[notifier.name] = str(exc)
        except Exception as exc:
            log.error("Notifier '%s' raised an exception: %s", notifier.name, exc)
            results[notifier.name] = f"error: {exc}"
            error_detail[notifier.name] = str(exc)

    summary = summarize_notify_results(results)
    return {
        "notify_results": results,
        **summary,
        "notify_opportunity_count": len(opportunities),
        "notify_error_detail": error_detail,
    }


def run_pipeline(
    *,
    check_cooldown_fn=None,
    import_module_fn=None,
    notifier_runner_fn=None,
) -> None:
    import importlib as _importlib
    from src.run_guard import check_cooldown as _check_cooldown

    check_cooldown_fn = check_cooldown_fn or _check_cooldown
    import_module_fn = import_module_fn or _importlib.import_module
    notifier_runner_fn = notifier_runner_fn or run_notifiers

    start = time.time()
    load_env_defaults()

    cleanup_stats = cleanup_old_run_artifacts()
    if cleanup_stats["removed_files"] > 0:
        log.info("Cleanup removed %d old run artifact file(s).", cleanup_stats["removed_files"])

    run_dir = make_run_dir()
    run_id = run_dir.name
    log.info("=== Tender Engine starting  |  run: %s ===", run_id)
    from src.outreach_state import ensure_lead_activation_state

    lead_state_created = ensure_lead_activation_state(LEAD_ACTIVATION_STATE_FILE)
    if lead_state_created:
        log.info("Created outreach state bootstrap -> %s", LEAD_ACTIVATION_STATE_FILE)

    # --- Cooldown guard (T1) ---
    guard = check_cooldown_fn(DATA_DIR)
    run_mode = guard["run_mode"]
    cooldown_reason = guard["cooldown_reason"]

    if run_mode == RUN_MODE_COOLDOWN_SKIP:
        log.info("=== Pipeline COOLDOWN SKIP — %s ===", cooldown_reason)
        # Write a minimal manifest for observability
        skip_manifest = {
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_duration_s": round(time.time() - start, 2),
            "status": RUN_MODE_COOLDOWN_SKIP,
            "run_mode": RUN_MODE_COOLDOWN_SKIP,
            "cooldown_reason": cooldown_reason,
            "steps": {},
        }
        save_manifest(run_dir, skip_manifest)
        return

    manifest = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "run_mode": run_mode,
        "steps": {},
    }

    steps = [
        ("ingest", "src.ingest", "run"),
        ("normalize", "src.normalize", "run"),
        ("match", "src.match", "run"),
        ("context", "src.context", "run"),
        ("buyer_intel", "src.buyer_intel", "run"),
        ("tender_forecast", "src.tender_forecast", "run"),
        ("buyer_timing", "src.buyer_timing", "run"),
        ("patterns", "src.patterns", "run"),
        ("select", "src.select", "run"),
        ("decision", "src.decision", "run"),
        ("supplier_match", "src.supplier_runner", "run"),
        ("dedupe", "src.dedupe", "run"),
    ]

    context = {
        "run_dir": run_dir,
        "data_dir": DATA_DIR,
        "config_dir": CONFIG_DIR,
        "state_dir": STATE_DIR,
        "lead_activation_state_file": LEAD_ACTIVATION_STATE_FILE,
        "lead_activation_state_created": lead_state_created,
        "run_mode": run_mode,
        "cooldown_reason": cooldown_reason,
    }

    for step_name, module_path, func_name in steps:
        log.info("--- Step: %s ---", step_name)
        step_start = time.time()
        try:
            module = import_module_fn(module_path)
            func = getattr(module, func_name)
            result = func(context) or {}
            context.update(result)

            duration = round(time.time() - step_start, 2)
            if step_name == "supplier_match":
                step_status = result.get("supplier_match_status", "ok")
                manifest["steps"][step_name] = {
                    "status": step_status,
                    "duration_s": duration,
                    "tenders_processed": result.get("supplier_match_tenders_processed", 0),
                    "suppliers_evaluated": result.get("supplier_match_suppliers_evaluated", 0),
                    "matches_included": result.get("supplier_match_matches_included", 0),
                }
                if step_status == "skipped":
                    log.info("Step '%s' SKIPPED in %.2fs", step_name, duration)
                else:
                    log.info("Step '%s' OK in %.2fs", step_name, duration)
            else:
                manifest["steps"][step_name] = {"status": "ok", "duration_s": duration}
                log.info("Step '%s' OK in %.2fs", step_name, duration)

        except Exception as exc:
            if step_name in ("patterns", "buyer_intel", "tender_forecast", "buyer_timing", "supplier_match"):
                duration = round(time.time() - step_start, 2)
                manifest["steps"][step_name] = {
                    "status": "failed" if step_name == "supplier_match" else "error",
                    "error": str(exc),
                    "duration_s": duration,
                }
                if step_name == "patterns":
                    context.update(
                        {
                            "pattern_module_status": "error",
                            "pattern_signal_count": 0,
                            "pattern_adjusted_count": 0,
                            "pattern_artifacts": {},
                        }
                    )
                    log.error("Pattern step error (non-fatal): %s", exc)
                elif step_name == "tender_forecast":
                    context.update(
                        {
                            "forecast_status": "error",
                            "forecast_count": 0,
                            "forecast_due_soon": 0,
                        }
                    )
                    log.error("Tender forecast step error (non-fatal): %s", exc)
                elif step_name == "buyer_timing":
                    context.update(
                        {
                            "buyer_timing_status": "error",
                            "buyer_timing_count": 0,
                            "buyer_timing_due_soon": 0,
                        }
                    )
                    log.error("Buyer timing step error (non-fatal): %s", exc)
                elif step_name == "supplier_match":
                    context.update(
                        {
                            "supplier_match_status": "failed",
                            "supplier_match_tenders_processed": 0,
                            "supplier_match_suppliers_evaluated": 0,
                            "supplier_match_matches_total": 0,
                            "supplier_match_matches_included": 0,
                            "supplier_match_suppliers_excluded": 0,
                            "supplier_match_market_profile": None,
                            "supplier_match_market_profile_version": None,
                            "supplier_match_source_file": None,
                            "supplier_matches_file": None,
                        }
                    )
                    log.error("Supplier match step error (non-fatal): %s", exc)
                else:
                    context.update(
                        {
                            "buyer_intel_status": "error",
                            "buyer_intel_accumulated": 0,
                            "buyer_intel_briefs": {},
                            "buyer_intel_briefs_attached": 0,
                        }
                    )
                    log.error("Buyer intel step error (non-fatal): %s", exc)
                continue
            duration = round(time.time() - step_start, 2)
            manifest["steps"][step_name] = {
                "status": "failed",
                "error": str(exc),
                "duration_s": duration,
            }
            manifest["status"] = "failed"
            manifest["failed_at_step"] = step_name
            manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
            manifest["total_duration_s"] = round(time.time() - start, 2)
            save_manifest(run_dir, manifest)
            log.error("Pipeline FAILED at step '%s': %s", step_name, exc)
            log.error("No notifications will be sent.")
            sys.exit(1)

    # --- Buyer watchlist (non-fatal, runs after buyer_timing) ---
    log.info("--- Step: buyer_watchlist ---")
    buyer_watchlist_start = time.time()
    try:
        from src.buyer_watchlist import build_and_write as _bw_build_and_write
        bw_result = _bw_build_and_write(run_dir=run_dir, state_dir=STATE_DIR)
        context.update(bw_result or {})
        manifest["steps"]["buyer_watchlist"] = {
            "status": "ok",
            "duration_s": round(time.time() - buyer_watchlist_start, 2),
            "buyer_count": bw_result.get("buyer_watchlist_count", 0),
            "hot": bw_result.get("buyer_watchlist_hot", 0),
            "warm": bw_result.get("buyer_watchlist_warm", 0),
        }
        log.info(
            "Step 'buyer_watchlist' OK in %.2fs — %d buyers (%d hot, %d warm)",
            time.time() - buyer_watchlist_start,
            bw_result.get("buyer_watchlist_count", 0),
            bw_result.get("buyer_watchlist_hot", 0),
            bw_result.get("buyer_watchlist_warm", 0),
        )
    except Exception as exc:
        manifest["steps"]["buyer_watchlist"] = {
            "status": "error",
            "error": str(exc),
            "duration_s": round(time.time() - buyer_watchlist_start, 2),
        }
        context.update({
            "buyer_watchlist_count": 0,
            "buyer_watchlist_status": "error",
        })
        log.warning("Buyer watchlist step error (non-fatal): %s", exc)

    log.info("--- Step: buyer_intel_attach ---")
    buyer_intel_attach_start = time.time()
    try:
        buyer_intel_module = import_module_fn("src.buyer_intel")
        attach_func = getattr(buyer_intel_module, "attach_briefs")
        attach_result = attach_func(context)
        context.update(attach_result or {})
        manifest["steps"]["buyer_intel_attach"] = {
            "status": "ok",
            "duration_s": round(time.time() - buyer_intel_attach_start, 2),
        }
        log.info("Step 'buyer_intel_attach' OK in %.2fs", time.time() - buyer_intel_attach_start)
    except Exception as exc:
        manifest["steps"]["buyer_intel_attach"] = {
            "status": "error",
            "error": str(exc),
            "duration_s": round(time.time() - buyer_intel_attach_start, 2),
        }
        context.update({"buyer_intel_briefs_attached": 0})
        log.warning("Buyer intel attach step error (non-fatal): %s", exc)

    # --- Product runner (non-fatal) ---
    log.info("--- Step: products ---")
    products_start = time.time()
    try:
        from src.product_runner import run_all_products as _run_all_products
        products_result = _run_all_products(run_dir)
        manifest["steps"]["products"] = {
            "status": products_result.get("status", "unknown"),
            "duration_s": round(time.time() - products_start, 2),
            "enabled_count": products_result.get("enabled_count", 0),
            "generated_count": products_result.get("generated_count", 0),
        }
        manifest["products"] = products_result
        log.info(
            "Step 'products' OK in %.2fs — %d products, %d generated",
            time.time() - products_start,
            products_result.get("enabled_count", 0),
            products_result.get("generated_count", 0),
        )
    except Exception as exc:
        manifest["steps"]["products"] = {
            "status": "error",
            "error": str(exc),
            "duration_s": round(time.time() - products_start, 2),
        }
        manifest["products"] = {
            "status": "error",
            "error": str(exc),
            "enabled_count": 0,
            "generated_count": 0,
            "outputs": {},
        }
        log.warning("Product runner step error (non-fatal): %s", exc)

    # --- Client runner (non-fatal) ---
    log.info("--- Step: clients ---")
    clients_start = time.time()
    try:
        from src.client_runner import run_clients as _run_clients
        clients_result = _run_clients(run_dir)
        manifest["steps"]["clients"] = {
            "status":          clients_result.get("status", "unknown"),
            "duration_s":      round(time.time() - clients_start, 2),
            "enabled_count":   clients_result.get("enabled_count", 0),
            "notified_count":  clients_result.get("notified_count", 0),
        }
        manifest["clients"] = clients_result
        log.info(
            "Step 'clients' OK in %.2fs — %d clients, %d notified",
            time.time() - clients_start,
            clients_result.get("enabled_count", 0),
            clients_result.get("notified_count", 0),
        )
    except Exception as exc:
        manifest["steps"]["clients"] = {
            "status":    "error",
            "error":     str(exc),
            "duration_s": round(time.time() - clients_start, 2),
        }
        manifest["clients"] = {
            "status": "error", "error": str(exc),
            "enabled_count": 0, "notified_count": 0, "outputs": {},
        }
        log.warning("Client runner step error (non-fatal): %s", exc)

    log.info("--- Step: notify ---")
    notify_start = time.time()
    try:
        notify_result = notifier_runner_fn(context, run_id)
        context.update(notify_result)
        channel_results = notify_result.get("notify_results", {})

        if channel_results and any(
            status.startswith("failed") or status.startswith("error")
            for status in channel_results.values()
        ):
            notify_status = "failed"
        elif channel_results and all(
            status.startswith("skipped") for status in channel_results.values()
        ):
            notify_status = "skipped"
        else:
            notify_status = "ok"

        manifest["steps"]["notify"] = {
            "status": notify_status,
            "duration_s": round(time.time() - notify_start, 2),
            "channels": channel_results,
        }
        if notify_status == "failed":
            log.error("Step 'notify' FAILED in %.2fs", time.time() - notify_start)
        elif notify_status == "skipped":
            log.info("Step 'notify' SKIPPED in %.2fs", time.time() - notify_start)
        else:
            log.info("Step 'notify' OK in %.2fs", time.time() - notify_start)
    except Exception as exc:
        manifest["steps"]["notify"] = {
            "status": "error",
            "error": str(exc),
        }
        log.error("Notify step error (non-fatal): %s", exc)

    # --- Outreach Queue (non-fatal) ---
    log.info("--- Step: outreach_queue ---")
    outreach_start = time.time()
    try:
        from src.outreach_queue import build_and_write as _oq_build
        oq_result = _oq_build(run_dir, STATE_DIR)
        context.update(oq_result)
        manifest["steps"]["outreach_queue"] = {
            "status": "ok",
            "duration_s": round(time.time() - outreach_start, 2),
            "count": oq_result.get("outreach_queue_count", 0),
            "hot":   oq_result.get("outreach_hot_count", 0),
        }
        log.info(
            "Step 'outreach_queue' OK in %.2fs — %d buyers (%d Hot)",
            time.time() - outreach_start,
            oq_result.get("outreach_queue_count", 0),
            oq_result.get("outreach_hot_count", 0),
        )
    except Exception as exc:
        manifest["steps"]["outreach_queue"] = {
            "status": "error",
            "error": str(exc),
            "duration_s": round(time.time() - outreach_start, 2),
        }
        log.warning("Outreach queue step error (non-fatal): %s", exc)

    # Save partial manifest so openclaw_sync can read it during the same run
    apply_manifest_fields(manifest, context, cleanup_stats)
    save_manifest(run_dir, manifest)

    # --- OpenClaw memory sync (non-fatal) ---
    log.info("--- Step: openclaw_sync ---")
    openclaw_start = time.time()
    try:
        import importlib.util as _ilu2
        sync_script = BASE_DIR / "scripts" / "sync_to_openclaw.py"
        if sync_script.exists():
            spec2 = _ilu2.spec_from_file_location("sync_to_openclaw", sync_script)
            sync_mod = _ilu2.module_from_spec(spec2)
            spec2.loader.exec_module(sync_mod)
            sync_result = sync_mod.sync_run(run_dir, buyers_only=False)
            manifest["steps"]["openclaw_sync"] = {
                "status": "ok",
                "duration_s": round(time.time() - openclaw_start, 2),
                "buyers_written": sync_result.get("buyers", 0),
            }
            log.info(
                "Step 'openclaw_sync' OK in %.2fs — %d buyer dossiers written",
                time.time() - openclaw_start,
                sync_result.get("buyers", 0),
            )
        else:
            manifest["steps"]["openclaw_sync"] = {
                "status": "skipped",
                "duration_s": 0,
                "detail": "sync_to_openclaw.py not found",
            }
    except Exception as exc:
        manifest["steps"]["openclaw_sync"] = {
            "status": "error",
            "error": str(exc),
            "duration_s": round(time.time() - openclaw_start, 2),
        }
        log.warning("OpenClaw sync step error (non-fatal): %s", exc)

    # --- Finalise manifest ---
    has_warnings = any(
        step.get("status") in ("error", "failed")
        for step in manifest["steps"].values()
    )
    shortlist_count = context.get("shortlist_count", 0)
    new_count = context.get("new_count", 0)

    if shortlist_count == 0 and new_count == 0:
        final_status = "success_empty" if not has_warnings else "success_with_warnings"
    elif has_warnings:
        final_status = "success_with_warnings"
    else:
        final_status = "success"

    manifest["status"] = final_status
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["total_duration_s"] = round(time.time() - start, 2)

    cleanup_stats_final = {"removed_files": cleanup_stats.get("removed_files", 0)}
    apply_manifest_fields(manifest, context, cleanup_stats_final)
    save_manifest(run_dir, manifest)

    # --- Dashboard bundle (non-fatal) ---
    # Build after the final manifest is saved so the bundle selects the current run,
    # not the previous successful one.
    log.info("--- Step: dashboard ---")
    dashboard_start = time.time()
    try:
        import importlib.util as _ilu
        bundle_script = BASE_DIR / "scripts" / "build_dashboard_bundle.py"
        if bundle_script.exists():
            spec = _ilu.spec_from_file_location("build_dashboard_bundle", bundle_script)
            bundle_mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(bundle_mod)
            bundle_mod.main()
            manifest["steps"]["dashboard"] = {
                "status": "ok",
                "duration_s": round(time.time() - dashboard_start, 2),
            }
            log.info("Step 'dashboard' OK in %.2fs — bundle refreshed", time.time() - dashboard_start)
        else:
            manifest["steps"]["dashboard"] = {
                "status": "skipped",
                "duration_s": 0,
                "detail": "build_dashboard_bundle.py not found",
            }
    except Exception as exc:
        manifest["steps"]["dashboard"] = {
            "status": "error",
            "error": str(exc),
            "duration_s": round(time.time() - dashboard_start, 2),
        }
        log.warning("Dashboard bundle step error (non-fatal): %s", exc)

    save_manifest(run_dir, manifest)

    log.info(
        "=== Pipeline complete in %.2fs  |  %d shortlisted  |  %d new  ===",
        manifest["total_duration_s"],
        shortlist_count,
        new_count,
    )


if __name__ == "__main__":
    run_pipeline()
