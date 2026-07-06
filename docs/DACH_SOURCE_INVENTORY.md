# DACH Source Inventory

This is an unverified source inventory for DACH procurement discovery. No scraping has been performed yet, and no source should be treated as working until it has been manually verified.

The current TenderNed Hostinger demo remains untouched.

## Priority Order

1. Germany is the first priority because it has the largest contractor and public procurement opportunity surface in DACH.
2. Switzerland is the second priority because it is commercially attractive for premium public and private-enterprise intelligence.
3. Austria is the third priority because it is a smaller extension once Germany and Switzerland discovery patterns are proven.

## Source Strategy

TED/eForms can be used as a fallback for Germany, Austria, and Switzerland-adjacent discovery where relevant. It should not be assumed complete or sufficient until field coverage, terms, and duplicate behavior are verified.

Before any adapter work, each source must be checked for:

- Terms and usage permissions.
- API, RSS, download, search-only, or manual portal support.
- Authentication requirements.
- Rate limits and acceptable access patterns.
- Useful fields for construction/civils opportunity intelligence.
- Duplicate risk against TED/eForms, national portals, regional portals, and sector portals.
- Stale or expired notice handling.

## Local Inventory Files

- Inventory template: `data/dach/source_inventory_TEMPLATE.json`
- Local report script: `scripts/dach_source_inventory_report.py`
- Generated local report: `data/dach/source_inventory_report.md`

The report script is local-only and does not require internet access. It validates required fields, groups sources by country, and summarizes verification actions.

## Verification Workflow

For each source:

1. Confirm the official source URL and owner.
2. Read terms, robots guidance where relevant, and redistribution restrictions.
3. Identify whether API, RSS, download, search-only, or manual access exists.
4. Confirm whether authentication is required.
5. Check whether the required expected fields are available.
6. Estimate scraper difficulty only after source inspection.
7. Assign commercial priority based on construction/civils relevance, notice freshness, and buyer value.
8. Mark status only after verification evidence exists.
