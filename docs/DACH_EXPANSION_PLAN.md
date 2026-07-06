# DACH Expansion Plan

## Objective

Prepare ProcessEd Intelligence for DACH expansion as public procurement intelligence for construction/civils teams across DACH.

The current TenderNed demo remains untouched. This plan layers discovery, prototype adapters, normalized exports, dashboard filtering, and sales enablement through separate scripts, docs, and tests without changing the existing TenderNed/Hostinger static demo flow.

## Expansion Sequence

1. Germany first.
2. Switzerland second.
3. Austria third.

## Why This Order

Germany should lead because it has the biggest contractor and procurement market in DACH, with the largest potential volume of construction and civils notices.

Switzerland should follow because it is strong for premium/private-enterprise intelligence, where high-value construction, infrastructure, property, and specialist contractor opportunities can support a differentiated intelligence product.

Austria should come later as a smaller extension once Germany and Switzerland have proven the source discovery, normalization, and commercial workflow.

## Product Positioning

ProcessEd Intelligence should position DACH coverage as:

> public procurement intelligence for construction/civils teams across DACH.

The core promise is early, structured, and commercially useful tender intelligence for teams that need to track public-sector and adjacent enterprise opportunities without manually checking fragmented portals.

## Phased Delivery

### Phase 1: Source Discovery Only

- Identify primary national, regional, sector-specific, and private-enterprise procurement sources for Germany, Switzerland, and Austria.
- Record whether each source offers API, RSS, bulk download, searchable web pages, or manual-only portal access.
- Capture authentication, terms, scraping, language, and usefulness notes before building any collector.

### Phase 2: Adapter Prototypes

- Build separate prototype scripts for high-confidence sources only.
- Keep prototypes outside `run_pipeline.py`.
- Do not wire prototype data into the current TenderNed/Hostinger demo.
- Validate extraction of the required fields before investing in scale or scheduling.

### Phase 3: Normalized Export

- Convert source-specific notices into the DACH normalized tender object.
- Preserve source references and raw IDs for auditability.
- Export static JSON/CSV artifacts in a backward-compatible way, separate from the existing dashboard data unless a later phase adds compatible fields.

### Phase 4: Dashboard Country Filter

- Add a country filter only after normalized DACH exports are stable.
- Keep the static Hostinger architecture.
- Treat any dashboard schema changes as additive and backward-compatible.
- Confirm the TenderNed demo remains untouched before merging dashboard work.

### Phase 5: DACH Sales/Outreach Pack

- Create country-specific sales messaging for Germany, Switzerland, and Austria.
- Prioritize construction/civils contractors, infrastructure suppliers, consultants, and bid teams.
- Include market-specific examples, source coverage notes, and buyer intelligence angles.

## Key Risks

- Language coverage across German, French, Italian, and localized terminology.
- Portal fragmentation across federal, state, cantonal, municipal, utility, and private-enterprise sources.
- eForms/TED differences across notice types, publication formats, and field completeness.
- CPV translation and sector mapping for construction/civils relevance.
- Buyer naming inconsistencies across authorities, regions, and source portals.
- Duplicate notices across national portals, TED/eForms, and regional mirrors.
- Stale or expired notices appearing in searches, exports, and cached source pages.

## Guardrails

- The current TenderNed demo remains untouched.
- Do not modify `run_pipeline.py`.
- Do not break the current TenderNed/Hostinger demo.
- Keep the static Hostinger architecture.
- Layer DACH work through separate scripts, docs, and tests.
- Do not commit raw databases, logs, secrets, caches, or generated large exports.
