# Hostinger Dashboard Export

Generated locally for the static Hostinger dashboard. This is the current production path:

TenderNed public TNS JSON -> canonical tenders -> static Hostinger dashboard export.

No VPS, Flask, DuckDB, or TenderNed XML credentials are required for this flow.

## Files Created

The Hostinger-ready upload bundle is:

`C:\Users\bilal\tender_engine\data\export\hostinger_upload_bundle`

It contains:

- `dashboard.html`
- `dashboard_data.json`
- `dashboard_data.js`
- `tenderned_latest.json`

The same dashboard files are also written locally to:

- `data/export/dashboard_data.json`
- `data/export/dashboard_data.js`
- `data/dashboard/dashboard_data.json`
- `data/dashboard/dashboard_data.js`
- `data/export/tenderned_latest.json`
- `data/dashboard/tenderned_latest.json`

## Current Export Status

- Dashboard version: `hostinger_static_v2`
- Status: `ready`
- Source input: `C:\Dev\dutch_output\dutch_tenders.json`
- Total tenders: 50
- Total opportunities: 50
- Unique buyers: 45
- Shortlist count: 21
- Average fit score: 16
- Hot outreach: 5
- Warm buyers: 19
- Timing ready: 7
- Product rails: 2
- Tenders with score above 0: 40
- Hostinger ready: true
- VPS verified: false

The export now populates compatibility fields used by old and new dashboard code:

- `status`
- `total_tenders`
- `total_opportunities`
- `shortlist_count`
- `buyer_count`
- `client_count`
- `pipeline_runs`
- `avg_fit_score`
- `hot_outreach`
- `outreach_queue`
- `warm_buyers`
- `timing_ready`
- `products`
- `product_rails`
- `pipeline_model`
- `supplier_source`
- `notifier_channels`
- `loop_steps`
- `post_run_steps`
- `fatal_steps`
- `latestRun.tenders`
- `latestRun.opportunities`
- `latestRun.shortlist`
- `latestRun.buyers`
- `latestRun.buyerCards`
- `latestRun.manifest.shortlist_count`
- `latestRun.summary.avg_fit_score`
- `latestRun.summary.hot_outreach`
- `latestRun.summary.warm_buyers`
- `latestRun.summary.timing_ready`
- `tenders`
- `opportunities`
- `shortlist`
- `buyers`
- `buyerCards`
- `top_buyers`
- `kpis`
- `system_health`
- `generated_at`

Each tender/opportunity includes dashboard table fields:

- `id`
- `source_id`
- `source`
- `country`
- `title`
- `buyer`
- `region`
- `deadline`
- `published_at`
- `publication_date`
- `value`
- `decision`
- `verdict`
- `confidence`
- `score`
- `procedure`
- `contract_type`
- `url`
- `summary`
- `description`
- `rationale`
- `next_step`

## Files To Upload To Hostinger

Upload these files from:

`C:\Users\bilal\tender_engine\data\export\hostinger_upload_bundle`

Files:

- `dashboard.html`
- `dashboard_data.json`
- `dashboard_data.js`
- `tenderned_latest.json`

Upload them to the same Hostinger static data directory where the live dashboard currently reads `dashboard_data.js` or `dashboard_data.json`.

## Manual Upload Instructions

1. Open Hostinger File Manager or your upload client.
2. Navigate to the live dashboard static data directory.
3. Upload `dashboard.html`, `dashboard_data.json`, `dashboard_data.js`, and `tenderned_latest.json`.
4. Overwrite the existing files.
5. Clear Hostinger/cache/CDN cache if the old generated timestamp remains visible.
6. Hard-refresh the browser.

## Browser Verification

Open the live dashboard and check:

- KPI/sidebar Tenders should show 50.
- Shortlist should show 21.
- Buyers should show 45.
- Avg fit score should show 16 rather than 0.
- Hot outreach should show 5 rather than 0.
- Warm buyers should show 19 rather than 0.
- Timing ready should show 7 rather than 0.
- Products should show 2 rather than 0.
- Pipeline model should show 1 loop step, supplier source `tenderned_json`, and notifier channel `hostinger_static`.
- The opportunities table should still show 50 Dutch TenderNed rows.
- Region should show `Netherlands` where no better region exists.
- Decision/confidence/score/summary should be populated.

Console checks:

```js
window.PROCESSED_DASHBOARD_DATA.total_tenders
window.PROCESSED_DASHBOARD_DATA.shortlist_count
window.PROCESSED_DASHBOARD_DATA.buyer_count
window.PROCESSED_DASHBOARD_DATA.avg_fit_score
window.PROCESSED_DASHBOARD_DATA.hot_outreach.length
window.PROCESSED_DASHBOARD_DATA.warm_buyers.length
window.PROCESSED_DASHBOARD_DATA.timing_ready.length
window.PROCESSED_DASHBOARD_DATA.products.length
window.PROCESSED_DASHBOARD_DATA.pipeline_model
window.PROCESSED_DASHBOARD_DATA.latestRun.summary
window.PROCESSED_DASHBOARD_DATA.opportunities[0]
```

The patched frontend also logs this mapping:

```js
// Search console output for:
"[ProcessEd dashboard mapping]"
```

Expected:

- `total_tenders` is `50`
- `shortlist_count` is `21`
- `buyer_count` is `45`
- `avg_fit_score` is `16`
- `hot_outreach.length` is `5`
- `warm_buyers.length` is `19`
- `timing_ready.length` is `7`
- `products.length` is `2`
- `pipeline_model.supplier_source` is `tenderned_json`
- `pipeline_model.notifier_channels[0]` is `hostinger_static`
- `system_health.status` is `ready`
- `system_health.hostinger_ready` is `true`

## TenderNed XML Status

TenderNed `/public-xml` is intentionally not required. It returns 403 without Basic Auth credentials.

Credentials can be requested from `functioneelbeheer@tenderned.nl`.

If `TENDERNED_USERNAME` and `TENDERNED_PASSWORD` exist later, XML enrichment can be added as an optional layer. Missing XML credentials must continue to skip cleanly and must not block the JSON-first dashboard flow.

## Not Verified

VPS access is blocked in this session, so these were not verified:

- `/opt/tender_engine/data/export`
- The VPS-to-Hostinger 5-minute sync job
- Production cron state
- Whether the VPS has the same v2 bundle

## Regenerate Locally

From `C:\Users\bilal\tender_engine`:

```powershell
python scripts\build_hostinger_dashboard_export.py --input C:\Dev\dutch_output\dutch_tenders.json --output-dir data\export --dashboard-dir data\dashboard
```

Run tests:

```powershell
python -m pytest tests\test_hostinger_dashboard_export.py -q
```
