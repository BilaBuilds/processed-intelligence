# DACH Static Demo Bundle

The DACH static demo bundle is fixture-only. It packages the locally scored DACH demo tenders into a standalone HTML, JSON, and JavaScript dashboard for review.

No live scraping is performed. The bundle is not bid advice and makes no guaranteed-win claims.

The TenderNed Hostinger dashboard is not touched. This DACH upload path is separate:

`data/export/dach_demo_bundle`

## Files

- `data/export/dach_demo_bundle/index.html`
- `data/export/dach_demo_bundle/dach_dashboard_data.json`
- `data/export/dach_demo_bundle/dach_dashboard_data.js`

## Data Source

The bundle reads from the local fixture scoring outputs:

- `data/dach/demo/dach_demo_scored.json`
- `data/dach/demo/dach_demo_score_summary.json`

The dashboard data payload is exposed as:

`window.PROCESSED_DACH_DASHBOARD_DATA`

## Guardrails

- Fixture-only DACH sample data.
- No live scraping.
- Not bid advice.
- No guaranteed-win claims.
- No API keys or credentials.
- No edits to `run_pipeline.py`.
- No edits to `dashboard_data.json` or `dashboard_data.js`.
- No edits to the current TenderNed Hostinger dashboard.

Future live integration requires source verification first, including terms, authentication, rate limits, available fields, duplicate handling, and stale notice handling.
