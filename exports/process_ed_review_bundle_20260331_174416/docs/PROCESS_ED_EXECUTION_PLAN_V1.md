# ProcessEd - API-First Execution Plan (Revenue + Compliance)
Date: 2026-03-31
Owner: Bilal (CEO/Orchestrator)
Prepared by: AI Engineering Copilot

## Objective
Build a compliance-first, API-first lead activation system on top of the existing tender intelligence engine so ProcessEd can generate revenue reliably without legal shortcuts or brittle scraping hacks.

## Current baseline (already strong)
1. Tender pipeline runs end-to-end (`ingest -> normalize -> match -> select -> decision -> dedupe -> notify`).
2. Decision layer is live (BID/REVIEW/NO_BID + confidence + risk flags).
3. Discord notifications are decision-aware.
4. Dedupe and idempotency controls are in place.
5. Audit artifacts (`run_manifest.json`) are generated every run.

## Why no contractor lead scraper was built first
1. Tender APIs were cleaner and delivered fastest value.
2. Lead scraping introduces higher compliance risk (GDPR/PECR, suppression handling).
3. Unstructured web lead scraping creates data-quality debt (bad emails, duplicates, stale contacts).
4. API-first architecture gives better reliability and auditability for enterprise clients.

## Phase plan

### Phase A (Week 1-2): Compliance and governance foundation
Deliverables:
1. Data map and records of processing:
   - categories of data
   - purpose
   - lawful basis
   - retention
2. Direct marketing control pack:
   - suppression workflow
   - opt-out handling
   - right-to-object handling
3. Compliance gate in code:
   - `src/leads_compliance.py`
   - unit tests

Exit criteria:
1. No outbound lead can be activated without passing compliance gate.
2. Suppressed leads are blocked by design.
3. Governance checklist signed off.

### Phase B (Week 2-4): API-first lead ingestion
Deliverables:
1. `src/leads_ingest.py` (API adapters only)
2. `state/leads.db` (canonical lead store)
3. `src/leads_enrich.py` (normalization + dedupe + quality scoring)
4. `src/leads_score.py` (fit scoring against ICP)

Primary data sources:
1. Companies House API (entity metadata)
2. Existing tender data (buyers, awards, supplier relationships)
3. Optional compliant data vendors for business contacts (contracted DPA required)

Exit criteria:
1. 500 clean leads in DB with confidence scores.
2. Duplicate rate < 5%.
3. All rows have source provenance.

### Phase C (Week 4-6): Outreach activation
Deliverables:
1. `src/outreach_queue.py`
2. daily send plan with per-domain/per-recipient throttles
3. mandatory footer and unsubscribe handling
4. campaign analytics table (opens, replies, positive intent, meetings)

Exit criteria:
1. 30 qualified outreach sends/day with logging.
2. unsubscribe honored within SLA.
3. no suppressed lead sends.

### Phase D (Week 6-8): Revenue engine and conversion ops
Deliverables:
1. Offer packaging (Pilot, Weekly Intel Pack, Managed Desk)
2. CRM handoff format and pipeline stages
3. weekly KPI review dashboard

Revenue KPIs:
1. outreach -> reply rate
2. reply -> meeting rate
3. meeting -> paid pilot conversion
4. pilot -> retained monthly client conversion

## Architecture additions (new modules)
1. `src/leads_ingest.py`
2. `src/leads_enrich.py`
3. `src/leads_score.py`
4. `src/outreach_queue.py`
5. `src/leads_compliance.py` (already added)
6. `tests/test_leads_compliance.py` (already added)

## Data contracts
Lead record fields (minimum):
1. `lead_id`
2. `company_name`
3. `domain`
4. `email`
5. `subscriber_type` (`corporate`/`individual`/`unknown`)
6. `source`
7. `source_ref`
8. `fit_score`
9. `compliance_status`
10. `suppressed`
11. `last_contacted_at`

## Compliance gates (non-negotiable)
1. Suppression list check before send.
2. Sender identity clear in every message.
3. Opt-out mechanism in every message.
4. Individual/unknown subscriber path requires consent or soft-opt-in eligibility.
5. Privacy information must be available at or before first contact.
6. Governance docs maintained and reviewable.

## Operational runbook
Daily:
1. Run tender pipeline.
2. Run lead ingestion/enrichment.
3. Generate outreach queue from compliant leads.
4. Send capped campaign batch.
5. Log outcomes.

Weekly:
1. Run audit script.
2. Review KPI deltas.
3. Tune score thresholds and exclusions.
4. Review compliance incidents and suppression events.

## Review gates (for external reviewers)
Gate 1 - Architecture:
1. module boundaries
2. data contracts
3. idempotency

Gate 2 - Compliance:
1. lawful basis mapping
2. suppression enforcement
3. auditability

Gate 3 - Revenue:
1. lead quality
2. outreach performance
3. conversion quality

