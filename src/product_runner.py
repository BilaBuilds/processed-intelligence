"""
src/product_runner.py
=====================
Product Layer — multi-product shortlist generator.

Reads canonical scored_tenders.jsonl from a completed run and applies
per-product filter + ranking configs to produce differentiated outputs.

Design principles:
  - reads from run artifacts only; never re-runs ingest/normalize
  - base_score is immutable; product_rank = base_score + boost (not written back)
  - one bad product config must not block others (isolated failure)
  - adding a product = drop a JSON file in config/products/, done

Manifest semantics:
  - enabled_count: number of enabled product configs discovered
  - generated_count: number of products that successfully ran (regardless of output size)
  - Each product gets status: "ok" (has items), "empty" (no items but ran), or "error" (failed)
  - Top-level status is "ok" if generated_count > 0 (even if all outputs are empty)
  - Top-level status is "error" if any product failed
  - Top-level status is "no_products" if no configs enabled
  - Top-level status is "skipped" if no scored_tenders.jsonl available

Output per product:
  data/runs/<run_id>/products/<product_id>/product_shortlist.json
  data/runs/<run_id>/products/<product_id>/product_summary.json

Filter pipeline (applied in order, each stage logged):
  1. include_keywords   — title+description must match at least one (empty = all pass)
  2. exclude_keywords   — title+description must NOT match any
  3. regions            — region field must be in list (empty = all pass)
  4. buyer_filters      — buyer_name must contain at least one substring (empty = all pass)
  5. value band         — value_amount must be in [value_min, value_max] if set
  6. min_score          — base score must be >= min_score
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("product_runner")

PRODUCTS_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "products"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {
    "id", "display_name", "enabled", "min_score", "shortlist_size",
    "include_keywords", "exclude_keywords", "regions", "buyer_filters",
    "value_min", "score_boosts", "notify",
}

_OPTIONAL_FIELDS = {
    "allow_null_value",  # default False
    "value_max",
}


def load_product_config(path: Path) -> dict[str, Any]:
    """Load and validate a single product config. Raises ValueError on bad config."""
    raw = json.loads(path.read_text(encoding="utf-8"))

    missing = _REQUIRED_FIELDS - raw.keys()
    if missing:
        raise ValueError(f"Product config {path.name} missing fields: {sorted(missing)}")

    if not isinstance(raw["id"], str) or not raw["id"]:
        raise ValueError(f"Product config {path.name}: 'id' must be a non-empty string")
    if not isinstance(raw["shortlist_size"], int) or raw["shortlist_size"] < 1:
        raise ValueError(f"Product config {path.name}: 'shortlist_size' must be a positive int")
    if not isinstance(raw["min_score"], int):
        raise ValueError(f"Product config {path.name}: 'min_score' must be an int")
    if not isinstance(raw["score_boosts"], dict):
        raise ValueError(f"Product config {path.name}: 'score_boosts' must be a dict")

    # Validate optional fields if present
    if "allow_null_value" in raw:
        if not isinstance(raw["allow_null_value"], bool):
            raise ValueError(f"Product config {path.name}: 'allow_null_value' must be a boolean")

    return raw


def discover_product_configs(config_dir: Path = PRODUCTS_CONFIG_DIR) -> list[dict[str, Any]]:
    """
    Load all enabled product configs from config_dir.
    Invalid configs are logged and skipped, never raised.
    """
    configs: list[dict[str, Any]] = []
    if not config_dir.exists():
        log.warning("Products config dir not found: %s", config_dir)
        return configs

    for path in sorted(config_dir.glob("*.json")):
        try:
            cfg = load_product_config(path)
            if cfg.get("enabled"):
                configs.append(cfg)
                log.debug("Loaded product config: %s", cfg["id"])
            else:
                log.debug("Skipped disabled product: %s", path.name)
        except Exception as exc:
            log.error("Invalid product config %s — skipping: %s", path.name, exc)

    log.info("Discovered %d enabled product configs", len(configs))
    return configs


# ---------------------------------------------------------------------------
# Scored tender loader
# ---------------------------------------------------------------------------

def load_scored_tenders(run_dir: Path) -> list[dict]:
    path = run_dir / "scored_tenders.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


# ---------------------------------------------------------------------------
# Filter pipeline
# ---------------------------------------------------------------------------

def _text_matches_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def _text_matches_none(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return not any(kw.lower() in lower for kw in keywords)


def _tender_text(tender: dict) -> str:
    return f"{tender.get('title', '')} {tender.get('description', '')}".strip()


def apply_filters(
    tenders: list[dict],
    config: dict,
) -> tuple[list[dict], dict[str, int]]:
    """
    Apply all product filters in order. Returns (matching_tenders, stage_counts).
    stage_counts records how many records survived each stage.
    """
    stages: dict[str, int] = {"input": len(tenders)}
    current = list(tenders)

    # 1. include_keywords — at least one must match title+description (empty = all pass)
    include_kw = config.get("include_keywords") or []
    if include_kw:
        current = [t for t in current if _text_matches_any(_tender_text(t), include_kw)]
    stages["after_include_keywords"] = len(current)

    # 2. exclude_keywords — none must match
    exclude_kw = config.get("exclude_keywords") or []
    if exclude_kw:
        current = [t for t in current if _text_matches_none(_tender_text(t), exclude_kw)]
    stages["after_exclude_keywords"] = len(current)

    # 3. regions — region must be in list (empty = all pass)
    regions = [r.lower() for r in (config.get("regions") or [])]
    if regions:
        current = [
            t for t in current
            if (t.get("region") or "").lower() in regions
        ]
    stages["after_region_filter"] = len(current)

    # 4. buyer_filters — buyer_name must contain at least one substring (empty = all pass)
    buyer_filters = [bf.lower() for bf in (config.get("buyer_filters") or [])]
    if buyer_filters:
        current = [
            t for t in current
            if any(
                bf in (t.get("buyer_name") or t.get("buyer") or "").lower()
                for bf in buyer_filters
            )
        ]
    stages["after_buyer_filter"] = len(current)

    # 5. value band
    value_min = config.get("value_min")
    value_max = config.get("value_max")
    allow_null = config.get("allow_null_value", False)
    if value_min is not None or value_max is not None:
        filtered = []
        for t in current:
            v = t.get("value_amount")
            if v is None:
                # if allow_null_value is True, pass null values through
                if allow_null:
                    filtered.append(t)
                # else: strict filtering — null values excluded when value filter is set
            else:
                try:
                    v_num = float(v)
                    ok = True
                    if value_min is not None and v_num < value_min:
                        ok = False
                    if value_max is not None and v_num > value_max:
                        ok = False
                    if ok:
                        filtered.append(t)
                except (TypeError, ValueError):
                    filtered.append(t)
        current = filtered
    stages["after_value_filter"] = len(current)

    # 6. min_score
    min_score = config.get("min_score", 0)
    current = [t for t in current if (t.get("score") or 0) >= min_score]
    stages["after_min_score"] = len(current)

    return current, stages


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def compute_product_rank(tender: dict, score_boosts: dict[str, int]) -> int:
    """
    product_rank = base_score + sum of matched keyword boosts.
    Never mutates the tender dict.
    """
    base = tender.get("score") or 0
    text = _tender_text(tender).lower()
    boost = sum(v for kw, v in score_boosts.items() if kw.lower() in text)
    return base + boost


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

def _write_product_artifacts(
    output_dir: Path,
    product_id: str,
    run_id: str,
    records: list[dict],
    config: dict,
    stage_counts: dict[str, int],
    generated_at: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # product_shortlist.json
    shortlist_path = output_dir / "product_shortlist.json"
    shortlist_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # product_summary.json
    summary = {
        "product_id":     product_id,
        "display_name":   config.get("display_name", product_id),
        "run_id":         run_id,
        "generated_at":   generated_at,
        "item_count":     len(records),
        "filter_stages":  stage_counts,
        "config_applied": {
            "min_score":       config.get("min_score"),
            "shortlist_size":  config.get("shortlist_size"),
            "include_keywords": config.get("include_keywords", []),
            "exclude_keywords": config.get("exclude_keywords", []),
            "regions":          config.get("regions", []),
            "buyer_filters":    config.get("buyer_filters", []),
            "value_min":        config.get("value_min"),
            "value_max":        config.get("value_max"),
            "score_boosts":     config.get("score_boosts", {}),
        },
    }
    (output_dir / "product_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Product runner — core
# ---------------------------------------------------------------------------

def run_product(
    tenders: list[dict],
    config: dict,
    run_dir: Path,
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    """
    Run one product config against all scored tenders.
    Returns a manifest entry dict.
    """
    product_id    = config["id"]
    shortlist_size = config["shortlist_size"]
    score_boosts  = config.get("score_boosts") or {}

    matched, stage_counts = apply_filters(tenders, config)

    if not matched:
        # Log which stage killed all records
        prev = stage_counts.get("input", 0)
        bottleneck = "input was empty"
        for stage, count in stage_counts.items():
            if stage == "input":
                prev = count
                continue
            if count < prev:
                bottleneck = f"{stage} (dropped {prev - count})"
                prev = count
        log.info(
            "Product '%s': 0 matched — bottleneck: %s",
            product_id, bottleneck,
        )

    # Rank and trim
    ranked = sorted(
        matched,
        key=lambda t: compute_product_rank(t, score_boosts),
        reverse=True,
    )[:shortlist_size]

    # Attach product_rank to each output record (separate field, never overwrites base score)
    output_records = []
    for t in ranked:
        rec = dict(t)
        rec["product_rank"] = compute_product_rank(t, score_boosts)
        rec["product_id"]   = product_id
        output_records.append(rec)

    output_dir = run_dir / "products" / product_id
    _write_product_artifacts(
        output_dir, product_id, run_id, output_records, config, stage_counts, generated_at,
    )

    status = "ok" if output_records else "empty"
    log.info(
        "Product '%s': %d/%d passed filters → shortlist %d — %s",
        product_id,
        stage_counts.get("after_min_score", len(matched)),
        stage_counts.get("input", len(tenders)),
        len(output_records),
        status,
    )

    return {
        "status":     status,
        "item_count": len(output_records),
        "path":       str(output_dir.relative_to(run_dir.parent.parent) if run_dir.parent.parent.exists() else output_dir),
        "stages":     stage_counts,
    }


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_all_products(
    run_dir: Path,
    config_dir: Path = PRODUCTS_CONFIG_DIR,
) -> dict[str, Any]:
    """
    Discover all enabled product configs and run each against scored_tenders.jsonl.
    Returns manifest-ready dict.
    """
    run_id = run_dir.name
    generated_at = datetime.now(timezone.utc).isoformat()

    # Load base tenders
    tenders = load_scored_tenders(run_dir)
    if not tenders:
        log.info("Product runner: no scored_tenders.jsonl in %s — skipping", run_dir.name)
        return {
            "status": "skipped",
            "reason": "scored_tenders.jsonl not found or empty",
            "enabled_count": 0,
            "generated_count": 0,
            "outputs": {},
        }

    log.info("Product runner: %d scored tenders available", len(tenders))

    configs = discover_product_configs(config_dir)
    if not configs:
        return {
            "status": "no_products",
            "enabled_count": 0,
            "generated_count": 0,
            "outputs": {},
        }

    outputs: dict[str, dict] = {}
    generated_count = 0

    for cfg in configs:
        product_id = cfg["id"]
        try:
            result = run_product(tenders, cfg, run_dir, run_id, generated_at)
            outputs[product_id] = result
            generated_count += 1
        except Exception as exc:
            log.error("Product '%s' failed (skipping): %s", product_id, exc)
            outputs[product_id] = {"status": "error", "error": str(exc), "item_count": 0}

    overall_status = "ok"
    if any(v.get("status") == "error" for v in outputs.values()):
        overall_status = "error"

    return {
        "status":          overall_status,
        "enabled_count":   len(configs),
        "generated_count": generated_count,
        "outputs":         outputs,
    }
