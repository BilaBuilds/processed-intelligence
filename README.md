# ProcessEd Intelligence

ProcessEd Intelligence is a procurement intelligence and contact enrichment project. It is designed to ingest tender/source data, normalize buyers and opportunities, enrich company/contact records, score evidence, and publish dashboard/export artifacts for review and outreach workflows.

This repository is GitHub-ready source code and documentation only. Runtime data, warehouse files, exports, logs, caches, local credentials, and generated artifacts must stay local.

## Core Pipeline Overview

The intended production pipeline entry point is:

```text
run_pipeline.py
```

In this local copy, the visible active implementation is the enrichment/Hermes layer:

1. Load configuration from `enrichment/config.yaml` and local environment variables.
2. Run provider waterfall enrichment in this order by default:
   - Companies House
   - website scrape
   - Hunter.io
   - pattern guess
3. Cache enrichment results locally in SQLite.
4. Write evidence records and policy decisions for client-safe review.
5. Generate Hermes batch outputs, outreach artifacts, machine traces, and HTML reports.
6. Keep warehouse/dashboard exports under ignored data paths.

Historical/local deployment facts:

- Historical VPS root: `/opt/tender_engine/`
- Warehouse path: `data/warehouse/procurement.duckdb` or `data/warehouse/procurement.db`
- Dashboard export path: `data/export/`

## Project Layout

```text
enrichment/     Enrichment package, providers, evidence, policy gates, storage
scripts/        Operational scripts, migrations, Hermes runners, validation
src/            Supporting classifier code
tests/          Unit tests
docs/           Architecture notes and agent handoff context
warehouse/      Warehouse schema docs only; do not commit database files
```

## Local Setup

Use Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a local environment file from the public template:

```powershell
Copy-Item .env.example .env
```

Fill `.env` locally only. Never commit `.env`.

## Environment Variables

Use [.env.example](.env.example) as the only committed reference for environment shape. It intentionally contains no real credentials.

Current template variables:

```text
COMPANIES_HOUSE_API_KEY=
HUNTER_API_KEY=
HOSTINGER_EMAIL=your-mailbox@example.com
HOSTINGER_EMAIL_PASSWORD=
HOSTINGER_IMAP_HOST=imap.hostinger.com
HOSTINGER_IMAP_PORT=993
HOSTINGER_DRAFTS_FOLDER=Drafts
SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
TENDER_ENGINE_ROOT=/opt/tender_engine/
WAREHOUSE_PATH=data/warehouse/procurement.duckdb
DASHBOARD_EXPORT_DIR=data/export/
```

Do not place real API keys, tokens, passwords, SSH keys, or private keys in committed files.

## Run Tests

```powershell
python -m unittest discover -s tests
```

## Run The Pipeline Manually

If `run_pipeline.py` is present in your working copy, run:

```powershell
python run_pipeline.py
```

For the enrichment CLI in this local copy:

```powershell
python cli.py --company "Example Ltd" --domain example.com
```

Batch enrichment:

```powershell
python cli.py --batch companies.csv --output enriched_output.csv
```

Hermes batch runner:

```powershell
python scripts/run_hermes.py --input data/leads/companies.csv
```

Treat batch inputs and outputs as private business data unless deliberately sanitized.

## Dashboard And Exports

Dashboard/export artifacts are runtime outputs, not source files.

- Tender/dashboard exports should live under `data/export/`.
- Hermes run reports are written under `data/hermes/runs/<run_id>/`.
- Local warehouse files live under `data/warehouse/`.

These paths are ignored for GitHub upload. Commit dashboard frontend source files if they exist, but do not commit generated exports, HTML reports containing private data, SQLite/DuckDB files, or raw tender/customer/outreach data.

## Security

Before committing or pushing:

```powershell
git status --short --ignored
git add -n .
python .githooks/pre_commit_secret_scan.py
```

Do not commit:

- `.env` or `.env.*` files other than `.env.example`
- API keys, tokens, passwords, private keys, or SSH keys
- `data/`, `measurement_runs/`, local warehouse files, or raw exports
- logs, caches, virtual environments, `node_modules`, build outputs, or archives
