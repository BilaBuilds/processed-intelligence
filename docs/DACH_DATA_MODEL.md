# DACH Data Model

## Normalized Tender Object

The DACH expansion should normalize Germany, Austria, and Switzerland procurement notices into the object below before any dashboard or sales workflow consumes them.

```json
{
  "id": "string",
  "title": "string",
  "buyer": "string",
  "country": "Germany | Austria | Switzerland",
  "region": "string",
  "language": "string",
  "source": "string",
  "source_url": "string",
  "notice_id": "string",
  "published_at": "YYYY-MM-DD or ISO-8601 datetime",
  "deadline": "YYYY-MM-DD or ISO-8601 datetime",
  "value": 0,
  "currency": "EUR | CHF | unknown",
  "cpv_codes": ["string"],
  "description": "string",
  "procurement_stage": "planned | open | awarded | cancelled | unknown",
  "fit_score": 0,
  "priority": "high | medium | low | unknown",
  "reasons": ["string"],
  "raw_source_ref": "string"
}
```

## Field Notes

- `id`: Stable internal ID, ideally derived from country, source, notice ID, and publication date.
- `title`: Human-readable tender title.
- `buyer`: Contracting authority, utility, enterprise, or lead buyer.
- `country`: Normalized country name: Germany, Austria, or Switzerland.
- `region`: State, canton, city, municipality, or source-provided region.
- `language`: Source language such as German, French, Italian, or English.
- `source`: Source system or portal name.
- `source_url`: Public URL for the notice or source record.
- `notice_id`: Source-provided notice identifier.
- `published_at`: Publication timestamp where available.
- `deadline`: Submission deadline, expiry date, or response deadline.
- `value`: Numeric contract value where available.
- `currency`: Currency code, expected to be EUR or CHF for most DACH notices.
- `cpv_codes`: One or more CPV codes as strings.
- `description`: Notice summary or extracted description.
- `procurement_stage`: Normalized stage for filtering and stale-notice handling.
- `fit_score`: Numeric relevance score for construction/civils targeting.
- `priority`: Commercial priority derived from fit, value, urgency, buyer, and source quality.
- `reasons`: Short explanations for score and priority.
- `raw_source_ref`: Pointer to source payload, file, hash, or audit reference without committing raw large exports.

## Compatibility

This model is a planning contract for DACH work. It does not change the existing `dashboard_data.json` schema. Any future dashboard fields must be additive and backward-compatible.
