# ProcessEd 90-Day Build Blueprint (SME-First)
Date: 2026-04-01  
Mode: Decision-complete execution spec  
Primary wedge: SME-first commercialization

## 1) Build Outcome

Deliver a production operating system that:

1. Converts procurement data into explainable BID/REVIEW/NO_BID decisions for SME users.
2. Preserves legal/audit-grade provenance so outputs can support institutional and forensic expansion.
3. Produces measurable commercial outcomes (reply, call, pilot, paid conversion) within 90 days.

## 2) Architecture Principles (Locked)

1. Deterministic core first, optional AI enrichment second.
2. Every decision must be explainable and traceable to source records.
3. Notification failures are non-fatal; core pipeline failures are fatal.
4. One shared data spine for SME, institutional, and forensic surfaces.
5. Compliance controls are product logic, not policy-only documentation.

## 3) Canonical Public Interfaces (Source of Truth)

### 3.1 `ProcurementOpportunity`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `opportunity_id` | string | yes | Internal canonical ID |
| `source` | enum(`cf`,`fts`,`other`) | yes | Origin source |
| `source_notice_id` | string | yes | Source notice/release identifier |
| `ocid` | string | no | OCDS identifier if available |
| `buyer_name` | string | yes | Canonical buyer label |
| `title` | string | yes | Opportunity title |
| `region` | string | no | Normalized region |
| `value_amount` | number | no | Numeric value |
| `value_currency` | string | no | Currency code |
| `deadline_at` | datetime (UTC ISO 8601) | no | Bid deadline |
| `status` | string | no | Normalized status |
| `release_tags` | array[string] | no | Source tags |
| `source_url` | string | yes | Notice URL |
| `published_at` | datetime (UTC ISO 8601) | no | Notice publish date |
| `updated_at` | datetime (UTC ISO 8601) | yes | Last update seen |
| `ingested_at` | datetime (UTC ISO 8601) | yes | Internal ingest timestamp |

### 3.2 `DecisionEvent`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `decision_id` | string | yes | Unique decision event ID |
| `opportunity_id` | string | yes | FK to `ProcurementOpportunity` |
| `verdict` | enum(`BID`,`REVIEW`,`NO_BID`) | yes | Final decision |
| `confidence` | integer (0-100) | yes | Decision confidence |
| `reason_codes` | array[string] | yes | Deterministic reasons |
| `risk_flags` | array[string] | no | Risk annotations |
| `score_total` | number | yes | Decision input score |
| `scoring_version` | string | yes | Scoring ruleset version |
| `model_version` | string | no | AI model version if enrichment used |
| `provenance_refs` | array[string] | yes | Source references used |
| `decided_at` | datetime (UTC ISO 8601) | yes | Decision timestamp |

### 3.3 `SupplierEntity`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `supplier_id` | string | yes | Canonical supplier ID |
| `legal_name` | string | yes | Canonical legal name |
| `aliases` | array[string] | no | Alternate names |
| `registration_number` | string | no | Companies House/company number |
| `country` | string | no | Jurisdiction |
| `owner_links` | array[string] | no | Ownership IDs/refs |
| `sanctions_markers` | array[string] | no | Sanctions/PEP markers |
| `debarment_markers` | array[string] | no | Debarment/exclusion markers |
| `performance_markers` | array[string] | no | Performance notice markers |
| `updated_at` | datetime (UTC ISO 8601) | yes | Last refresh |

### 3.4 `RiskSignal`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `risk_signal_id` | string | yes | Unique signal ID |
| `subject_type` | enum(`opportunity`,`supplier`,`buyer`) | yes | Entity type |
| `subject_id` | string | yes | FK to subject entity |
| `signal_type` | string | yes | e.g., repeated_winner, tight_deadline |
| `severity` | enum(`low`,`medium`,`high`,`critical`) | yes | Signal severity |
| `confidence` | integer (0-100) | yes | Signal confidence |
| `evidence_source` | string | yes | Source reference |
| `created_at` | datetime (UTC ISO 8601) | yes | Signal creation time |

### 3.5 `LeadActivationRecord`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `lead_id` | string | yes | Lead record ID |
| `account_name` | string | yes | Company/account |
| `contact_name` | string | no | Contact name |
| `contact_channel` | enum(`email`,`linkedin`,`phone`) | yes | Outreach channel |
| `lawful_basis_path` | string | yes | Compliance rationale path ID |
| `outreach_stage` | enum(`D1`,`D2`,`D3`,`D4`,`D5`,`D6`,`D7`,`closed`) | yes | Sequence stage |
| `suppression_state` | enum(`active`,`suppressed`,`opted_out`) | yes | Suppression status |
| `response_status` | enum(`none`,`replied`,`positive`,`negative`,`stop`) | yes | Response state |
| `call_booked` | boolean | yes | Call booked flag |
| `pilot_started` | boolean | yes | Pilot started flag |
| `last_contacted_at` | datetime (UTC ISO 8601) | no | Last outreach timestamp |

## 4) Execution Tracks and Owners

### Track A: Data and graph foundation
Owner: Data engineering lead

Scope:
- Harden ingest and normalization for CF/FTS.
- Introduce provenance references for all canonical entities.
- Build base supplier and opportunity linkage keys.

Exit criteria:
- Freshness and quality SLOs green for 4 consecutive weeks.
- Provenance completeness >= 98%.
- Entity linkage confidence tags present on all linked records.

### Track B: Decision and explainability engine
Owner: Decision systems lead

Scope:
- Persist `DecisionEvent` for every shortlisted record.
- Standardize reason codes and risk flags.
- Version scoring and decision rules.

Exit criteria:
- 100% decision explainability coverage.
- 0 silent decision paths.
- Decision logs replayable from source references.

### Track C: SME revenue product and workflow
Owner: Product + commercial ops lead

Scope:
- 7-day pilot onboarding flow.
- Notification and action workflow.
- Sequence-to-conversion instrumentation.

Exit criteria:
- Pilot activation within 24h SLA.
- End-to-end conversion funnel measurable daily.
- Minimum 3 active pilots running in steady cadence.

### Track D: Compliance and governance controls
Owner: Compliance ops lead

Scope:
- Enforce lawful basis and suppression in lead activation workflow.
- Preserve outreach audit trails.
- Standardize opt-out and objection handling.

Exit criteria:
- 0 suppression violations.
- 100% outbound messages include opt-out control.
- Opt-out SLA met on every case.

### Track E: GTM and conversion operations
Owner: Growth ops lead

Scope:
- Daily outreach execution loop.
- Weekly message and targeting optimization.
- Offer packaging and close scripts.

Exit criteria:
- Weekly outreach and conversion dashboard in production.
- Repeatable pipeline from outreach to paid conversion.
- Pilot-to-paid decision rule documented and used.

## 5) 30/60/90 Implementation (Locked)

## Days 0-30 (Foundation)

Build outcomes:
1. Stabilize ingest/normalize freshness and quality SLOs.
2. Formalize decision event logging and provenance.
3. Launch pilot packaging and outreach cadence.

Deliverables:
- Canonical interfaces implemented in data contracts.
- Decision event persistence and versioning.
- Daily operator loop for outreach live.

SLO targets:
- Pipeline success rate >= 99%.
- CF freshness lag <= 6h.
- FTS freshness lag <= 6h.
- Dedupe precision >= 99.5%.

## Days 31-60 (Revenue)

Build outcomes:
1. Run active SME pilots continuously.
2. Instrument conversion funnel from first touch to paid.
3. Tighten scoring from outcome feedback.

Deliverables:
- Conversion event schema and dashboard.
- Weekly score calibration routine.
- Offer and objection scripts standardized.

Commercial targets:
- Reply rate >= 8%.
- Calls booked >= 1 per day average.
- Pilot start rate >= 20% of qualified calls.

## Days 61-90 (Expansion readiness)

Build outcomes:
1. Release supplier-risk alpha overlays (performance/debarment/ownership context).
2. Publish first forensic-style intelligence template.
3. Prepare API/data product readiness pack.

Deliverables:
- Institutional alpha views from existing data spine.
- Forensic report template with provenance trace.
- API readiness checklist and schema docs.

Readiness targets:
- Institutional alpha pack produced from current data model.
- Forensic output reproducible from `DecisionEvent` + `RiskSignal`.
- API licensing prerequisites documented and testable.

## 6) Acceptance Gates and Test Protocol

### Gate A: Strategic memo tests

- Includes 3 quantified market-sizing views with cited logic.
- Includes 12+ competitors in 4 clusters.
- Includes 5+ underserved segments and 3+ non-obvious intersections.
- Includes explicit best wedge, second wedge, and moat path.

### Gate B: Blueprint tests

- 30/60/90 leaves zero unresolved implementation decisions.
- Every track has owner, outputs, metrics, and exit criteria.
- Canonical interfaces are explicit and reusable.

### Gate C: Operational scenario checks

1. No-new-tenders day: pipeline remains trustworthy and status is explicit.
2. High-volume burst: decision and dedupe quality remains within thresholds.
3. Compliance objection/opt-out: suppression state blocks outreach immediately.

### Gate D: Commercial scenario checks

1. Pilot-to-paid decision framework is explicit and applied weekly.
2. SME-first GTM supports institutional expansion without re-architecture.
3. Forensic/institutional outputs can be generated from same provenance spine.

## 7) Runbook: Weekly Operating Rhythm

Monday:
- Review reliability SLOs, freshness, dedupe precision.
- Lock outreach target list and sequence plan.

Wednesday:
- Review decision quality and response signals.
- Recalibrate scoring thresholds if needed.

Friday:
- Review commercial funnel metrics and pilot outcomes.
- Decide next-week focus by objective evidence (not intuition).

End-of-week artifact:
- One-page execution summary with green/yellow/red by track.

## 8) Non-Negotiables

1. No change ships without provenance and explainability impact assessed.
2. No outreach sends without suppression check.
3. No KPI reporting without definition, owner, and source of truth.
4. No wedge switching until SME-first metrics pass threshold for 3 consecutive weeks.
