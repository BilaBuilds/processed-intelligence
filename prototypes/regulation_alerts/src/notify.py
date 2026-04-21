import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

MAX_DISCORD_ALERTS = 5


def _format_digest(run_id: str, all_alerts: List[dict], new_ids: set) -> str:
    new_count = sum(1 for a in all_alerts if a["id"] in new_ids)
    lines = [
        "=== OpenClaw Regs Alert ===",
        f"Run: {run_id}",
        f"Total alerts: {len(all_alerts)} ({new_count} new)",
        "",
    ]
    for i, alert in enumerate(all_alerts, 1):
        effective = alert.get("effective_at") or "TBC"
        reasons = ", ".join(alert.get("relevance_reasons", []))
        tag = "[NEW] " if alert["id"] in new_ids else "[SEEN] "
        lines += [
            f"{tag}[{i}] {alert['title']}",
            f"    Authority: {alert['authority']} | Region: {alert['region']} | Score: {alert['relevance_score']}",
            f"    Impact: {alert['impact_type']}",
            f"    Effective: {effective}",
            f"    URL: {alert['url']}",
            f"    Why: {reasons}",
            "",
        ]
    return "\n".join(lines)


def _send_discord(webhook_url: str, run_id: str, alerts: List[dict]) -> str:
    """Send up to MAX_DISCORD_ALERTS to Discord. Returns status string."""
    capped = alerts[:MAX_DISCORD_ALERTS]
    lines = [f"**OpenClaw Regs Alert** | Run: `{run_id}` | {len(alerts)} alert(s)"]
    for i, alert in enumerate(capped, 1):
        effective = alert.get("effective_at") or "TBC"
        lines.append(
            f"\n**[{i}] {alert['title'][:100]}**\n"
            f"Authority: {alert['authority']} | Region: {alert['region']} | Score: {alert['relevance_score']}\n"
            f"Impact: {alert['impact_type']} | Effective: {effective}\n"
            f"<{alert['url']}>"
        )
    if len(alerts) > MAX_DISCORD_ALERTS:
        lines.append(f"\n...and {len(alerts) - MAX_DISCORD_ALERTS} more. See full digest.")

    payload = {"content": "\n".join(lines)[:2000]}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return "sent"
    except Exception as e:
        logger.warning(f"[notify] Discord webhook failed: {e}")
        return "error"


def run_notify(
    run_id: str,
    client_results: Dict[str, dict],
    run_dir: Path,
    dry_run: bool = False,
) -> Dict[str, dict]:
    """
    Write alert digest and send Discord notifications.
    Updates client_results summaries with notify_status.
    Returns updated client_results.
    """
    # Collect all alerts across clients for the digest
    all_alerts: List[dict] = []
    digest_seen: set = set()
    all_new_ids: set = set()
    for cr in client_results.values():
        for item in cr["shortlist"]:
            if item["id"] not in digest_seen:
                digest_seen.add(item["id"])
                all_alerts.append(item)
        for item in cr.get("new_records", []):
            all_new_ids.add(item["id"])
    all_alerts.sort(key=lambda r: r["relevance_score"], reverse=True)

    digest = _format_digest(run_id, all_alerts, all_new_ids)

    if not dry_run:
        digest_path = run_dir / "alert_digest.txt"
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(digest_path, "w", encoding="utf-8") as f:
            f.write(digest)
        logger.info(f"[notify] digest written to {digest_path}")

    # Send per-client notifications
    for client_id, cr in client_results.items():
        notify_cfg = cr.get("notify_config", {})
        shortlist = cr["shortlist"]
        summary = cr["summary"]

        if not notify_cfg or not notify_cfg.get("channel"):
            summary["notify_status"] = "disabled"
            summary["notified"] = False
            continue

        new_count = summary.get("new_count", 0)
        if new_count == 0:
            summary["notify_status"] = "skipped"
            summary["notified"] = False
            continue

        new_records = cr.get("new_records", shortlist)
        channel = notify_cfg.get("channel", "")
        webhook_env_var = notify_cfg.get("webhook_env_var", "")
        webhook_url = os.environ.get(webhook_env_var, "") if webhook_env_var else ""

        if channel == "discord" and webhook_url and not dry_run:
            status = _send_discord(webhook_url, run_id, new_records)
            summary["notify_status"] = status
            summary["notified"] = status == "sent"
        elif dry_run:
            summary["notify_status"] = "skipped"
            summary["notified"] = False
        else:
            logger.info(
                f"[notify] client {client_id}: no webhook URL for {webhook_env_var} — skipping"
            )
            summary["notify_status"] = "skipped"
            summary["notified"] = False

        # Persist updated client_summary
        if not dry_run:
            client_summary_path = run_dir / "clients" / client_id / "client_summary.json"
            if client_summary_path.exists():
                with open(client_summary_path, "w") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=True)

    return client_results
