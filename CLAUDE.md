# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo root

The only valid repo root is `C:\Users\bilal\tender_engine` (WSL path: `/mnt/c/Users/bilal/tender_engine`).
Never assume the project is in `C:\Dev` or any other folder.

## Running the pipeline

```bash
# Preferred — runs from any directory
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\bilal\tender_engine\run_tenders.ps1

# Direct fallback
python3 /mnt/c/Users/bilal/tender_engine/run_pipeline.py
```

After a run, report: `run_id`, ingest counts by source, shortlist count, new count, notify status, and the manifest path under `data/runs/<run_id>/run_manifest.json`.

## Tests

```bash
# Full suite
python3 -m pytest tests/ -q

# Single test file
python3 -m pytest tests/test_supplier_match.py -v

# Single test
python3 -m pytest tests/test_supplier_match.py::test_deterministic_same_score_on_repeat -v
```

`pythonpath = .` is set in `pytest.ini` so all `src.*` imports resolve from the repo root. The one known pre-existing failure is `test_real_shortlist_loads` — it asserts the latest run has a non-empty shortlist; it fails on quiet market days, not on code defects.

## Environment

Copy `config/.env.example` to `config/.env` and set values. Key variables:

| Variable | Purpose |
|---|---|
| `TENDER_WEBHOOK_URL` | Discord notification delivery |
| `TENDER_MIN_SCORE` | Minimum match score to retain a tender (default 20) |
| `TENDER_DECISION_BID_MIN_SCORE` | Score floor for BID verdict (default 40) |
| `TENDER_INGEST_MODE` | `incremental` / `recovery` / `backfill` |
| `TENDER_SECTOR` | Active sector pack (default `construction`) |
| `GEMINI_API_KEY` | Optional — buyer intelligence briefs only |

## Architecture

### Two separate systems sharing one repo

**Demand pipeline** (`run_pipeline.py` + `src/`) — ingests UK procurement notices, scores and filters them, and sends Discord alerts. The core pipeline must never import from `src/supplier/` or `src/market/`.

**Supply intelligence layer** (`src/supplier/`, `src/market/`) — matches shortlisted tenders against supplier records using market profiles. Consumes pipeline outputs only; never modifies them.

### Demand pipeline step order

```
ingest → normalize → match → context → buyer_intel → tender_forecast →
buyer_timing → patterns → select → decision → dedupe →
buyer_watchlist → buyer_intel_attach → products → clients → notify →
outreach_queue → openclaw_sync → dashboard
```

Fatal steps (pipeline aborts on failure): `ingest`, `normalize`, `match`, `context`, `select`, `decision`, `dedupe`.

Non-fatal steps (logged, pipeline continues): `buyer_intel`, `tender_forecast`, `buyer_timing`, `patterns`, `buyer_watchlist`, `products`, `clients`, `notify`.

Each step is a `run(context: dict) -> dict` function imported dynamically. Steps read from `context` (set by previous steps) and write back into it.

### Key data flow

- `raw_tenders.jsonl` → `normalized_tenders.jsonl` → `scored_tenders.jsonl`
- `scored_tenders.jsonl` → `shortlist.json` → `decision_shortlist.json` → `deduped.jsonl`
- `decision_shortlist.json` is the handoff point to the supplier intelligence layer

### Configuration layers

| Config path | Consumed by |
|---|---|
| `config/sectors/<sector>/scoring.yaml` | `src/match.py` via `src/sector_pack.py` — keyword weights, disqualifiers, region weights, value bands |
| `config/sectors/<sector>/niche.yaml` | `src/context.py` — trade classification and strategic fit narrative |
| `config/markets/<market>.yaml` | `src/market/profile.py` — supplier matching weights and tiers |
| `config/products/<product>.json` | `src/product_runner.py` — per-product filter/ranking config |
| `config/clients/<client>.json` | `src/client_runner.py` — per-client shortlist delivery |

Sector packs and market profiles are **different systems**. Sector packs control demand-side scoring; market profiles control supply-side matching.

### Supplier intelligence layer (Phase 4+)

Three-stage pipeline: `ingest_suppliers` → `normalize_suppliers` → `match_suppliers`.

- `src/supplier/match_suppliers.py` — scores every `SupplierRecord` against every `ShortlistedTender` across four dimensions (capability keyword overlap, regional fit, value band overlap, sector experience). Weights come entirely from `MarketProfile.scoring_weights`. Suppliers with flags in `profile.disqualifier_flags` or `suspended` are hard-excluded before scoring.
- `src/schemas/match.py` — `SupplierMatch` output contract. `schema_version` must be bumped on any field change.
- `src/schemas/shortlist.py` — `ShortlistedTender` input contract. The supplier layer must consume this, never raw dicts from pipeline artifacts.
- `src/market/registry.py` — explicit registry of market slugs → YAML paths. Add new markets here when adding a `config/markets/*.yaml`.

### Shared utilities

- `src/utils/region.py` — single source of truth for ONS NUTS/ITL code decoding and `region_slug()`. Both normalize and supplier layers import from here; never duplicate.
- `src/entities.py` — canonical frozen dataclasses: `ProcurementOpportunity`, `DecisionEvent`, `RiskSignal`, `SupplierEntity`.
- `src/sector_pack.py` — loads `config/sectors/<sector>/` YAML trio into a `SectorPack`. Use `get_pack()` which respects `TENDER_SECTOR` env var.

### State and artifacts

- `data/runs/<run_id>/` — all per-run artifacts; never write outside this during a run
- `state/` — cross-run persistent state: `buyer_history.jsonl`, `sent_log.sqlite`, FTS watermark files
- `openclaw_workspace/` — markdown sidecar files for operator intelligence (buyers, run summaries, timing watchlist). Written by `scripts/sync_to_openclaw.py` after each run; never modifies pipeline state.

## Diagnosis rules

- `Notify: skipped` with `new_count = 0` is a normal healthy run.
- `FTS: 0 releases fetched` is not automatically an error — the FTS window may be dry.
- If FTS or Discord fails only inside a sandbox/CI environment, state: *"This failure is sandbox/network constrained, not a repo regression."*
- Check `run_manifest.json` first before diagnosing failures — it captures per-step status, error strings, and durations.
