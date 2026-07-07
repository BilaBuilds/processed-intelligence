# Netherlands Live Source Readiness

Status: research_needed/sample_demo roadmap. This pack does not claim verified live TenderNed, TED/EU, PPDS, municipal, water authority, transport, or maintenance coverage.

## Controlled Vertex Use

- Records assessed: 9
- Enrichment mode: Vertex AI Gemini Flash
- Model: gemini-2.5-flash
- Project reference in outputs: configured_via_GOOGLE_CLOUD_PROJECT
- Cost control: `--dry-run` and `--limit N` supported; prompts are concise, low temperature, and request JSON.

## Source-By-Source Assessment

### CPV groups

- Scope: EU/Netherlands taxonomy | CPV filters for construction, roads, drainage, water, maintenance, engineering, and inspection services
- Likely access: Use public CPV taxonomy and source-provided CPV fields; maintain ProcessEd-specific filter groups.
- Difficulty/value/risk: 1/5, 5/5, 1/5
- Credentials: None.
- Likely fields: CPV code; label; parent prefix; ProcessEd category mapping; source-specific occurrence counts after live testing
- Likely gaps: buyer intent; project scope nuance; false-positive control; language-specific title signals
- First test: Use the inventory CPV prefixes as a first ruleset, then measure false positives against 50 manually reviewed notices.
- Caveat: sample_demo research_needed; CPV is a filter/taxonomy layer, not a standalone live source.

### Dutch buyer categories

- Scope: Netherlands internal normalization layer | Internal taxonomy for municipalities, provinces, ministries, Rijkswaterstaat, ports, public transport, water authorities, and public estate bodies
- Likely access: Derived from public buyer names in TenderNed/TED outputs and maintained in project-controlled mapping files.
- Difficulty/value/risk: 2/5, 5/5, 1/5
- Credentials: None for taxonomy maintenance; avoid private contact enrichment without privacy review.
- Likely fields: buyer name; normalized category; likely sector; region; source provenance
- Likely gaps: official entity identifiers; parent/child authority structure; buyer aliases; contact ownership
- First test: Create a 50-buyer alias table from sample/TenderNed/TED records and test dashboard grouping consistency.
- Caveat: sample_demo research_needed; this is not an external source and should not imply live procurement coverage.

### TenderNed

- Scope: Netherlands | Dutch national public procurement notices and contracting authority publication workflows
- Likely access: Public portal and RSS/dataset review first; production API likely needs TenderNed-issued username/password.
- Difficulty/value/risk: 4/5, 5/5, 3/5
- Credentials: Likely credentials for official XML/API access; no credentials for manual public portal review.
- Likely fields: notice title; buyer; publication date; deadline; CPV; procedure; notice identifier; documents/links when published
- Likely gaps: supplier fit score; English summary; normalized buyer category; downstream relationship/contact data; some document details without deeper parsing
- First test: Manually verify 20 current public works notices, then test RSS/dataset/API shape without storing credentials in Git.
- Caveat: research_needed sample_demo not_verified; official access terms and automated-use constraints must be checked before claiming live coverage.

### TED/EU notices

- Scope: EU with Netherlands filtering | EU/TED published notices, especially above-threshold Dutch and cross-border infrastructure procurement
- Likely access: Official TED API for published notices; anonymous access appears available for published notices, while unpublished/manipulation endpoints require API key.
- Difficulty/value/risk: 3/5, 5/5, 2/5
- Credentials: None expected for published-notice search/retrieval pilot; API key may be required for non-public or eSender workflows.
- Likely fields: notice identifier; buyer; country; CPV; procedure; dates; values when disclosed; language; links; eForms fields
- Likely gaps: buyer aliases; practical eligibility interpretation; translations; commercial fit score; local-lot nuance
- First test: Run a Netherlands CPV query for construction, roads, water, maintenance, and compare returned fields against the demo data model.
- Caveat: research_needed not_verified; API availability is a source-access assumption until a live query is executed and logged outside committed artifacts.

### Dutch water authority procurement

- Scope: Netherlands water authorities | Waterschap procurement for flood defence, pumping stations, drainage, treatment works, asset inspection, and maintenance
- Likely access: TenderNed buyer/category filters first; maintain water authority buyer taxonomy and manually verify portal/document access.
- Difficulty/value/risk: 3/5, 5/5, 2/5
- Credentials: No credentials expected for notice discovery; tender-document access may vary by platform.
- Likely fields: buyer; water/civil CPV; location; publication/deadline; procedure; title; notice link
- Likely gaps: asset type classification; local consortium requirements; M&E/civils split; environmental permit nuance
- First test: Build a waterschap buyer alias list and test CPVs 4524, 452324, 452521, 7132 against TenderNed/TED records.
- Caveat: research_needed sample_demo not_verified; water authority scope is a strong hypothesis, not verified live coverage.

### Dutch infrastructure/transport procurement

- Scope: Netherlands national and regional infrastructure buyers | Rijkswaterstaat, provinces, transport authorities, ports, roads, waterways, bridges, tunnels, and mobility projects
- Likely access: TenderNed/TED first, then buyer-specific portals for document and framework nuance after access review.
- Difficulty/value/risk: 4/5, 5/5, 3/5
- Credentials: Notice discovery likely public; platform accounts may be needed for documents, Q&A, or bid participation.
- Likely fields: buyer; project title; CPV; NUTS/region; value where disclosed; deadline; notice type; procedure
- Likely gaps: framework call-off visibility; safety/certification requirements; local partner requirements; document-derived scoring criteria
- First test: Validate Rijkswaterstaat and two province buyer queries, then compare transport CPVs against existing demo categories.
- Caveat: research_needed sample_demo not_verified; high commercial relevance but heavier compliance and document parsing likely.

### Dutch public works / municipal procurement portals

- Scope: Netherlands municipalities | Municipal public realm, roads, buildings, drainage, and civil works opportunities that may appear on TenderNed plus local pages
- Likely access: Start via TenderNed buyer filtering; add municipality portal watchlist only after source terms review.
- Difficulty/value/risk: 4/5, 5/5, 3/5
- Credentials: Usually none for manual public pages; credentials may be needed for tender document platforms.
- Likely fields: buyer name; project title; procurement page link; deadline; document pointers; CPV when mirrored through TenderNed
- Likely gaps: consistent API fields; complete document metadata; normalized region; English summary; duplicate detection across portals
- First test: Pick Rotterdam, Utrecht, Eindhoven, and Haarlemmermeer as manual validation buyers, then check whether TenderNed already covers each relevant notice.
- Caveat: research_needed sample_demo not_verified; do not scrape local portals at scale before legal and robots review.

### Dutch framework/maintenance procurement sources

- Scope: Netherlands multi-year frameworks and recurring maintenance | Maintenance frameworks, road resurfacing, drainage cleaning, bridge repair, inspections, and asset services
- Likely access: TenderNed/TED CPV and notice-type filters, plus buyer framework pages if public and terms permit.
- Difficulty/value/risk: 3/5, 4/5, 2/5
- Credentials: Usually none for notice discovery; tender platform credentials may be needed for detailed documents.
- Likely fields: framework title; buyer; CPV; duration; estimated value when disclosed; deadline; lot indicators
- Likely gaps: call-off timing; incumbent supplier; renewal likelihood; granular lot geography; practical supplier fit
- First test: Search maintenance CPVs 50000000, 50230000, 71500000, and drainage CPVs, then classify recurring buyers.
- Caveat: research_needed sample_demo not_verified; frameworks can be commercially valuable but may hide call-off detail.

### EU Public Procurement Data Space

- Scope: EU analytics with Netherlands slice | EU procurement analytics, dashboards, harmonized datasets, market sizing, and trend intelligence
- Likely access: Public PPDS/data.europa.eu exploration first; confirm dataset download/API/registration options for production.
- Difficulty/value/risk: 4/5, 4/5, 3/5
- Credentials: Unknown until dataset-by-dataset review; may need account/API access for some services.
- Likely fields: aggregated procurement indicators; buyer and notice dimensions; CPV/country/time filters; historical trend views
- Likely gaps: active bid urgency; full notice detail; document attachments; local buyer aliases; sales-ready summaries
- First test: Map three Netherlands infrastructure CPV trends against TenderNed/TED sample notices for buyer prioritisation.
- Caveat: research_needed sample_demo not_verified; use as analytics layer until dataset licensing and freshness are verified.

## Recommended Integration Order

1. CPV groups: priority 1; value 5/5; start with `Use the inventory CPV prefixes as a first ruleset, then measure false positives against 50 manually reviewed notices.`
2. Dutch buyer categories: priority 1; value 5/5; start with `Create a 50-buyer alias table from sample/TenderNed/TED records and test dashboard grouping consistency.`
3. TenderNed: priority 1; value 5/5; start with `Manually verify 20 current public works notices, then test RSS/dataset/API shape without storing credentials in Git.`
4. TED/EU notices: priority 2; value 5/5; start with `Run a Netherlands CPV query for construction, roads, water, maintenance, and compare returned fields against the demo data model.`
5. Dutch water authority procurement: priority 2; value 5/5; start with `Build a waterschap buyer alias list and test CPVs 4524, 452324, 452521, 7132 against TenderNed/TED records.`
6. Dutch infrastructure/transport procurement: priority 2; value 5/5; start with `Validate Rijkswaterstaat and two province buyer queries, then compare transport CPVs against existing demo categories.`
7. Dutch public works / municipal procurement portals: priority 3; value 5/5; start with `Pick Rotterdam, Utrecht, Eindhoven, and Haarlemmermeer as manual validation buyers, then check whether TenderNed already covers each relevant notice.`
8. Dutch framework/maintenance procurement sources: priority 3; value 4/5; start with `Search maintenance CPVs 50000000, 50230000, 71500000, and drainage CPVs, then classify recurring buyers.`
9. EU Public Procurement Data Space: priority 4; value 4/5; start with `Map three Netherlands infrastructure CPV trends against TenderNed/TED sample notices for buyer prioritisation.`

## What Can Be Tested Without Credentials

- TenderNed: Manually verify 20 current public works notices, then test RSS/dataset/API shape without storing credentials in Git.
- TED/EU notices: Run a Netherlands CPV query for construction, roads, water, maintenance, and compare returned fields against the demo data model.
- Dutch public works / municipal procurement portals: Pick Rotterdam, Utrecht, Eindhoven, and Haarlemmermeer as manual validation buyers, then check whether TenderNed already covers each relevant notice.
- Dutch infrastructure/transport procurement: Validate Rijkswaterstaat and two province buyer queries, then compare transport CPVs against existing demo categories.
- Dutch framework/maintenance procurement sources: Search maintenance CPVs 50000000, 50230000, 71500000, and drainage CPVs, then classify recurring buyers.
- Dutch buyer categories: Create a 50-buyer alias table from sample/TenderNed/TED records and test dashboard grouping consistency.
- CPV groups: Use the inventory CPV prefixes as a first ruleset, then measure false positives against 50 manually reviewed notices.

## What Needs Credentials Or API Keys

- TenderNed: Likely credentials for official XML/API access; no credentials for manual public portal review.
- TED/EU notices: None expected for published-notice search/retrieval pilot; API key may be required for non-public or eSender workflows.
- EU Public Procurement Data Space: Unknown until dataset-by-dataset review; may need account/API access for some services.
- Dutch public works / municipal procurement portals: Usually none for manual public pages; credentials may be needed for tender document platforms.
- Dutch water authority procurement: No credentials expected for notice discovery; tender-document access may vary by platform.
- Dutch infrastructure/transport procurement: Notice discovery likely public; platform accounts may be needed for documents, Q&A, or bid participation.
- Dutch framework/maintenance procurement sources: Usually none for notice discovery; tender platform credentials may be needed for detailed documents.

## Data Model Gaps

- Add source notice IDs, source publication version, attribution/licence fields, and retrieval timestamp before live ingestion.
- Add buyer entity normalization, buyer category, aliases, official identifiers where available, and duplicate detection across TenderNed/TED/local portals.
- Add language detection confidence, translation review status, document URL provenance, CPV parent/child expansion, and live-source freshness status.
- Add `source_access_status` values such as `manual_verified`, `api_verified`, `credentials_required`, `terms_review_required`, and `not_verified`.

## Legal And Data Caveats

- Treat this as a roadmap, not a legal opinion or a verified live source integration.
- Review source terms, robots guidance, attribution requirements, rate limits, and redistribution limits before scheduled collection.
- Keep credentials, raw source payloads, platform accounts, service account files, and customer notes outside Git.
- Avoid personal contact enrichment until a privacy review defines lawful basis, retention, and suppression handling.

## Next 7-Day Implementation Plan

1. Day 1: Run manual TenderNed and TED field checks for construction, water, roads, drainage, maintenance, engineering, and inspection CPVs.
2. Day 2: Create a source field mapping table from the checked notices to the Netherlands data model.
3. Day 3: Build a no-credentials TED published-notice prototype and record only normalized sample outputs.
4. Day 4: Request/confirm TenderNed API access path and keep any credentials outside the repository.
5. Day 5: Build buyer taxonomy for municipalities, provinces, water authorities, Rijkswaterstaat, ports, and transport authorities.
6. Day 6: Run a 50-notice manual false-positive review for CPV groups and buyer categories.
7. Day 7: Produce a founder-ready weekly digest mock with caveats and a go/no-go list for live ingestion.

## Commercial Product Impact

This moves ProcessEd Intelligence from a Netherlands demo pack toward a credible integration roadmap. The commercial upside is a clearer first wedge: verified TenderNed/TED discovery, Dutch buyer normalization, English summaries, source caveats, and CPV-led prioritisation for contractors and suppliers considering Netherlands or Benelux public works growth.

## Vertex Status Distribution

- generated: 9
