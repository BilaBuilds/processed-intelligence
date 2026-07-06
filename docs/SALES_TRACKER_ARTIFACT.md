# ProcessEd Sales Tracker Artifact

## Purpose

`data/sales/process_ed_sales_tracker.html` is a standalone working tracker for ProcessEd Intelligence sales outreach. It is designed for manual, targeted B2B outreach to construction and civils companies, with fields for contacts, status, sentiment, notes, opt-outs, suppression notes, and next steps.

## How to open locally

Open `data/sales/process_ed_sales_tracker.html` directly in a browser. Keep `process_ed_sales_tracker_data.js` in the same folder as the HTML file so the seed company data loads correctly.

For Hostinger, upload these files together:

- `data/sales/process_ed_sales_tracker.html`
- `data/sales/process_ed_sales_tracker_data.js`
- `data/sales/process_ed_sales_tracker_data.json`
- `data/sales/outreach_tracker_2026_07_06.csv`

No backend, API key, credential, React, Next.js, or Flask service is required.

## How localStorage edits work

The tracker loads the 10 seed companies from `process_ed_sales_tracker_data.js`. When a status, sentiment, notes field, opt-out, suppression note, or other editable field changes, the browser saves the working copy in localStorage under `processed_sales_tracker_state_v1`.

Those edits stay in that browser on that device. They do not change the source JSON, JS, or CSV files until you export and intentionally replace a file yourself.

Use `Reset local changes` in the dashboard to remove the localStorage company edits and reload the original seed data.

## How to export CSV

Use `Export current CSV` in the dashboard. The browser downloads the current local tracker state as `process_ed_sales_tracker_export.csv`, including edited statuses, notes, opt-out flags, and suppression notes.

## Today's outreach target

The daily execution checklist is:

- 10 LinkedIn profile reviews
- 5 contact names identified
- 5 personalised messages drafted
- 3 messages sent
- 1 demo/call ask

Checklist ticks are saved separately in localStorage under `processed_sales_tracker_goals_v1`.

## Why this is separate from the procurement dashboard

This artifact is a sales execution workspace, not a public procurement intelligence dashboard. Keeping it under `data/sales/` prevents outreach notes, contact research, suppression fields, and working sales state from being mixed into the existing public TenderNed dashboard bundle or pipeline outputs.
