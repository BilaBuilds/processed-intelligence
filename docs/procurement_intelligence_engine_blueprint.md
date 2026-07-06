# ProcessEd Procurement Intelligence Engine Blueprint

## 1. Current-System Diagnosis

Current Hermes is a contact/outreach enrichment system. It is useful, but it is not yet a procurement intelligence engine.

Hard gaps:

- No tender warehouse. Current durable state is CSV, JSON artifacts, cache SQLite, and run folders.
- No buyer/supplier/award history model.
- No source-level provenance across tender lifecycle events.
- No amendment tracking.
- No framework intelligence.
- No CPV/region taxonomy as first-class data.
- No client-specific opportunity scoring history.
- No award-winner/incumbent memory.
- No evidence ledger that can defend every output claim.
- No event-driven orchestrator. Current operation is mostly batch execution and file-based tasks.
- No serious document extraction layer for PDFs, procurement packs, specifications, schedules, or pricing docs.

Current strengths to keep:

- Evidence-backed mindset.
- Draft-only outreach safety.
- Machine trace output.
- Account intelligence shape: strengths, gaps, priority score, next action.
- Agent registry and operating model.

## 2. Ideal Target Architecture

Target architecture: event-driven evidence-to-action system.

Core loop:

1. Ingest raw public-source records.
2. Preserve raw payloads permanently.
3. Resolve tender, buyer, supplier, framework, document, and award entities.
4. Build evidence ledger claims.
5. Enrich opportunity intelligence.
6. Score per client profile.
7. Emit alerts, reports, briefs, and outreach angles.
8. Learn from outcomes and client feedback.

Main subsystems:

- Ingestion: APIs, RSS, bulk files, portal monitors, page monitors, manual seeds.
- Warehouse: PostgreSQL with immutable raw records and derived intelligence tables.
- Evidence ledger: every claim has source, confidence, timestamp, reasoning note, and claim type.
- Agent graph: async jobs selected by expected value and evidence gaps.
- Client product outputs: JSON, dashboard, weekly PDF, alert email, buyer report, opportunity report.
- Memory: buyer behaviour, supplier wins, client preferences, alert outcomes, outreach outcomes.

## 3. Warehouse / Database Schema

Target DDL lives at `warehouse/procurement_intelligence_schema.sql`.

Core permanent storage:

- `source_systems`: every upstream data source and access method.
- `raw_ingest_events`: immutable source payloads with hash, URL, fetch time, and raw JSON.
- `buyers`, `buyer_aliases`: canonical authorities, aliases, PPON, region, domain.
- `suppliers`, `supplier_aliases`: award winners, likely competitors, framework suppliers.
- `tenders`: canonical opportunity entity.
- `tender_source_records`: links a tender to source notices and IDs.
- `tender_versions`: every changed notice payload.
- `tender_amendments`: commercial changes: deadline, value, title, scope, buyer, documents.
- `tender_lots`: lot-level opportunity records.
- `cpv_codes`, `tender_cpv_codes`: observed and inferred category intelligence.
- `regions`, `tender_regions`: place of performance and client territory matching.
- `frameworks`, `framework_lots`, `framework_suppliers`, `tender_framework_links`: route-to-market intelligence.
- `awards`, `award_suppliers`: winner and incumbent history.
- `documents`, `document_extractions`: attachments and extracted procurement-pack text.
- `evidence_ledger`: defensible claims for all derived intelligence.
- `client_profiles`, `client_preferences`: what each paying contractor cares about.
- `opportunity_scores`: scoring history by tender and client.
- `alerts`: generated commercial alerts and status.
- `briefing_runs`: weekly client-ready briefings.
- `outreach_memory`: buyer/contact/outcome memory.
- `agent_runs`: operational audit trail.

Commercial-value priority fields:

- Buyer canonical identity and aliases.
- Tender deadline, value band, region, CPV, procurement stage.
- Award winner, supplier aliases, award value.
- Framework/lot/supplier eligibility.
- Similar past contracts.
- Incumbent likelihood.
- Client fit score and reasons.
- Evidence confidence and source trace.
- Amendment/change impact.

Deduplication strategy:

- Source-level dedupe: `(source_id, source_record_id)` and raw `content_hash`.
- Tender-level dedupe: canonical `dedupe_key` from OCID/notice ID when present; fallback to normalized buyer, normalized title, deadline, value band, region.
- Buyer dedupe: PPON first; normalized name + region/domain second.
- Supplier dedupe: Companies House number first; normalized name + domain second.
- Framework dedupe: normalized framework name + start/end date + owner.
- Award dedupe: source award ID first; fallback buyer + supplier + title + value + award date.

Migration plan from current system:

1. Create PostgreSQL database and run target DDL.
2. Seed `source_systems` from `data/source_catalog/procurement_sources.json`.
3. Load existing Hermes run artifacts as `raw_ingest_events` with source `hermes_legacy`.
4. Convert each `machine_trace.json` claim into `evidence_ledger`.
5. Create initial `suppliers` from enriched companies.
6. Create `outreach_memory` from draft sync logs.
7. Keep current SQLite cache only as temporary provider cache; warehouse becomes source of truth.
8. Add tender ingestion tables before changing user-facing outputs.
9. Backfill official notice history before building competitor reports.
10. Only after history exists, sell buyer/supplier intelligence.

## 4. New Data Sources To Add

Highest-value official/core sources:

1. Find a Tender OCDS API: national lifecycle notices, Procurement Act notice types.
2. Contracts Finder API/OCDS: below-threshold England, awards, SME/VCSE flags.
3. Public Contracts Scotland: Scottish regulated procurement, downloads/API.
4. Sell2Wales API: Welsh authorities, Welsh NHS, colleges, linked public opportunities.
5. eTendersNI: Northern Ireland government and arms-length bodies.
6. NHS Atamis: estates, maintenance, health-sector procurement routes.
7. Local authority procurement pipelines: overlooked forward work, often CSV/PDF/XLSX.
8. National Highways pipelines and market engagement.
9. Homes England commercial pipeline.
10. Construction framework providers: SCAPE, Pagabo, Procure Partnerships, LHC, Fusion21, CHIC, PfH, ESPO, YPO, NEPO.
11. Award notice history across all portals.
12. Planning portals, committee papers, capital programmes.

Source catalog lives at `data/source_catalog/procurement_sources.json`.

Update cadence:

- Official notice APIs: hourly.
- Award backfill: daily.
- Framework pages: weekly.
- Local authority pipelines: weekly page monitor, monthly full refresh.
- Planning/capital programme sources: weekly.
- NHS Atamis and portal sources: daily.

## 5. Enrichment Pipeline Design

Raw tender to intelligence product:

1. Normalize raw notice and preserve original.
2. Resolve tender entity.
3. Resolve buyer.
4. Resolve supplier/award entities if present.
5. Extract documents and attachments.
6. Classify CPV and work category.
7. Map region and place of performance.
8. Link to framework if framework terms, route, buyer, or supplier list matches.
9. Backfill buyer procurement history.
10. Backfill award/winner history.
11. Detect likely incumbent from similar previous awards.
12. Match similar past contracts.
13. Estimate value if missing.
14. Estimate urgency from deadline, stage, clarification dates, and market engagement dates.
15. Estimate bid difficulty.
16. Estimate competition risk.
17. Score against client profile.
18. Generate commercial angle.
19. Generate evidence-backed explanation.
20. Adversarial verifier blocks unsupported claims.

Every enriched field must include:

- `source_id`
- `source_record_id`
- `confidence`
- `observed_at`
- `reasoning_note`
- `claim_kind`: observed, inferred, or estimated
- `extractor`

## 6. Agent Architecture

Agents are services with durable state, not renamed functions.

| Agent | Runs | Reads | Writes | Evidence Required | Failure Mode |
| --- | --- | --- | --- | --- | --- |
| Source Budgeter | scheduled + event | source stats, client profiles | agent_runs | source freshness/cost | over-polls noisy sources |
| Tender Entity Resolver | sync on ingest | raw_ingest_events | tenders, tender_source_records | IDs, title, buyer, deadline | bad merge/split |
| Buyer Resolver | async | tenders, source records | buyers, buyer_aliases | PPON/name/domain/address | authority alias drift |
| Supplier/Award Resolver | async | awards, suppliers | suppliers, award_suppliers | award notice fields | supplier alias collision |
| Evidence Harvester | async | raw records, documents | evidence_ledger | source links | partial extraction |
| Evidence Graph Builder | async | evidence_ledger | machine trace / graph view | claims | stale claims |
| Document Extractor | async | documents | document_extractions | extracted spans | OCR/PDF failure |
| CPV/Sector Classifier | sync + async | title, desc, docs | tender_cpv_codes, evidence | observed/inferred CPV | overclassification |
| Region Classifier | sync | locations, postcodes | tender_regions | location source | ambiguous multi-region work |
| Similar Contract Matcher | async | tenders, awards | evidence, scores | vector/text match | false similarity |
| Incumbent Detector | async | awards, frameworks | evidence | previous winners | overclaims incumbent |
| Opportunity Fit Scorer | sync per client | tender, client profile | opportunity_scores | scored reason JSON | generic scores |
| Commercial Angle Agent | sync after score | scores, evidence | evidence, alert body | claim support | weak angle |
| Client Alert Agent | scheduled/event | scores, preferences | alerts | threshold/evidence | alert fatigue |
| Adversarial Verifier | sync gate | proposed outputs | evidence ledger verdict | claim entailment | false pass |
| Dashboard Publisher | scheduled | warehouse views | JSON/API cache | current scores | stale dashboard |
| Briefing Generator | weekly | alerts, scores | briefing_runs | evidence-backed summaries | bloated briefs |
| Outcome Learner | event | outcomes, feedback | preferences, memory | reply/client action | wrong feedback attribution |
| Memory Curator | scheduled | all history | compact memory views | traceable summaries | memory drift |

Orchestrator:

- Event-driven graph, not linear batch.
- State object per tender, buyer, supplier, framework, and client.
- Next action selected by expected value:
  `commercial_value_gain - source_cost - latency_penalty - risk_penalty`.
- Missing evidence, freshness, client relevance, and deadline urgency raise priority.
- Low-fit opportunities stop early.

## 7. Evidence Ledger Design

Evidence ledger is the product's trust layer.

Each claim:

- Subject type: tender, buyer, supplier, framework, client, alert.
- Subject ID.
- Claim key: `deadline`, `likely_incumbent`, `work_category`, `region`, `buyer_history`, etc.
- Claim value JSON.
- Claim kind: observed, inferred, estimated.
- Source.
- Document/span where available.
- Confidence.
- Reasoning note.
- Timestamp.
- Extractor/agent.

Client outputs can only use ledger claims. If a sentence cannot be traced to ledger claims, it is blocked.

## 8. Scoring Model

Score per tender per client.

Suggested v1 weights:

- Contractor fit: 25
- Work category relevance: 15
- Region fit: 10
- Value fit: 10
- Deadline/urgency: 10
- Buyer relationship potential: 10
- Incumbent/competition risk: 10
- Evidence strength: 5
- Framework accessibility: 5

Penalty rules:

- Portal-only and no relationship angle: cap score at 70.
- Not on relevant closed framework: cap score at 50 unless relationship/pre-market value exists.
- Missing deadline: subtract 8.
- Missing buyer identity: subtract 15.
- Weak construction relevance: cap at 45.
- Suppressed buyer/contact: block outreach, not intelligence.

Recommendation bands:

- 85-100: act now.
- 70-84: review this week.
- 55-69: watch/research.
- 0-54: ignore unless strategic buyer.

## 9. Client-Facing Product Recommendation

Build now:

- Weekly PDF intelligence brief.
- Email alerts for top opportunities and material changes.
- Opportunity report JSON + HTML.
- Buyer report for top 20 target buyers.
- Top 10 opportunities this week.
- Bespoke client-fit shortlist.

Delay:

- Full client portal.
- Complex CRM.
- Bid management workflow.
- Chatbot UI.
- Heavy map UI.

Kill:

- Generic tender-alert website.
- Daily huge alert dumps.
- Unsupported competitor claims.
- Social-media vanity personalization.
- Human-only dashboards that do not feed the machine trace.

Client must get answers:

- Which tenders matter?
- Why this one?
- Who is the buyer?
- Who usually wins similar work?
- Is this worth bidding?
- What is the deadline?
- What is the risk?
- What is the angle?
- What should I do next?

## 10. Implementation Roadmap

### Next 24 Hours

- Land warehouse DDL.
- Seed source catalog.
- Create ingestion job skeleton for Find a Tender and Contracts Finder.
- Create `source_systems` seed loader.
- Add tender entity model and evidence ledger writer.
- Backfill current Hermes machine traces into evidence ledger prototype.

### Next 3 Days

- Implement Find a Tender OCDS ingest.
- Implement Contracts Finder ingest.
- Build tender resolver and buyer resolver.
- Store raw records and tender source links.
- Build CPV/region classifier v1.
- Build opportunity scoring v1 against one dummy client profile.

### Next 7 Days

- Backfill 12-24 months of official award history.
- Build supplier/award resolver.
- Add likely incumbent detector.
- Add similar contract matcher.
- Produce weekly briefing JSON and HTML/PDF draft.
- Add local authority pipeline monitor for 10 priority councils.

### Next 30 Days

- Add Sell2Wales, PCS, eTendersNI.
- Add framework catalog for SCAPE, Pagabo, Procure Partnerships, LHC, Fusion21.
- Add document extraction for tender packs.
- Add client preference UI/input file.
- Build client-ready weekly intelligence brief.
- Add alert feedback/outcome learning.

### After First Paying Customers

- Add portal.
- Add per-client dashboards.
- Add benchmarking across similar contractors.
- Add pricing/estimator signals.
- Add integration with CRM/mailbox.
- Add paid source partnerships if public data is not enough.

## Highest-Leverage Lists

### Top 10 Highest-Leverage Technical Changes

1. PostgreSQL warehouse.
2. Immutable raw ingest.
3. Evidence ledger.
4. Tender/buyer/supplier/entity resolver.
5. Award backfill.
6. Client-specific scoring.
7. Framework linking.
8. Document extraction.
9. Event-driven orchestrator.
10. Outcome learning.

### Top 10 Highest-Value Data Sources

1. Find a Tender OCDS.
2. Contracts Finder.
3. Award notices across portals.
4. Public Contracts Scotland.
5. Sell2Wales.
6. Local authority pipelines.
7. National Highways pipeline.
8. Homes England pipeline.
9. NHS Atamis.
10. Construction framework providers.

### Top 10 Enrichment Fields That Will Make Clients Pay

1. Buyer history.
2. Likely incumbent supplier.
3. Similar past contracts.
4. Framework route and eligibility.
5. Client fit score.
6. Competition risk.
7. Bid difficulty.
8. Deadline urgency.
9. Commercial angle.
10. Evidence-backed next action.

### Fastest Sellable MVP

Weekly client-specific intelligence brief for one construction niche and one region:

- Top 10 opportunities.
- 3 buyer intelligence notes.
- 3 incumbent/competitor signals.
- 3 framework/watchlist alerts.
- Evidence-backed next action for each.

### Long-Term Defensible Moat

The moat is not tender scraping. The moat is longitudinal buyer/supplier/framework memory:

- Who buys what.
- Who wins what.
- Which frameworks route the work.
- Which buyers repeat patterns.
- Which contractors fit which work.
- Which recommendations produced action.
- Which alerts clients ignored or valued.

### Exact Next Engineering Tasks For Codex/Hermes

1. Add Postgres connection/config.
2. Add migration runner.
3. Seed `source_systems`.
4. Implement Find a Tender ingest.
5. Implement Contracts Finder ingest.
6. Implement tender resolver.
7. Implement buyer resolver.
8. Implement evidence ledger writer.
9. Implement scoring v1.
10. Generate first weekly intelligence brief from warehouse data.
