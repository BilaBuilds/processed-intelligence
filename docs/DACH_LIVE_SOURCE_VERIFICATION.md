# DACH Live Source Verification

## 1. Purpose

This checklist is the final safety and documentation layer before any Germany, Austria, or Switzerland source integration work. No live scraping has been performed.

Current TenderNed Hostinger demo remains untouched. DACH static demo remains fixture-only. run_pipeline.py must not be modified for source verification.

## 2. Non-Negotiable Rule: No Adapter Until Source Is Verified

No DACH adapter should be built until the source owner, access method, terms, rate limits, authentication, fields, freshness, duplicates, language handling, and commercial usefulness have been checked and recorded.

Only then build adapter.

## 3. Verification Checklist

- Confirm source legality/terms.
- Confirm API/RSS/download/search access.
- Confirm authentication requirements.
- Confirm rate limits.
- Confirm available fields: title, buyer, country, region, deadline, value, currency, cpv, url, source, notice_id, published_at, description.
- Confirm notice freshness.
- Confirm duplicate handling.
- Confirm language handling.
- Confirm DACH country mapping.
- Confirm whether source is commercially useful.
- Only then build adapter.

## 4. Germany Source Verification

Starter Germany sources:

- TED/eForms Germany fallback
- bund.de
- service.bund.de
- regional/state procurement portals
- construction-specific public portals

Germany should be verified first because it is the largest DACH public procurement and construction opportunity market. Verification must start with source ownership, terms, available access method, and whether the source has useful construction/civils fields.

## 5. Austria Source Verification

Starter Austria sources:

- TED/eForms Austria fallback
- auftrag.at
- public procurement platform placeholders

Austria should be verified after Germany and Switzerland patterns are understood. Confirm whether national and platform sources provide useful fields, whether authentication is required, and whether notices duplicate TED/eForms records.

## 6. Switzerland Source Verification

Starter Switzerland sources:

- simap.ch
- canton/municipal portals
- TED/eForms Switzerland/EU-adjacent fallback where relevant

Switzerland verification must pay special attention to multilingual handling, canton/municipal source fragmentation, high-value civil engineering and infrastructure relevance, and any restrictions on reuse.

## 7. TED/eForms Fallback Verification

TED/eForms can be assessed as a fallback or cross-check source for Germany, Austria, and Switzerland/EU-adjacent notices where relevant.

Before using it in an adapter, verify:

- Access method and official API/download options.
- Terms and reuse permissions.
- Field completeness for construction/civils intelligence.
- Country and buyer mapping.
- Duplicate risk against national, regional, and platform sources.
- Notice freshness and expired notice handling.

## 8. Legal/Terms/Rate-Limit Review

Each source must have a documented legal and operational review before any automated collection work:

- Terms or usage policy reviewed.
- Robots guidance checked where relevant.
- Rate limits known or conservative limits documented.
- Authentication requirements recorded.
- Redistribution constraints recorded.
- Contact or owner noted where available.

## 9. Required Data Fields

Every source should be checked for these fields before adapter work:

- title
- buyer
- country
- region
- deadline
- value
- currency
- cpv
- url
- source
- notice_id
- published_at
- description

Missing fields do not automatically disqualify a source, but they must be recorded before deciding whether the source is useful enough for DACH procurement intelligence.

## 10. Adapter-Readiness Decision

A source is adapter-ready only when:

- Terms and source legality are acceptable.
- API, RSS, download, or search access is understood.
- Authentication requirements are known.
- Rate limits are known or a conservative approach is documented.
- Required fields are mapped.
- Notice freshness and stale notice handling are understood.
- Duplicate handling is designed.
- Language handling is documented.
- DACH country mapping is reliable.
- Commercial usefulness is clear.

Only then build adapter.
