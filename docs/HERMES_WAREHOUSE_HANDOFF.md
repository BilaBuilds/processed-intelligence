# Hermes Warehouse Handoff

Hermes can use the warehouse exports as lead and account-intelligence inputs, but it must not receive raw DuckDB, SQLite, backup, log, or warehouse files. The handoff boundary is CSV only.

## Files For Hermes

- `data/hermes_handoff/hermes_company_targets.csv`: company-level supplier and award-winner targets. These are the best outreach candidates when domains are available or can be enriched safely.
- `data/hermes_handoff/hermes_buyer_targets.csv`: buyer intelligence targets. Public-sector bodies are marked as buyer targets, not normal supplier outreach targets.
- `data/hermes_handoff/warehouse_targets_FOR_HERMES.csv`: minimal `company_name,domain` input for the Hermes enrichment runner.

Blank domains are a quality caveat. Keep the rows, but expect limited enrichment until a safe domain is added from a website, known URL, email, or manual review.

## Copy To Hermes Project

Run from PowerShell:

```powershell
New-Item -ItemType Directory -Force "C:\Users\bilal\OneDrive\Documents\Playground 3\data\leads" | Out-Null
Copy-Item "C:\Users\bilal\tender_engine_pilot\data\hermes_handoff\warehouse_targets_FOR_HERMES.csv" "C:\Users\bilal\OneDrive\Documents\Playground 3\data\leads\warehouse_targets_FOR_HERMES.csv" -Force
```

## Run Hermes

```powershell
cd "C:\Users\bilal\OneDrive\Documents\Playground 3"
python scripts\run_hermes.py --input data\leads\warehouse_targets_FOR_HERMES.csv
```

## Targeting Guidance

Prioritise UK construction contractors, award winners, suppliers with repeated public-sector wins, framework-heavy firms, civils firms, highways suppliers, groundworks contractors, drainage specialists, housing-maintenance contractors, and firms that appear repeatedly against high-fit buyers.

Use buyer targets for buyer reports, market maps, and account intelligence. Use supplier/company targets for enrichment and outreach drafts.

## Prohibited

Do not copy raw `.duckdb`, `.db`, `.wal`, backup, log, or secrets files into Hermes. Do not give Hermes direct source-database access. Do not invent domains aggressively; use blank domains when there is no clear evidence.
