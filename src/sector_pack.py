"""
src/sector_pack.py
==================
Sector Pack Loader

Reads the TENDER_SECTOR environment variable (default: "construction") and
loads the matching pack from config/sectors/<sector>/.

A sector pack is three YAML files:
    scoring.yaml  — keyword_weights, disqualify_keywords, region_weights, value_bands
    niche.yaml    — trade definitions, geographies, exclusions (legacy civils_niche shape)
    meta.yaml     — dashboard_labels, outreach_templates, sector display name

Usage:
    from src.sector_pack import get_pack
    pack = get_pack()                      # reads TENDER_SECTOR env var
    pack = get_pack("social_housing")      # explicit override

    pack.scoring.keyword_weights           # dict[str, int]
    pack.scoring.disqualify_keywords       # set[str]
    pack.scoring.region_weights            # dict[str, int]
    pack.scoring.value_bands               # list[tuple[float, float, int]]
    pack.niche                             # raw dict (trades, exclusions, value_bands)
    pack.meta                              # raw dict (display_name, dashboard_labels, ...)
    pack.sector                            # str e.g. "construction"
    pack.niche_yaml_path                   # Path to niche.yaml (for context.py)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("sector_pack")

# Root of the project (two levels up from this file: src/ -> tender_engine/)
_BASE_DIR = Path(__file__).resolve().parent.parent
_SECTORS_DIR = _BASE_DIR / "config" / "sectors"

DEFAULT_SECTOR = "construction"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScoringConfig:
    keyword_weights: dict[str, int] = field(default_factory=dict)
    disqualify_keywords: set[str] = field(default_factory=set)
    region_weights: dict[str, int] = field(default_factory=dict)
    value_bands: list[tuple[float, float, int]] = field(default_factory=list)


@dataclass
class SectorPack:
    sector: str
    scoring: ScoringConfig
    niche: dict[str, Any]
    meta: dict[str, Any]
    niche_yaml_path: Path


# ---------------------------------------------------------------------------
# YAML loader (no external deps beyond PyYAML which context.py already uses)
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        log.warning("Sector pack file not found: %s", path)
        return {}
    try:
        import yaml  # type: ignore
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        log.error("PyYAML not installed — cannot load sector pack from %s", path)
        return {}
    except Exception as exc:
        log.error("Failed to load %s: %s", path, exc)
        return {}


# ---------------------------------------------------------------------------
# Scoring YAML -> ScoringConfig
# ---------------------------------------------------------------------------

def _parse_scoring(raw: dict[str, Any]) -> ScoringConfig:
    kw_raw = raw.get("keyword_weights") or {}
    kw: dict[str, int] = {str(k): int(v) for k, v in kw_raw.items()}

    disq_raw = raw.get("disqualify_keywords") or []
    disq: set[str] = {str(kw_).strip().lower() for kw_ in disq_raw}

    reg_raw = raw.get("region_weights") or {}
    reg: dict[str, int] = {str(k).lower(): int(v) for k, v in reg_raw.items()}

    vb_raw = raw.get("value_bands") or []
    vb: list[tuple[float, float, int]] = []
    for band in vb_raw:
        try:
            vb.append((float(band["min"]), float(band["max"]), int(band["score"])))
        except (KeyError, TypeError, ValueError):
            log.warning("Skipping malformed value_band entry: %s", band)

    return ScoringConfig(
        keyword_weights=kw,
        disqualify_keywords=disq,
        region_weights=reg,
        value_bands=vb,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_cache: dict[str, SectorPack] = {}


def get_pack(sector: str | None = None) -> SectorPack:
    """
    Load (and cache) a sector pack.

    Args:
        sector: Sector name override. If None, reads TENDER_SECTOR env var.
                Defaults to "construction" if env var is also unset.

    Returns:
        SectorPack with scoring, niche, and meta data loaded.

    Raises:
        FileNotFoundError: If the sector directory does not exist.
    """
    if sector is None:
        sector = os.getenv("TENDER_SECTOR", DEFAULT_SECTOR).strip().lower()

    if sector in _cache:
        return _cache[sector]

    sector_dir = _SECTORS_DIR / sector
    if not sector_dir.is_dir():
        # Try to fall back to default sector gracefully
        if sector != DEFAULT_SECTOR:
            log.warning(
                "Sector pack '%s' not found at %s — falling back to '%s'",
                sector, sector_dir, DEFAULT_SECTOR,
            )
            return get_pack(DEFAULT_SECTOR)
        raise FileNotFoundError(
            f"Default sector pack '{DEFAULT_SECTOR}' missing. "
            f"Expected directory: {sector_dir}"
        )

    scoring_raw = _load_yaml(sector_dir / "scoring.yaml")
    niche_raw = _load_yaml(sector_dir / "niche.yaml")
    meta_raw = _load_yaml(sector_dir / "meta.yaml")

    pack = SectorPack(
        sector=sector,
        scoring=_parse_scoring(scoring_raw),
        niche=niche_raw,
        meta=meta_raw,
        niche_yaml_path=sector_dir / "niche.yaml",
    )

    _cache[sector] = pack
    log.info(
        "Loaded sector pack '%s': %d keywords, %d disqualifiers, %d region weights",
        sector,
        len(pack.scoring.keyword_weights),
        len(pack.scoring.disqualify_keywords),
        len(pack.scoring.region_weights),
    )
    return pack


def clear_cache() -> None:
    """Clear the pack cache — useful in tests."""
    _cache.clear()
