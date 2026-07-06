# Landing Page Hostinger Export

## Summary

Created a premium static landing page for ProcessEd Intelligence that links into the existing Hostinger dashboard.

The page is built as a single static HTML file with embedded CSS and no external framework, CDN, build step, VPS, DuckDB, or backend requirement.

## Files Created

- `hostinger_upload/index.html`
- `data/export/hostinger_upload_bundle/index.html`
- `tests/test_landing_page_static.py`
- `docs/LANDING_PAGE_HOSTINGER.md`

## Design Direction

The landing page follows the supplied ProcessEd reference style:

- Pale mist backgrounds: `#E5EAEC` and `#EDF1F2`
- Deep navy typography: `#15263A` and `#172A3E`
- Amber accents: `#F4B247` and `#F2A93B`
- Muted blue-grey support text: `#8195A8`
- Dark navy capability band: `#142437` and `#182B40`
- Soft glass cards, thin borders, rounded corners, and monospace micro-labels

## Included Sections

- Header with ProcessEd logo, navigation, Request demo, and Sign in
- Hero with the headline `Win contracts before the ITT drops.`
- Dashboard preview using the current live demo metrics
- Dark ticker strip
- Problem and workflow section
- Capability cards
- 2-week pilot CTA
- Footer with dashboard link and VPS verification note

## Links

- Request demo / early access:
  `mailto:info@processedcivils.com?subject=ProcessEd%20Pilot%20Access%20Request`
- Book pilot review:
  `mailto:info@processedcivils.com?subject=ProcessEd%202-Week%20Pilot%20Review`
- Sign in / Open dashboard:
  `dashboard.html`

## Files To Upload To Hostinger

Upload these from `data/export/hostinger_upload_bundle/`:

- `index.html`
- `dashboard.html`
- `dashboard_data.js`
- `dashboard_data.json`
- `tenderned_latest.json`

For this landing-page release, the newly required upload file is:

- `data/export/hostinger_upload_bundle/index.html`

## Browser Verification Checklist

After upload:

- Visit the Hostinger root page and confirm `index.html` loads.
- Confirm the hero headline reads `Win contracts before the ITT drops.`
- Confirm Request demo and Request early access open the pilot access email.
- Confirm Book pilot review opens the pilot review email.
- Confirm Sign in and Open live dashboard navigate to `dashboard.html`.
- Confirm the dashboard preview shows 50 tenders, 21 shortlisted, 45 buyers, 5 hot outreach, 19 warm buyers, 7 timing-ready, and 16% average fit score.
- Confirm the footer says `Production VPS pipeline verification pending.`
- Check mobile width for clean stacking and no full-page horizontal overflow.

## Test

Run:

```powershell
python -m pytest tests\test_landing_page_static.py -q
```

Expected result:

```text
5 passed
```

## Not Claimed

The landing page does not claim paying clients, guaranteed tender wins, automated bid submission, or legal/procurement advice.
