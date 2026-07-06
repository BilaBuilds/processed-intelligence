# DACH Adapter Skeleton

This is a skeleton only. It creates a local adapter, normalization, and export structure for Germany, Austria, and Switzerland using fixture data.

No live scraping has been performed. The DACH live sources remain unverified, and this work does not claim live DACH coverage.

The current TenderNed Hostinger demo remains untouched. `run_pipeline.py` was intentionally not modified.

## What Exists

- `scripts/dach/normalize_dach_tender.py`: normalizes one raw fixture-like tender into the DACH normalized object.
- `scripts/dach/dach_adapter_base.py`: provides the future adapter shape with `source_name`, `country`, `fetch_raw()`, `normalize()`, and `export()`.
- `scripts/dach/dach_demo_fixtures.py`: contains nine clearly marked fixture-only notices.
- `scripts/dach/export_dach_demo.py`: exports fixture-only demo JSON, JSONL, and summary files under `data/dach/demo`.
- `data/dach/fixtures/dach_sample_raw.json`: small raw fixture sample for planning and tests.

## Guardrails

- DACH demo data is fixture-only.
- No network calls are implemented.
- `fetch_raw()` raises `NotImplementedError`.
- No API keys, credentials, raw databases, logs, caches, or backups are required.
- Future adapter work must first complete source verification, including terms, API/RSS/download support, authentication, rate limits, fields, duplicate risk, and stale notice behavior.

## Demo Disclaimer

The generated demo summary contains this disclaimer:

> DACH demo generated from fixture data. No live scraping performed.
