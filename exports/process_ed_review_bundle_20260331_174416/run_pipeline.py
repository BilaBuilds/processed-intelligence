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
    TENDER_DECISION_INCLUDE - Which verdicts pass downstream (default BID,REVIEW)
    TENDER_RAW_RETENTION_DAYS - Days to keep heavy JSONL run artifacts (default 7)
    TENDER_BASE_DIR      - Base dir override (default: this folder)

Each step is a separate module in /src.
If any core step fails, the run is marked failed and no notifications are sent.
Notifier failures are logged but do NOT fail the run.
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

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
CONFIG_DIR = BASE_DIR / "config"

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

    if not RUNS_DIR.exists():
        return {"removed_files": 0}

    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        for name in HEAVY_RUN_ARTIFACTS:
            candidate = run_dir / name
            if not candidate.exists():
                continue
            modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            if modified < cutoff:
                candidate.unlink(missing_ok=True)
                removed_files += 1

    return {"removed_files": removed_files}


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
        return {"notify_results": results}

    with open(deduped_file, encoding="utf-8") as f:
        data = json.load(f)
    opportunities = data.get("opportunities", [])

    if not opportunities:
        log.info("No new opportunities - nothing to notify.")
        for notifier in notifiers:
            results[notifier.name] = "skipped (nothing new)"
        return {"notify_results": results}

    for notifier in notifiers:
        try:
            success = notifier.send(opportunities, run_id)
            results[notifier.name] = "ok" if success else "failed"
        except ValueError as exc:
            log.error("Notifier '%s' config error: %s", notifier.name, exc)
            results[notifier.name] = f"error: {exc}"
        except Exception as exc:
            log.error("Notifier '%s' raised an exception: %s", notifier.name, exc)
            results[notifier.name] = f"error: {exc}"

    return {"notify_results": results}


def run_pipeline() -> None:
    start = time.time()
    load_env_defaults()

    cleanup_stats = cleanup_old_run_artifacts()
    if cleanup_stats["removed_files"] > 0:
        log.info("Cleanup removed %d old run artifact file(s).", cleanup_stats["removed_files"])

    run_dir = make_run_dir()
    run_id = run_dir.name
    log.info("=== Tender Engine starting  |  run: %s ===", run_id)

    manifest = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "steps": {},
    }

    steps = [
        ("ingest", "src.ingest", "run"),
        ("normalize", "src.normalize", "run"),
        ("match", "src.match", "run"),
        ("select", "src.select", "run"),
        ("decision", "src.decision", "run"),
        ("dedupe", "src.dedupe", "run"),
    ]

    context = {"run_dir": run_dir}

    for step_name, module_path, func_name in steps:
        log.info("--- Step: %s ---", step_name)
        step_start = time.time()
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            result = func(context)
            context.update(result or {})

            duration = round(time.time() - step_start, 2)
            manifest["steps"][step_name] = {"status": "ok", "duration_s": duration}
            log.info("Step '%s' OK in %.2fs", step_name, duration)

        except Exception as exc:
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

    log.info("--- Step: notify ---")
    notify_start = time.time()
    try:
        notify_result = run_notifiers(context, run_id)
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

    manifest["status"] = "success"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["total_duration_s"] = round(time.time() - start, 2)
    manifest["shortlist_count"] = context.get("shortlist_count", 0)
    manifest["new_count"] = context.get("new_count", 0)
    manifest["source_health"] = context.get("source_health", {})
    manifest["decision_total_count"] = context.get("decision_total_count", 0)
    manifest["decision_pass_count"] = context.get("decision_pass_count", 0)
    manifest["decision_verdict_counts"] = context.get("decision_verdict_counts", {})
    manifest["cleanup"] = cleanup_stats
    save_manifest(run_dir, manifest)

    log.info(
        "=== Pipeline complete in %.2fs  |  %d shortlisted  |  %d new  ===",
        manifest["total_duration_s"],
        manifest["shortlist_count"],
        manifest["new_count"],
    )


if __name__ == "__main__":
    run_pipeline()
