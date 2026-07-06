# Netherlands Market Entry Brief

Status: sample/demo planning brief. This document does not claim verified live tender coverage.

## Objective

Build a Netherlands expansion lane for ProcessEd Intelligence that can identify construction, civils, roads, drainage, water, maintenance, public works, and infrastructure opportunities from Dutch and EU procurement sources without changing the existing UK, DACH, or sales tracker pipeline.

## Market Thesis

The Netherlands is a strong fit for procurement intelligence because public infrastructure buyers publish recurring works packages across water resilience, road maintenance, municipal public realm, utilities coordination, and civil engineering frameworks. The market has high transparency through national and EU procurement systems, but tender texts are commonly Dutch-first and buyer structures differ from the UK model.

The first commercial wedge should be a monitored opportunity feed for UK/EU contractors, consultants, suppliers, and specialist subcontractors that need early warning, English summaries, CPV tagging, and buyer segmentation.

## Expansion Priorities

1. National Dutch public works: municipalities, provinces, Rijkswaterstaat, water authorities, public transport authorities, and port bodies.
2. Water and climate resilience: drainage, pumping stations, dikes, sewer systems, flood defence, and water treatment works.
3. Roads and civils maintenance: resurfacing, bridge works, asset inspection, traffic management, and framework renewals.
4. EU/TED cross-border notices: high-value Dutch notices or Benelux/EU infrastructure packages where non-Dutch suppliers may participate.

## Data Position

This pack uses sanitized demo data under `data/dutch/demo/`. It is suitable for dashboard development, sales demonstration, and data model tests. It is not a live coverage claim and should not be used for bid decisions without source verification.

## Go-To-Market Angle

Position the Netherlands lane as a practical expansion intelligence layer:

- Translate Dutch-first notices into buyer-ready English summaries.
- Separate local municipal works from larger cross-border or EU-relevant opportunities.
- Score urgency and fit so commercial teams can decide whether to qualify, partner, monitor, or ignore.
- Map Dutch buyer categories and CPV groups into existing ProcessEd opportunity logic.

## Operating Guardrails

- Keep Netherlands artifacts separate from existing UK, DACH, and sales tracker outputs.
- Do not require network access for the demo bundle.
- Do not store credentials, API keys, tokens, private customer data, or raw scraped payloads.
- Label sample data clearly as demo data not verified against live coverage.

## Suggested Launch Sequence

1. Validate source access assumptions for TenderNed, TED, and the EU Public Procurement Data Space.
2. Run a two-week manual sample collection to tune CPV filters, buyer aliases, and region taxonomy.
3. Add Dutch language normalization and translation review workflows.
4. Pilot a weekly Netherlands opportunity digest with 20-40 scored records.
5. Convert recurring buyers into target account segments for outreach and partner discovery.
