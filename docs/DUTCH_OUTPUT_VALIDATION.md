# Dutch TenderNed Output Validation

Generated locally. No VPS, DuckDB, Flask, or TenderNed XML was required.

## Files checked

- `C:\Dev\dutch_output\dutch_tenders.json`
- `C:\Dev\dutch_output\dutch_tenders.jsonl`
- `C:\Users\bilal\tender_engine\data\export\tenderned_latest.json`
- `C:\Users\bilal\tender_engine\data\dashboard\tenderned_latest.json`
- `C:\Users\bilal\tender_engine\data\export\dashboard_data.json`
- `C:\Users\bilal\tender_engine\data\dashboard\dashboard_data.json`

## Counts

- `dutch_tenders.json`: 50 tenders
- `dutch_tenders.jsonl`: 50 tenders
- Dashboard export tenders: 50
- Dashboard export opportunities: 50
- `latestRun.tenders`: 50
- `latestRun.opportunities`: 50

## Missing field counts

- Missing `source_id`: 0
- Missing `title`: 0
- Missing `buyer`: 0
- Missing `publication_date` or `published_at`: 0
- Missing `deadline`: 11
- Duplicate `source_id` values: 0

## Sample tender objects

```json
{
  "source_id": "431953",
  "title": "Werkplek-hardware",
  "buyer": "Gemeente Súdwest-Fryslân",
  "deadline": "2026-09-11T14:00:00",
  "publication_date": "2026-07-05",
  "type_code": "L",
  "type_name": "supplies",
  "procedure_code": "OPE",
  "procedure_name": "open",
  "source": "tenderned",
  "country": "NL",
  "url": null
}
```

```json
{
  "source_id": "431951",
  "title": "Concessie Twente Airport",
  "buyer": "Technology Base",
  "deadline": "2026-09-21T10:00:00",
  "publication_date": "2026-07-05",
  "type_code": "D",
  "type_name": "services",
  "procedure_code": "CCD",
  "procedure_name": "competitive_dialogue",
  "source": "tenderned",
  "country": "NL",
  "url": null
}
```

```json
{
  "source_id": "431950",
  "title": "Pressure Increase study",
  "buyer": "N.V. Nederlandse Gasunie",
  "deadline": null,
  "publication_date": "2026-07-05",
  "type_code": "D",
  "type_name": "services",
  "procedure_code": "OZB",
  "procedure_name": "negotiated_without_call",
  "source": "tenderned",
  "country": "NL",
  "url": null
}
```

## Fixes made

- Updated `C:\Dev\dutch_adapter.py` so JSON exports use a dashboard-compatible shape.
- Preserved JSONL as one canonical tender per line.
- Added `latestRun.tenders`, `latestRun.opportunities`, top-level `tenders`, and top-level `opportunities`.
- Added parser support for TenderNed `content` arrays.
- Added deduplication by `source_id`.
- Added clean XML enrichment skip behavior when credentials are missing.
- Added Hostinger-ready static dashboard export builder.

## Tests run

```powershell
python -m pytest tests\test_dutch_tenderned_adapter.py -q
python -m pytest tests\test_hostinger_dashboard_export.py -q
```

Result:

- Dutch adapter tests: 5 passed
- Hostinger export tests: 6 passed

## Dashboard-ready status

Dashboard-ready: yes.

The current static bundle contains non-empty compatible aliases:

- `tenders`
- `opportunities`
- `latestRun.tenders`
- `latestRun.opportunities`
- `kpis`
- `system_health`
- `generated_at`
