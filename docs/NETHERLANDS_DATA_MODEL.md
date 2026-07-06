# Netherlands Data Model

Status: demo schema for Netherlands expansion artifacts. Sample opportunity records are not verified live coverage.

## Fixture Location

`data/dutch/demo/dutch_demo_opportunities.json`

The fixture is the source for the local dashboard bundle. It is intentionally separate from existing UK, DACH, and sales tracker artifacts.

## Opportunity Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| id | string | yes | Stable demo identifier, prefixed with `NL-DEMO` or `EU-DEMO`. |
| title | string | yes | English-readable opportunity title. |
| buyer | string | yes | Public buyer or contracting authority name. |
| country | string | yes | `Netherlands` or EU/cross-border label. |
| region | string | yes | Dutch province, municipality, or cross-border area. |
| source | string | yes | TenderNed, TED/EU notices, or EU Public Procurement Data Space sample. |
| notice_url | string | yes | Public placeholder/source URL. Demo URLs may be illustrative. |
| deadline | string | yes | ISO date. |
| published_at | string | yes | ISO date. |
| cpv_codes | array[string] | yes | One or more CPV codes. |
| category | string | yes | Normalized category for dashboard grouping. |
| estimated_value_eur | number | yes | Demo estimate in EUR. |
| estimated_value_gbp | number | yes | Demo estimate in GBP. |
| language | string | yes | Primary notice language. |
| summary_en | string | yes | English summary for UK/EU commercial users. |
| summary_nl | string | yes | Dutch summary for local review. |
| fit_score | number | yes | 0-100 ProcessEd demo fit score. |
| urgency | string | yes | `high`, `medium`, or `low`. |
| recommended_action | string | yes | Suggested next commercial step. |
| buyer_signal | string | yes | Buyer intent or relationship clue. |
| expansion_relevance | string | yes | Why the opportunity matters for Netherlands entry. |
| data_status | string | yes | Must make demo/non-live status explicit. |

## Bundle Shape

`scripts/build_dutch_demo_bundle.py` reads the fixture and outreach segment CSV, then writes:

- `data/export/dutch_demo_bundle/dutch_dashboard_data.json`
- `data/export/dutch_demo_bundle/dutch_dashboard_data.js`
- `data/export/dutch_demo_bundle/index.html`

The dashboard data contains:

- `metadata`
- `kpis`
- `source_coverage`
- `outreach_segments`
- `opportunities`

## Scoring Notes

Fit score is a demo heuristic, not a predictive model. Higher scores indicate stronger alignment with the Netherlands expansion wedge:

- Public works, infrastructure, drainage, water, roads, or civils scope.
- Clear contracting authority.
- Near-term deadline.
- Cross-border relevance or repeat buyer signal.
- Sufficient estimated value to justify qualification effort.

## Future Production Extensions

- Add source notice identifiers and publication versioning.
- Add buyer entity normalization and deduplication.
- Add source attribution and license metadata.
- Add language detection confidence and translation review status.
- Add CPV parent/child expansion.
- Add contact and partner eligibility only after privacy review.
