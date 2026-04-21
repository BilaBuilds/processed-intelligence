"""
src/client_runner.py
====================
Client Layer — per-client filtered views of product outputs.

A client subscribes to one or more product IDs and optionally applies
additional filters on top. Each client receives its own shortlist artifact
and Discord notification.

Design:
  - reads from product artifacts only (never re-runs pipeline steps)
  - per-client failures are isolated — one bad config/webhook never blocks others
  - deterministic: same inputs always produce same shortlist
  - Discord sends per-client, not globally

Manifest semantics:
  - "ok"         — clients ran (even if all shortlists are empty)
  - "skipped"    — step was skipped (no products ran, etc.)
  - "error"      — runner itself failed fatally
  - "no_clients" — no active client configs found

Per-client status:
  - "ok"    — produced >= 1 item
  - "empty" — ran cleanly but 0 items passed filters
  - "error" — client-level exception

notify_status:
  - "sent"     — Discord POST succeeded
  - "skipped"  — new_count == 0
  - "error"    — webhook env var missing or POST failed
  - "disabled" — notify.channel != "discord" or notify block absent
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import re

log = logging.getLogger("client_runner")

CLIENTS_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "clients"
STATE_DIR = Path(__file__).resolve().parent.parent / "state"
CLIENT_SEEN_DIRNAME = "client_seen"

_VALID_WEBHOOK_HOSTS = {"discord.com", "ptb.discord.com", "canary.discord.com"}
_WEBHOOK_PATH_RE = re.compile(r"^/api/webhooks/\d+/[A-Za-z0-9._-]+/?$")
_DISCORD_MAX_TENDERS = 10


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_REQUIRED_CLIENT_FIELDS = {"client_id", "display_name", "active", "subscribed_products", "notify"}


def load_client_config(path: Path) -> dict[str, Any]:
    """Load and validate a client config. Raises ValueError on bad config."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    missing = _REQUIRED_CLIENT_FIELDS - raw.keys()
    if missing:
        raise ValueError(f"Client config {path.name} missing fields: {sorted(missing)}")
    if not isinstance(raw["client_id"], str) or not raw["client_id"]:
        raise ValueError(f"Client config {path.name}: 'client_id' must be non-empty string")
    if not isinstance(raw["subscribed_products"], list):
        raise ValueError(f"Client config {path.name}: 'subscribed_products' must be a list")
    if not isinstance(raw["notify"], dict):
        raise ValueError(f"Client config {path.name}: 'notify' must be a dict")
    return raw


def discover_client_configs(config_dir: Path = CLIENTS_CONFIG_DIR) -> list[dict[str, Any]]:
    """Load all active client configs. Invalid configs are skipped with a warning."""
    configs: list[dict[str, Any]] = []
    if not config_dir.exists():
        log.warning("Clients config dir not found: %s", config_dir)
        return configs
    for path in sorted(config_dir.glob("*.json")):
        try:
            cfg = load_client_config(path)
            if cfg.get("active"):
                configs.append(cfg)
            else:
                log.debug("Skipped inactive client: %s", path.name)
        except Exception as exc:
            log.error("Invalid client config %s — skipping: %s", path.name, exc)
    log.info("Discovered %d active client configs", len(configs))
    return configs


# ---------------------------------------------------------------------------
# Product shortlist loader
# ---------------------------------------------------------------------------

def load_product_shortlist(run_dir: Path, product_id: str) -> list[dict]:
    path = run_dir / "products" / product_id / "product_shortlist.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        log.warning("Could not load product shortlist for %s: %s", product_id, exc)
        return []


# ---------------------------------------------------------------------------
# Client-level filters
# ---------------------------------------------------------------------------

def _notice_id(tender: dict) -> str:
    return str(
        tender.get("id") or
        tender.get("opportunity_id") or
        tender.get("source_notice_id") or
        tender.get("ocid") or
        tender.get("raw_id") or
        ""
    )


def apply_client_filters(tenders: list[dict], filters: dict) -> list[dict]:
    """
    Apply client-level filters on top of already-product-filtered tenders.
    Filters:
      min_score       — base score >= threshold (0 = all pass)
      regions         — region in list (empty = all pass)
      buyer_whitelist — buyer_name contains at least one substring (empty = all pass)
    """
    current = list(tenders)

    min_score = filters.get("min_score") or 0
    if min_score:
        current = [t for t in current if (t.get("score") or 0) >= min_score]

    regions = [r.lower() for r in (filters.get("regions") or [])]
    if regions:
        current = [t for t in current if (t.get("region") or "").lower() in regions]

    buyer_whitelist = [b.lower() for b in (filters.get("buyer_whitelist") or [])]
    if buyer_whitelist:
        current = [
            t for t in current
            if any(
                bw in (t.get("buyer_name") or t.get("buyer") or "").lower()
                for bw in buyer_whitelist
            )
        ]

    return current


def merge_and_deduplicate(tenders_by_product: dict[str, list[dict]]) -> list[dict]:
    """
    Merge tenders from multiple products, deduplicating by notice ID.
    First occurrence wins (product iteration order = config order).
    Items without an ID are included once each.
    """
    seen: set[str] = set()
    merged: list[dict] = []
    no_id_index = 0
    for product_id, tenders in tenders_by_product.items():
        for t in tenders:
            nid = _notice_id(t)
            key = nid if nid else f"__no_id_{no_id_index}"
            if not nid:
                no_id_index += 1
            if key not in seen:
                seen.add(key)
                record = dict(t)
                record.setdefault("product_id", product_id)
                merged.append(record)
    # Sort by product_rank desc, then base score desc
    merged.sort(key=lambda t: (-(t.get("product_rank") or t.get("score") or 0),))
    return merged


def _default_state_dir(run_dir: Path) -> Path:
    try:
        return run_dir.parent.parent.parent / "state"
    except Exception:
        return STATE_DIR


def _seen_ledger_path(state_dir: Path, client_id: str) -> Path:
    return state_dir / CLIENT_SEEN_DIRNAME / f"{client_id}.jsonl"


def _load_seen_ledger(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    if not path.exists():
        return [], set()

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("Could not decode client seen ledger line in %s: %s", path, exc)
            continue
        notice_id = str(row.get("notice_id") or "").strip()
        if not notice_id or notice_id in seen_ids:
            continue
        rows.append(row)
        seen_ids.add(notice_id)
    return rows, seen_ids


def _atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    content = "".join(
        json.dumps(row, ensure_ascii=False, default=str) + "\n"
        for row in rows
    )
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def _mark_new_tenders(
    shortlist: list[dict],
    *,
    client_id: str,
    run_id: str,
    generated_at: str,
    state_dir: Path,
) -> tuple[list[dict], list[dict]]:
    """
    Mark tenders as new based on a per-client seen ledger.

    Returns (annotated_shortlist, new_tenders). Ledger writes are non-fatal:
    if the write fails, new_tenders still reflects the current run's novelty
    calculation and the pipeline continues.
    """
    ledger_path = _seen_ledger_path(state_dir, client_id)
    existing_rows, seen_ids = _load_seen_ledger(ledger_path)

    annotated: list[dict] = []
    new_tenders: list[dict] = []
    appended_rows: list[dict[str, Any]] = []

    for tender in shortlist:
        record = dict(tender)
        notice_id = _notice_id(record).strip()
        is_new = False

        if notice_id:
            if notice_id not in seen_ids:
                is_new = True
                seen_ids.add(notice_id)
                appended_rows.append(
                    {
                        "notice_id": notice_id,
                        "first_seen_run": run_id,
                        "first_seen_at": generated_at,
                    }
                )
        else:
            log.debug(
                "Client '%s': tender '%s' missing notice_id; novelty not persisted",
                client_id,
                record.get("title") or "untitled",
            )

        record["is_new"] = is_new
        annotated.append(record)
        if is_new:
            new_tenders.append(record)

    if appended_rows:
        try:
            _atomic_write_jsonl(ledger_path, existing_rows + appended_rows)
        except Exception as exc:
            log.warning("Client '%s': could not update seen ledger %s: %s", client_id, ledger_path, exc)

    return annotated, new_tenders


# ---------------------------------------------------------------------------
# Discord notification
# ---------------------------------------------------------------------------

def _validate_webhook(url: str) -> None:
    if not url:
        raise ValueError("Webhook URL is empty")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use https")
    if parsed.netloc.lower() not in _VALID_WEBHOOK_HOSTS:
        raise ValueError(f"Webhook URL host not allowed: {parsed.netloc}")
    if not _WEBHOOK_PATH_RE.match(parsed.path):
        raise ValueError("Webhook URL path does not match Discord webhook pattern")


def _format_value(tender: dict) -> str:
    v = tender.get("value_amount")
    if v is None:
        return "TBC"
    try:
        n = float(v)
        if n >= 1_000_000:
            return f"£{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"£{n/1_000:.0f}k"
        return f"£{n:.0f}"
    except (TypeError, ValueError):
        return "TBC"


def _build_discord_message(client: dict, run_id: str, tenders: list[dict]) -> str:
    display = client.get("display_name", client.get("client_id", "Client"))
    lines = [
        f"**ProcessEd – {display}**",
        f"Run: `{run_id}`",
        f"New tenders: **{len(tenders)}**",
        "",
    ]
    shown = tenders[:_DISCORD_MAX_TENDERS]
    for t in shown:
        title = (t.get("title") or "Untitled")[:80]
        buyer = t.get("buyer_name") or t.get("buyer") or "Unknown buyer"
        value = _format_value(t)
        score = t.get("score") or 0
        lines.append(f"• {title} — {buyer} — {value} — Score: {score}")
    if len(tenders) > _DISCORD_MAX_TENDERS:
        lines.append(f"_…and {len(tenders) - _DISCORD_MAX_TENDERS} more (see full report)_")
    return "\n".join(lines)


def send_discord_notification(
    client: dict,
    run_id: str,
    tenders: list[dict],
    *,
    _requests_post=None,  # injectable for testing
) -> str:
    """
    Send Discord notification for a client.
    Returns notify_status: "sent" | "skipped" | "error" | "disabled"
    """
    notify_cfg = client.get("notify") or {}
    channel = notify_cfg.get("channel", "")
    if channel != "discord":
        return "disabled"

    if not tenders:
        return "skipped"

    env_var = notify_cfg.get("webhook_env_var", "TENDER_WEBHOOK_URL")
    webhook_url = os.getenv(env_var, "").strip()
    try:
        _validate_webhook(webhook_url)
    except ValueError as exc:
        log.warning(
            "Client '%s': webhook env var %s not set or invalid — skipping notify: %s",
            client.get("client_id"), env_var, exc,
        )
        return "error"

    message = _build_discord_message(client, run_id, tenders)
    payload = {"content": message}

    if _requests_post is not None:
        # Test injection
        try:
            resp = _requests_post(webhook_url, json=payload, timeout=10)
            if 200 <= resp.status_code < 300:
                return "sent"
            log.warning("Client '%s': Discord returned %d", client.get("client_id"), resp.status_code)
            return "error"
        except Exception as exc:
            log.warning("Client '%s': Discord POST failed: %s", client.get("client_id"), exc)
            return "error"

    try:
        import requests
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if 200 <= resp.status_code < 300:
            log.info("Client '%s': Discord notification sent", client.get("client_id"))
            return "sent"
        log.warning(
            "Client '%s': Discord returned %d", client.get("client_id"), resp.status_code
        )
        return "error"
    except Exception as exc:
        log.warning("Client '%s': Discord POST failed: %s", client.get("client_id"), exc)
        return "error"


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

def _top_values(records: list[dict], field: str, limit: int = 5) -> list[str]:
    """Return top-N non-empty distinct values of a field, by frequency."""
    from collections import Counter
    counts: Counter = Counter()
    for r in records:
        v = (r.get(field) or "").strip()
        if v:
            counts[v] += 1
    return [v for v, _ in counts.most_common(limit)]


def _write_client_artifacts(
    output_dir: Path,
    client: dict,
    run_id: str,
    shortlist: list[dict],
    notify_status: str,
    generated_at: str,
    new_tenders: list[dict] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    new_tenders = shortlist if new_tenders is None else new_tenders

    (output_dir / "client_shortlist.json").write_text(
        json.dumps(
            {
                "tenders": shortlist,
                "new_tenders": new_tenders,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    # Deterministic enrichment from shortlist contents
    top_buyers = _top_values(shortlist, "buyer_name", limit=5)
    top_regions = _top_values(shortlist, "region", limit=3)
    scores = [t.get("score") or t.get("product_rank") for t in shortlist if t.get("score") or t.get("product_rank")]
    score_range = {"min": min(scores), "max": max(scores)} if scores else None

    summary = {
        "client_id":           client["client_id"],
        "display_name":        client.get("display_name", client["client_id"]),
        "run_id":              run_id,
        "generated_at":        generated_at,
        "subscribed_products": client.get("subscribed_products", []),
        "item_count":          len(shortlist),
        "new_count":           len(new_tenders),
        "notified":            notify_status == "sent",
        "notify_status":       notify_status,
        "top_buyers":          top_buyers,
        "top_regions":         top_regions,
        "score_range":         score_range,
    }
    (output_dir / "client_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Per-client runner
# ---------------------------------------------------------------------------

def run_client(
    client: dict,
    run_dir: Path,
    run_id: str,
    generated_at: str,
    *,
    _requests_post=None,
) -> dict[str, Any]:
    """
    Run one client: load product outputs, apply filters, write artifacts, notify.
    Returns manifest entry dict.
    """
    client_id = client["client_id"]
    subscribed = client.get("subscribed_products") or []
    filters = client.get("filters") or {}

    # Load and merge product shortlists
    tenders_by_product: dict[str, list[dict]] = {}
    for product_id in subscribed:
        raw = load_product_shortlist(run_dir, product_id)
        filtered = apply_client_filters(raw, filters)
        tenders_by_product[product_id] = filtered
        log.debug(
            "Client '%s' / product '%s': %d items after client filters",
            client_id, product_id, len(filtered),
        )

    shortlist = merge_and_deduplicate(tenders_by_product)
    state_dir = _default_state_dir(run_dir)
    shortlist, new_tenders = _mark_new_tenders(
        shortlist,
        client_id=client_id,
        run_id=run_id,
        generated_at=generated_at,
        state_dir=state_dir,
    )
    log.info("Client '%s': %d items in merged shortlist", client_id, len(shortlist))

    # Notify
    notify_status = send_discord_notification(
        client, run_id, new_tenders, _requests_post=_requests_post,
    )

    # Write artifacts
    output_dir = run_dir / "clients" / client_id
    _write_client_artifacts(
        output_dir,
        client,
        run_id,
        shortlist,
        notify_status,
        generated_at,
        new_tenders=new_tenders,
    )

    status = "ok" if shortlist else "empty"
    return {
        "status":        status,
        "item_count":    len(shortlist),
        "new_count":     len(new_tenders),
        "notified":      notify_status == "sent",
        "notify_status": notify_status,
    }


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_clients(
    run_dir: Path,
    config_dir: Path = CLIENTS_CONFIG_DIR,
    *,
    _requests_post=None,
) -> dict[str, Any]:
    """
    Discover all active client configs and run each.
    Returns manifest-ready dict.
    """
    run_id = run_dir.name
    generated_at = datetime.now(timezone.utc).isoformat()

    configs = discover_client_configs(config_dir)
    if not configs:
        return {
            "status":          "no_clients",
            "enabled_count":   0,
            "notified_count":  0,
            "outputs":         {},
        }

    outputs: dict[str, dict] = {}
    notified_count = 0

    for cfg in configs:
        client_id = cfg["client_id"]
        try:
            result = run_client(
                cfg, run_dir, run_id, generated_at, _requests_post=_requests_post,
            )
            outputs[client_id] = result
            if result.get("notified"):
                notified_count += 1
        except Exception as exc:
            log.error("Client '%s' failed (skipping): %s", client_id, exc)
            outputs[client_id] = {
                "status":        "error",
                "error":         str(exc),
                "item_count":    0,
                "new_count":     0,
                "notified":      False,
                "notify_status": "error",
            }

    has_error = any(v.get("status") == "error" for v in outputs.values())
    overall = "error" if has_error else "ok"

    return {
        "status":         overall,
        "enabled_count":  len(configs),
        "notified_count": notified_count,
        "outputs":        outputs,
    }
