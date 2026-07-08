# Azure Deployment Prep

## Recommended Static Web App Shape

Use Azure Static Web Apps for the first hosted product surface. Deploy only a sanitized frontend folder from GitHub. In this repository, the best current candidates are:

- Landing page: `index_v2.html`
- Demo dashboard: `dashboard.html`, after reviewing the embedded data and replacing any private runtime rows with demo/synthetic data
- Data bundle: a future committed `public/demo-data/*.json` or `public/demo-data/*.js` bundle containing sanitized demo records only

Do not point Azure at `data/`, `warehouse/`, `measurement_runs/`, logs, SQLite/DuckDB files, raw XML, client exports, or `.env` files.

## GitHub Deployment Notes

Recommended path:

1. Create a small deployable frontend folder, for example `portal_static/`.
2. Copy or refactor `index_v2.html` as `portal_static/index.html`.
3. Add a sanitized demo dashboard page under `portal_static/dashboard.html`.
4. Store demo-only JSON under `portal_static/demo-data/`.
5. Configure Azure Static Web Apps to build from GitHub with:
   - App location: `portal_static`
   - API location: blank for v1
   - Output location: blank for plain static HTML

This branch does not deploy anything to Azure.

## Environment Variables Needed Later

Keep these in Azure/GitHub secret stores, never in committed files:

- `TENDERNED_XML_USERNAME`
- `TENDERNED_XML_PASSWORD`
- `TENDERNED_XML_BASE_URL`
- Future API/database secrets for Azure Functions, Azure SQL/Postgres, Blob Storage, AI services, and authentication

## Local Pipeline Versus Hosted Surface

The local machine or WSL pipeline remains the intelligence engine for now. It can ingest raw sources, preserve private raw payloads, run enrichment, and generate sanitized outputs. Azure should initially host only the client-facing surface and demo-safe bundles.

That separation keeps credentials, raw notices, warehouse files, and customer/outreach data out of the public deployment path while still giving GitHub and Azure a clean product surface.

## Do Not Deploy

- `.env` or `.env.*`
- Raw TenderNed XML
- `data/` except deliberately sanitized static demo bundles created for deployment
- `warehouse/` database files
- SQLite, DuckDB, cache, log, CSV, XLSX, parquet, JSONL runtime files
- Customer data, outreach drafts, mailbox exports, or machine traces containing private business information
