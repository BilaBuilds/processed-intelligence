# DACH Source Inventory Report

Generated from `data/dach/source_inventory_TEMPLATE.json`.

No scraping was performed. This report is generated from local static inventory data only.

## Source Count By Country

- Germany: 5
- Austria: 3
- Switzerland: 3

## High-Priority Sources

- Germany: TED/eForms Germany fallback
- Germany: bund.de / federal procurement discovery placeholder
- Germany: service.bund.de placeholder
- Germany: Regional/state procurement portals placeholder
- Germany: Construction-specific public portals placeholder
- Switzerland: simap.ch placeholder

## Unverified Sources

- Germany: TED/eForms Germany fallback
- Germany: bund.de / federal procurement discovery placeholder
- Germany: service.bund.de placeholder
- Germany: Regional/state procurement portals placeholder
- Germany: Construction-specific public portals placeholder
- Austria: TED/eForms Austria fallback
- Austria: auftrag.at placeholder
- Austria: Public procurement platform placeholders
- Switzerland: simap.ch placeholder
- Switzerland: Canton/municipal source placeholders
- Switzerland: TED/eForms Switzerland/EU-adjacent fallback where relevant

## Next Verification Actions

### Germany - TED/eForms Germany fallback
- Verify terms and usage permissions for TED/eForms Germany fallback.
- Confirm access mode, authentication, rate limits, and useful fields for TED/eForms Germany fallback.
- Check duplicate risk and stale notice behavior for TED/eForms Germany fallback.

### Germany - bund.de / federal procurement discovery placeholder
- Verify terms and usage permissions for bund.de / federal procurement discovery placeholder.
- Confirm access mode, authentication, rate limits, and useful fields for bund.de / federal procurement discovery placeholder.
- Check duplicate risk and stale notice behavior for bund.de / federal procurement discovery placeholder.

### Germany - service.bund.de placeholder
- Verify terms and usage permissions for service.bund.de placeholder.
- Confirm access mode, authentication, rate limits, and useful fields for service.bund.de placeholder.
- Check duplicate risk and stale notice behavior for service.bund.de placeholder.

### Germany - Regional/state procurement portals placeholder
- Verify terms and usage permissions for Regional/state procurement portals placeholder.
- Confirm access mode, authentication, rate limits, and useful fields for Regional/state procurement portals placeholder.
- Check duplicate risk and stale notice behavior for Regional/state procurement portals placeholder.

### Germany - Construction-specific public portals placeholder
- Verify terms and usage permissions for Construction-specific public portals placeholder.
- Confirm access mode, authentication, rate limits, and useful fields for Construction-specific public portals placeholder.
- Check duplicate risk and stale notice behavior for Construction-specific public portals placeholder.

### Austria - TED/eForms Austria fallback
- Verify terms and usage permissions for TED/eForms Austria fallback.
- Confirm access mode, authentication, rate limits, and useful fields for TED/eForms Austria fallback.
- Check duplicate risk and stale notice behavior for TED/eForms Austria fallback.

### Austria - auftrag.at placeholder
- Verify terms and usage permissions for auftrag.at placeholder.
- Confirm access mode, authentication, rate limits, and useful fields for auftrag.at placeholder.
- Check duplicate risk and stale notice behavior for auftrag.at placeholder.

### Austria - Public procurement platform placeholders
- Verify terms and usage permissions for Public procurement platform placeholders.
- Confirm access mode, authentication, rate limits, and useful fields for Public procurement platform placeholders.
- Check duplicate risk and stale notice behavior for Public procurement platform placeholders.

### Switzerland - simap.ch placeholder
- Verify terms and usage permissions for simap.ch placeholder.
- Confirm access mode, authentication, rate limits, and useful fields for simap.ch placeholder.
- Check duplicate risk and stale notice behavior for simap.ch placeholder.

### Switzerland - Canton/municipal source placeholders
- Verify terms and usage permissions for Canton/municipal source placeholders.
- Confirm access mode, authentication, rate limits, and useful fields for Canton/municipal source placeholders.
- Check duplicate risk and stale notice behavior for Canton/municipal source placeholders.

### Switzerland - TED/eForms Switzerland/EU-adjacent fallback where relevant
- Verify terms and usage permissions for TED/eForms Switzerland/EU-adjacent fallback where relevant.
- Confirm access mode, authentication, rate limits, and useful fields for TED/eForms Switzerland/EU-adjacent fallback where relevant.
- Check duplicate risk and stale notice behavior for TED/eForms Switzerland/EU-adjacent fallback where relevant.

## Sources By Country

### Germany
- Source: TED/eForms Germany fallback
  - Type: api
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: high
  - Base URL: https://ted.europa.eu/
  - Notes: Fallback discovery source for German public procurement notices. Verify eForms access, usable fields, terms, rate limits, and duplicate risk before adapter work.
- Source: bund.de / federal procurement discovery placeholder
  - Type: unknown
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: high
  - Base URL: https://www.bund.de/
  - Notes: Placeholder for German federal procurement discovery. Verify whether procurement notices, downloads, feeds, APIs, or onward links are available and reusable.
- Source: service.bund.de placeholder
  - Type: unknown
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: high
  - Base URL: https://www.service.bund.de/
  - Notes: Placeholder for German federal service portal discovery. Confirm procurement coverage, source terms, useful fields, and whether records duplicate TED/eForms.
- Source: Regional/state procurement portals placeholder
  - Type: manual
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: high
  - Base URL: TBD
  - Notes: Placeholder group for German state and regional procurement portals. Inventory each state separately before any collection work.
- Source: Construction-specific public portals placeholder
  - Type: manual
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: high
  - Base URL: TBD
  - Notes: Placeholder for construction and civils-focused German public procurement sources. Verify commercial usefulness and access model source by source.

### Austria
- Source: TED/eForms Austria fallback
  - Type: api
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: medium
  - Base URL: https://ted.europa.eu/
  - Notes: Fallback discovery source for Austrian public procurement notices. Verify eForms coverage, terms, useful fields, and duplicate risk before adapter work.
- Source: auftrag.at placeholder
  - Type: unknown
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: medium
  - Base URL: https://www.auftrag.at/
  - Notes: Placeholder for Austrian procurement discovery. Verify access, terms, authentication, available fields, and whether usage is suitable for commercial intelligence.
- Source: Public procurement platform placeholders
  - Type: manual
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: low
  - Base URL: TBD
  - Notes: Placeholder group for additional Austrian national, regional, municipal, and sector procurement platforms. Split into specific sources after manual verification.

### Switzerland
- Source: simap.ch placeholder
  - Type: unknown
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: high
  - Base URL: https://www.simap.ch/
  - Notes: Placeholder for Swiss procurement discovery. Verify multilingual fields, access mode, terms, authentication, and whether structured export or search access exists.
- Source: Canton/municipal source placeholders
  - Type: manual
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: medium
  - Base URL: TBD
  - Notes: Placeholder group for Swiss canton and municipal sources. Inventory each source separately with language, terms, and duplicate checks.
- Source: TED/eForms Switzerland/EU-adjacent fallback where relevant
  - Type: api
  - Status: unverified
  - Auth required: unknown
  - Scraper difficulty: unknown
  - Commercial priority: medium
  - Base URL: https://ted.europa.eu/
  - Notes: Fallback for Swiss-linked or EU-adjacent notices where relevant. Verify actual coverage, legal basis, field completeness, and duplicate risk before adapter work.
