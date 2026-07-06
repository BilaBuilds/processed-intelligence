# Dashboard Restyle - 2026-07-06

## Summary

The Hostinger static dashboard was restyled to sit closer to the ProcessEd landing-page direction while preserving the working static JSON/JS data architecture.

The dashboard remains a single static HTML file that reads `dashboard_data.js`. No Flask, VPS, DuckDB, React, Next.js, or `run_pipeline.py` changes were introduced.

## Files Changed

- `hostinger_upload/dashboard.html`
- `data/export/hostinger_upload_bundle/dashboard.html`
- `tests/test_dashboard_visual_contract.py`
- `docs/DASHBOARD_RESTYLE_2026_07_06.md`

Timestamped backups were created before editing:

- `local_backups/dashboard_restyle_20260706_012142/hostinger_upload_dashboard.html.bak_20260706_012142`
- `local_backups/dashboard_restyle_20260706_012142/bundle_dashboard.html.bak_20260706_012142`

## Visual Changes

- Replaced the dark vertical sidebar treatment with a light translucent top navigation shell.
- Added mist/ice page backgrounds using `#EDF1F2` and `#E5EAEC`.
- Updated primary navy and amber tokens to `#172A3E`, `#15263A`, `#F4B247`, and `#F2A93B`.
- Added glass-style dashboard cards with subtle borders, blur, and amber left accents.
- Strengthened KPI cards and table hover states without changing their data bindings.
- Styled intelligence and radar sections as dark navy blocks for stronger contrast.
- Added responsive rules to prevent horizontal page overflow on mobile while preserving scrollable data tables.

## Buyer Watchlist Clarification

The former outreach page is now labelled as a buyer intelligence watchlist. This keeps public-sector buyer accounts separate from client sales prospects and avoids implying that councils, NHS bodies, housing providers, or other public buyers are paying outreach targets.

Copy and UI mappings were updated:

- `Outreach queue` is now `Buyer watchlist`.
- `outreach targets` is now `buyer accounts tracked`.
- hot/warm/actionable/follow-up cards are now high-signal buyers, tracked buyers, timing signals, watchlist items, and total tracked.
- draft email actions are now buyer note actions.
- sent/contacted states are now reviewed states.
- zero or missing scores show `Tracking`, `Monitor`, `Not scored yet`, and `Not available` instead of misleading `0/100`, `Low`, or blank values.

This change only affects static dashboard presentation. It does not modify `run_pipeline.py`, `dashboard_data.json`, the dashboard data schema, or Hostinger upload architecture.

## Public Demo Copy Polish

The overview page and navigation were also tightened for public demo use so the dashboard reads as a credible static intelligence portal rather than a fully live commercial operations console.

- `Move on timing-ready buyers...` is now `Review timing-ready public opportunities...`
- `Next operator move` is now `Next review action`
- overview and buyer KPI labels now use buyer-signal language such as `High-signal buyers`, `Tracked buyers`, `Timing-ready`, and `Recent buyer activity`
- zero-state client and historical-activity areas now explain the public demo limitation instead of looking broken
- execution truth now states that delivery is currently via static Hostinger export for the public demo
- the visible navigation no longer exposes `Avatar builder`

## Static Demo Credentials

The public static login no longer supports the weak `admin/admin` or `user/user` demo credentials. The Hostinger HTML keeps only SHA-256 password hashes for the `demo` and `bilal` accounts.

This remains a static front-end gate. No backend, data schema, pipeline, or Hostinger architecture changes were introduced.

## Buyer Intelligence Public Demo Table

The Buyer intelligence page was tightened again for public Hostinger demos so unfinished internal workflow states do not appear as broken product features.

- the page subtitle now says `Public-sector buyer watchlist built from the current TenderNed demo export`
- the buyer table now uses `Buyer`, `Signal`, `Related opportunity`, `Review status`, and `Source`
- missing buyer/dossier links now show `No scored opportunity linked yet`
- source copy now uses `TenderNed public data`
- rows with no scored linked opportunity show `Tracking` and `Watch only`
- the topbar demo toggle is labelled `Demo mode` rather than `Admin`
- weak internal strings such as `No dossier path available`, `No quick actions available`, `Fit 0%`, `Not started`, and `Action state` were removed from the public dashboard source

## Data Compatibility Preserved

The dashboard still reads:

- `window.PROCESSED_DASHBOARD_DATA`
- `window.dashboardData`
- `window.DASHBOARD_DATA`

The existing frontend bindings remain present for:

- `hot_outreach`
- `warm_buyers`
- `timing_ready`
- `avg_fit_score`
- `pipeline_model`
- `supplier_source`
- `notifier_channels`

## Files To Upload To Hostinger

Upload these files from `data/export/hostinger_upload_bundle/`:

- `dashboard.html`
- `dashboard_data.js`
- `dashboard_data.json`
- `tenderned_latest.json`

For this restyle, the required changed upload file is:

- `data/export/hostinger_upload_bundle/dashboard.html`

## Browser Verification Checklist

After uploading, hard refresh the Hostinger dashboard and check:

- The page opens with a light mist background.
- The navigation is a translucent top bar, not a dark vertical sidebar.
- KPI cards still show the live counts and amber accents.
- Hot outreach, warm buyers, timing ready, average fit score, supplier source, and notifier channels still show the confirmed values.
- Top opportunities and summaries still render.
- Mobile width has no full-page horizontal overflow.

Optional console check:

```js
const d = window.PROCESSED_DASHBOARD_DATA || window.dashboardData || window.DASHBOARD_DATA;
({
  hot: d.hot_outreach?.length,
  warm: d.warm_buyers?.length,
  timing: d.timing_ready?.length,
  avg: d.avg_fit_score,
  loop: d.pipeline_model?.loop_steps,
  supplier: d.pipeline_model?.supplier_source,
  channels: d.pipeline_model?.notifier_channels
})
```

## Local Verification Completed

- `python -m pytest tests/test_dashboard_visual_contract.py -q` passed.
- Headless Chrome opened `hostinger_upload/dashboard.html` locally.
- The rendered page title started with `ProcessEd`.
- The restyle block and `dashboard_data.js` script were present.
- Desktop render width matched client width at 1440px, so no full-page horizontal overflow was detected at that viewport.

## Not Verified

- VPS sync is not verified in this local-only session.
- Hostinger production upload is not performed from this environment.
