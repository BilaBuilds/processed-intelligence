# Claude Context

ProcessEd Intelligence is a procurement intelligence and enrichment project. Prefer pipeline-safe, small, testable changes.

## Project Structure Quick Reference

```text
README.md                         Public project overview
.env.example                      Public environment template only
enrichment/                       Enrichment package
enrichment/cli.py                 CLI and provider waterfall setup
enrichment/waterfall.py           Waterfall enrichment orchestration
enrichment/cache.py               Local SQLite enrichment cache
enrichment/storage/evidence_ledger.py
                                  Local evidence ledger
enrichment/agents/                Hermes/account/outreach agents
scripts/                          Operational scripts and migrations
src/                              Supporting classifier code
tests/                            Unit tests
docs/                             Documentation and handoff notes
warehouse/procurement_intelligence_schema.sql
                                  Target warehouse schema
```

Known project facts:

- Intended pipeline entry point: `run_pipeline.py`
- Historical VPS root: `/opt/tender_engine/`
- Warehouse path: `data/warehouse/procurement.duckdb` or `data/warehouse/procurement.db`
- Dashboard export path: `data/export/`

Note: `run_pipeline.py` was not present in this local copy during the documentation pass. Do not invent it; if absent, work with the visible scripts and package.

## Data Schema Snapshot

Target warehouse schema is documented in `warehouse/procurement_intelligence_schema.sql`. Major target tables include:

- Source/raw ingest: `source_systems`, `raw_ingest_events`
- Buyer/supplier identity: `buyers`, `buyer_aliases`, `suppliers`, `supplier_aliases`
- Tender core: `tenders`, `tender_source_records`, `tender_versions`, `tender_amendments`, `tender_lots`
- Classification and geography: `cpv_codes`, `regions`, `tender_cpv_codes`, `tender_regions`
- Frameworks and awards: `frameworks`, `framework_lots`, `framework_suppliers`, `tender_framework_links`, `awards`, `award_suppliers`
- Documents/evidence: `documents`, `document_extractions`, `evidence_ledger`
- Client outputs: `client_profiles`, `client_preferences`, `opportunity_scores`, `alerts`, `briefing_runs`
- Outreach and automation: `outreach_memory`, `agent_runs`

Current local operational stores:

- `enrichment_cache`: `company_name`, `domain`, `record_json`, `source`, `cached_at`; primary key is `(company_name, domain)`.
- Local `evidence_ledger`: `id`, entity fields, source fields, confidence, timestamps, client safety, run id, conflict flag.
- `suppression_list`: `email`, `reason`, `added_at`, `source`.

Do not commit database files. The schema can be committed; runtime warehouse/cache files cannot.

## Known Gotchas And Workarounds

- Use `python3 << 'PYSCRIPT'` for remote Python heredocs instead of fragile pasted heredocs.
- If `crontab -e` fails over SSH, use a grep-filtered temp file, then `crontab /tmp/cron.tmp`.
- Tenders live under `data.get("opportunities", [])` in `shortlist.json`.
- `run_log` insert needs 8 values including `completed_at`.
- Runtime exports, dashboards, machine traces, local memories, and outreach drafts may contain private data even when file sizes are small.

## Current Blockers And Active Work

Blockers:

- VPS access is no longer available.
- `run_pipeline.py` is referenced as the pipeline entry point but was not present in this local copy.
- Warehouse files and dashboard exports are local runtime artifacts and must remain outside Git.

Active work:

- Dashboard overhaul
- Disk usage monitoring
- LinkedIn B2B outreach tracker
- Dutch market entry exploration

## Coding Instructions

- Pipeline-first: preserve the existing pipeline contract and data flow.
- Do not modify `run_pipeline.py` unless necessary. If it is absent, do not create a replacement without a clear task.
- Add new features as separate scripts or isolated modules where possible.
- Use Python for project automation and data processing.
- Keep changes small, reversible, and testable.
- Add or update tests for behavior changes.
- Do not commit secrets, real credentials, `.env`, private keys, warehouse data, raw tender data, customer/outreach data, logs, caches, or generated exports.
- Prefer config templates and documented paths over hardcoded local machine paths.
