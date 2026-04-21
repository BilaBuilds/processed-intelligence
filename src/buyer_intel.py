"""
src/buyer_intel.py
==================
Step 3c - Buyer Intelligence Layer

Two jobs:
    1. ACCUMULATE — every tender that passes context.py gets logged to
       state/buyer_history.jsonl (buyer name, value, CPV, deadline, date seen).

    2. SYNTHESISE — for each buyer in the current shortlist, query
       Gemini Flash (free tier) to produce a structured intelligence brief:
           - procurement frequency
           - typical value band
           - geographic preference
           - competitiveness signal
           - what they consistently favour

Briefs are cached in state/buyer_briefs.json (keyed by buyer name, lower).
Cache TTL: 7 days (re-synthesise weekly as new data accumulates).

Output added to context:
    buyer_intel_accumulated  - int, tenders logged this run
    buyer_intel_briefs       - dict, buyer_name -> brief text
    buyer_intel_file         - Path to buyer_history.jsonl
    buyer_intel_status       - "ok" | "no_api_key" | "error"

Gemini calls are best-effort — any failure is logged and skipped,
pipeline never fails due to this step.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("buyer_intel")

CACHE_TTL_DAYS = 7
GEMINI_MODEL = "gemini-2.0-flash-lite"  # cheapest / fastest; free tier sufficient
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
MAX_HISTORY_PER_BUYER = 20   # cap how many past records we send to Gemini
RATE_LIMIT_SLEEP = 1.0       # seconds between Gemini calls (free tier: 10 RPM)


# ---------------------------------------------------------------------------
# Accumulator
# ---------------------------------------------------------------------------

def _accumulate(tenders: list[dict], buyer_history_file: Path) -> int:
    """Append new tender records to buyer_history.jsonl. Returns count appended."""
    if not tenders:
        return 0

    appended = 0
    with open(buyer_history_file, "a", encoding="utf-8") as f:
        for t in tenders:
            buyer = t.get("buyer_name") or t.get("buyer") or ""
            if not buyer:
                continue
            record = {
                "buyer_name": buyer,
                "title": t.get("title") or "",
                "value_amount": t.get("value_amount") or t.get("value"),
                "value_currency": t.get("value_currency", "GBP"),
                "region": t.get("region") or "",
                "cpv_codes": t.get("cpv_codes") or [],
                "deadline_at": t.get("deadline_at") or t.get("deadline") or "",
                "score": t.get("score", 0),
                "decision_verdict": t.get("decision_verdict", ""),
                "source": t.get("source") or t.get("source_id") or "",
                "notice_published_at": (
                    t.get("published_at")
                    or t.get("publication_date")
                    or t.get("updated_at")
                    or ""
                ),
                "seen_at": (
                    t.get("published_at")
                    or t.get("publication_date")
                    or t.get("updated_at")
                    or datetime.now(timezone.utc).isoformat()
                ),
            }
            f.write(json.dumps(record, default=str) + "\n")
            appended += 1

    return appended


# ---------------------------------------------------------------------------
# History loader
# ---------------------------------------------------------------------------

def _load_buyer_history(buyer_history_file: Path) -> dict[str, list[dict]]:
    """Load buyer_history.jsonl grouped by buyer name (lowercased)."""
    grouped: dict[str, list[dict]] = {}
    if not buyer_history_file.exists():
        return grouped

    with open(buyer_history_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                key = (rec.get("buyer_name") or "").lower().strip()
                if not key:
                    continue
                grouped.setdefault(key, []).append(rec)
            except Exception as exc:
                log.warning("Skipping malformed buyer history record: %s", exc)
                continue

    return grouped


def _load_shortlist_opportunities(shortlist_file: Path) -> list[dict]:
    """
    Load shortlisted opportunities from the canonical shortlist payload.

    Canonical key is "opportunities". Older runs may still contain "tenders",
    so we accept that as a backward-compatible fallback.
    """
    if not shortlist_file.exists():
        return []
    with open(shortlist_file, encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    opportunities = payload.get("opportunities")
    if isinstance(opportunities, list):
        return opportunities
    legacy = payload.get("tenders")
    if isinstance(legacy, list):
        return legacy
    return []


def _load_briefs_cache(buyer_briefs_file: Path) -> dict[str, Any]:
    if not buyer_briefs_file.exists():
        return {}
    try:
        loaded = json.loads(buyer_briefs_file.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _brief_texts_from_cache(briefs_cache: dict[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for key, value in briefs_cache.items():
        if isinstance(value, dict):
            brief = str(value.get("brief") or "").strip()
        else:
            brief = str(value or "").strip()
        if brief:
            texts[str(key).strip().lower()] = brief
    return texts


def _build_buyer_summary_fields(buyer_key: str, history: dict[str, list[dict]], briefs_cache: dict) -> dict:
    """
    Build structured buyer intel fields from cached briefs and raw history.
    Returns a dict of fields to merge into each tender record.
    Never fabricates — returns empty dict if nothing useful is available.
    """
    result: dict[str, Any] = {}
    if not buyer_key:
        return result

    # Brief text (Gemini-synthesised or absent)
    cached = briefs_cache.get(buyer_key, {})
    if isinstance(cached, dict):
        brief = str(cached.get("brief") or "").strip()
    else:
        brief = str(cached or "").strip()
    if brief:
        result["buyer_intel_summary"] = brief

    # History-derived structured fields
    records = history.get(buyer_key, [])
    if not records:
        return result

    # Procurement pattern (most common CPV category from history)
    from collections import Counter
    all_cpv: list[str] = []
    values: list[float] = []
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    recent_count = 0

    for rec in records:
        cpv = rec.get("cpv_codes") or []
        if isinstance(cpv, list):
            all_cpv.extend(cpv)
        try:
            v = float(rec.get("value_amount") or rec.get("value") or 0)
            if v > 0:
                values.append(v)
        except (TypeError, ValueError):
            pass
        # Recent activity
        try:
            seen = rec.get("seen_at") or ""
            if seen:
                dt = datetime.fromisoformat(seen)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= recent_cutoff:
                    recent_count += 1
        except (ValueError, TypeError):
            pass

    if all_cpv:
        top_cpv = Counter(all_cpv).most_common(3)
        result["buyer_category_bias"] = [c for c, _ in top_cpv]

    if values:
        avg_val = sum(values) / len(values)
        result["buyer_avg_value"] = int(avg_val)

    result["buyer_activity_90d"] = recent_count

    # Pattern string for notify embed
    parts = []
    if all_cpv:
        top_cat = Counter(all_cpv).most_common(1)[0][0]
        parts.append(f"recurring {top_cat} packages")
    if values:
        avg_k = int(sum(values) / len(values) / 1000)
        parts.append(f"~£{avg_k}k avg")
    if parts:
        result["buyer_pattern"] = ", ".join(parts)

    return result


def attach_briefs_to_artifact(
    target_file: Path,
    briefs_cache: dict[str, Any],
    history: dict[str, list[dict]] | None = None,
) -> int:
    """
    Attach cached buyer-intel briefs + structured fields to the artifact
    that feeds notify AND dashboard consumers.

    Fields injected per tender:
      buyer_intel_summary   - Gemini brief text (if available)
      buyer_pattern         - compact pattern string for notify embeds
      buyer_activity_90d    - notice count in last 90d
      buyer_avg_value       - mean contract value from history
      buyer_category_bias   - top CPV codes list

    Returns the number of records enriched.
    """
    if not target_file.exists():
        return 0

    try:
        payload = json.loads(target_file.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not load target file for buyer brief attachment: %s", exc)
        return 0

    if isinstance(payload, list):
        opportunities = payload
        container = None
    elif isinstance(payload, dict):
        if isinstance(payload.get("opportunities"), list):
            opportunities = payload["opportunities"]
            container = "opportunities"
        elif isinstance(payload.get("tenders"), list):
            opportunities = payload["tenders"]
            container = "tenders"
        else:
            opportunities = []
            container = None
    else:
        opportunities = []
        container = None

    if not opportunities:
        return 0

    hist = history or {}
    attached = 0
    for opp in opportunities:
        buyer_key = (opp.get("buyer_name") or opp.get("buyer") or "").lower().strip()
        if not buyer_key:
            continue
        fields = _build_buyer_summary_fields(buyer_key, hist, briefs_cache)
        if fields:
            opp.update(fields)
            attached += 1

    if attached == 0:
        return 0

    try:
        if container is None:
            updated = opportunities
        else:
            payload[container] = opportunities
            updated = payload
        target_file.write_text(json.dumps(updated, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        log.warning("Could not write buyer brief attachment target: %s", exc)
        return 0

    return attached


def attach_briefs(context: dict) -> dict[str, Any]:
    """
    Post-dedupe enrichment step.

    Runs after dedupe so the real delivery artifact (`new_tenders.json`) carries
    buyer-intel fields into notify and downstream dashboard consumers.

    Injects per tender: buyer_intel_summary, buyer_pattern, buyer_activity_90d,
    buyer_avg_value, buyer_category_bias.
    """
    state_dir: Path = context.get("state_dir", Path("state"))
    buyer_briefs_file = state_dir / "buyer_briefs.json"
    buyer_history_file = state_dir / "buyer_history.jsonl"

    briefs_cache = _load_briefs_cache(buyer_briefs_file)
    history = _load_buyer_history(buyer_history_file)

    deduped_file = context.get("deduped_file")
    attached = 0
    if deduped_file:
        attached = attach_briefs_to_artifact(Path(deduped_file), briefs_cache, history)
        if attached:
            log.info("Buyer intel: attached enrichment to %d opportunity record(s)", attached)
        else:
            log.debug("Buyer intel: no enrichment attached (no matching briefs/history)")

    return {
        "buyer_intel_briefs_attached": attached,
        "buyer_intel_brief_cache_file": str(buyer_briefs_file),
    }


# ---------------------------------------------------------------------------
# Gemini synthesis
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, api_key: str) -> str:
    """Call Gemini API and return text response. Raises on failure."""
    try:
        import urllib.request
        import urllib.error

        url = f"{GEMINI_ENDPOINT}?key={api_key}"
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 400,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        candidates = result.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        return " ".join(p.get("text", "") for p in parts).strip()

    except Exception as exc:
        raise RuntimeError(f"Gemini call failed: {exc}") from exc


def _build_prompt(buyer_name: str, records: list[dict]) -> str:
    """Build a concise prompt for buyer intelligence synthesis."""
    # Summarise records into a compact table
    lines = []
    for r in records[-MAX_HISTORY_PER_BUYER:]:
        value = r.get("value_amount")
        value_str = f"£{int(float(value)):,}" if value else "unknown"
        lines.append(
            f"- {r.get('title', 'untitled')} | {value_str} | "
            f"{r.get('region', 'unknown region')} | "
            f"seen {r.get('seen_at', '')[:10]}"
        )

    history_block = "\n".join(lines) if lines else "No history available."
    count = len(records)

    return f"""You are a UK public procurement intelligence analyst.

Buyer: {buyer_name}
Total tenders on record: {count}

Tender history (most recent first):
{history_block}

Write a concise buyer intelligence brief (max 5 bullet points) covering:
- Procurement frequency and pattern
- Typical contract value range
- Geographic preference if visible
- Types of work they consistently commission
- How competitive their awards appear (e.g. open/restricted/framework)

Be factual, brief, and useful for a contractor deciding whether to bid.
Do not invent data not present in the history above."""


def _synthesise_briefs(
    buyers_to_brief: list[str],
    history: dict[str, list[dict]],
    briefs_cache: dict[str, Any],
    api_key: str,
) -> dict[str, str]:
    """
    For each buyer, check cache TTL. If stale/missing, call Gemini.
    Returns updated briefs dict (buyer_lower -> brief text).
    """
    now = datetime.now(timezone.utc)
    ttl_cutoff = now - timedelta(days=CACHE_TTL_DAYS)
    updated: dict[str, str] = {}

    for buyer_name in buyers_to_brief:
        key = buyer_name.lower().strip()
        records = history.get(key, [])
        if len(records) < 2:
            # Not enough history to synthesise — skip
            log.debug("Buyer '%s': only %d record(s), skipping synthesis", buyer_name, len(records))
            continue

        # Check cache
        cached = briefs_cache.get(key, {})
        cached_at_str = cached.get("synthesised_at", "")
        if cached_at_str:
            try:
                cached_at = datetime.fromisoformat(cached_at_str)
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                if cached_at > ttl_cutoff:
                    # Cache still fresh
                    updated[key] = cached.get("brief", "")
                    log.debug("Buyer '%s': using cached brief (age < %dd)", buyer_name, CACHE_TTL_DAYS)
                    continue
            except Exception as exc:
                log.warning("Buyer '%s': cache age check failed (%s) — will re-synthesise", buyer_name, exc)

        # Synthesise via Gemini
        log.info("Buyer '%s': synthesising intelligence brief (%d records)...", buyer_name, len(records))
        try:
            prompt = _build_prompt(buyer_name, records)
            brief = _call_gemini(prompt, api_key)
            updated[key] = brief
            briefs_cache[key] = {
                "buyer_name": buyer_name,
                "brief": brief,
                "record_count": len(records),
                "synthesised_at": now.isoformat(),
            }
            log.info("Buyer '%s': brief synthesised (%d chars)", buyer_name, len(brief))
            time.sleep(RATE_LIMIT_SLEEP)  # respect free tier rate limit
        except Exception as exc:
            log.warning("Buyer '%s': synthesis failed — %s", buyer_name, exc)

    return updated


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run(context: dict) -> dict:
    """
    Pipeline step: accumulate buyer history + synthesise briefs for shortlisted buyers.

    Input:  context["context_file"]   (from context.py, has all augmented tenders)
            context["shortlist_file"]  (from select.py, has shortlisted tenders)
    Output: context updated with buyer_intel_* keys
    """
    state_dir: Path = context.get("state_dir", Path("state"))
    state_dir.mkdir(parents=True, exist_ok=True)

    buyer_history_file = state_dir / "buyer_history.jsonl"
    buyer_briefs_file = state_dir / "buyer_briefs.json"

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    # --- Load all context tenders for accumulation ---
    context_file: Path = context.get("context_file")
    all_tenders: list[dict] = []
    if context_file and Path(context_file).exists():
        with open(context_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_tenders.append(json.loads(line))
                    except Exception as exc:
                        log.warning("Skipping malformed tender record in buyer intel: %s", exc)

    # --- Accumulate buyer history from all context tenders ---
    accumulated = _accumulate(all_tenders, buyer_history_file)
    log.info("Buyer intel: accumulated %d tender record(s)", accumulated)

    # --- Load buyer history for unique-buyer count ---
    history = _load_buyer_history(buyer_history_file)
    unique_buyers = len(history)

    # --- Load briefs cache ---
    briefs_cache = _load_briefs_cache(buyer_briefs_file)

    # --- Load shortlisted buyers ---
    shortlist_file: Path | None = context.get("shortlist_file")
    if not shortlist_file:
        run_dir: Path = context.get("run_dir", Path("."))
        shortlist_file = run_dir / "shortlist.json"

    shortlisted = _load_shortlist_opportunities(Path(shortlist_file) if shortlist_file else Path("."))
    buyers_to_brief = list({
        (opp.get("buyer_name") or opp.get("buyer") or "").strip()
        for opp in shortlisted
        if (opp.get("buyer_name") or opp.get("buyer") or "").strip()
    })

    if not api_key:
        log.info("Buyer intel: no GEMINI_API_KEY — skipping synthesis")
        status = "ok_no_api_key" if accumulated else "ok_no_shortlist"
        briefs: dict[str, str] = _brief_texts_from_cache(briefs_cache)
    elif not buyers_to_brief:
        log.info("Buyer intel: no shortlisted buyers — skipping synthesis")
        status = "ok_no_shortlist"
        briefs = _brief_texts_from_cache(briefs_cache)
    else:
        try:
            updated = _synthesise_briefs(buyers_to_brief, history, briefs_cache, api_key)
            briefs_cache.update({k: {"brief": v, "synthesised_at": datetime.now(timezone.utc).isoformat()} for k, v in updated.items() if isinstance(v, str)})
            # Persist updated cache
            buyer_briefs_file.write_text(json.dumps(briefs_cache, indent=2, default=str), encoding="utf-8")
            briefs = _brief_texts_from_cache(briefs_cache)
            status = "ok"
        except Exception as exc:
            log.warning("Buyer intel synthesis failed: %s", exc)
            briefs = _brief_texts_from_cache(briefs_cache)
            status = "error"

    return {
        "buyer_intel_status": status,
        "buyer_intel_accumulated": accumulated,
        "buyer_intel_unique_buyers": unique_buyers,
        "buyer_intel_briefs": briefs,
        "buyer_intel_file": buyer_history_file,
    }
