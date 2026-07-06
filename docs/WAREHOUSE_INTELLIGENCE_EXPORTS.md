# Warehouse Intelligence Exports

The older ProcessEd warehouse is commercially valuable because it contains repeat-buyer patterns, award-winner history, category signals, and trend evidence that a fresh tender alert feed cannot provide. The aim is to turn that history into clean, client-safe intelligence files without moving or exposing the raw database.

## Safety Model

`scripts/warehouse_intelligence_export.py` opens the DuckDB warehouse with `read_only=True`. It detects tables and columns, writes derived CSV/JSON/Markdown exports, and never writes back to the source database.

Raw `.duckdb`, `.db`, `.wal`, backup, log, and secret files must not be committed, uploaded, shared, or handed to Hermes. Hermes receives CSV targets only.

## Generated Exports

- `data/intelligence_exports/warehouse_inventory.json`: schema inventory, row counts, important columns, and warnings.
- `data/intelligence_exports/top_buyers.csv`: repeat buyers ranked by tender count and recency.
- `data/intelligence_exports/recent_high_score_tenders.csv`: recent or high-score tender rows reduced to client-safe fields.
- `data/intelligence_exports/buyer_memory_summary.csv`: buyer memory signals where the table exists, otherwise an empty headed file plus warning.
- `data/intelligence_exports/awards_top_winners.csv`: suppliers with repeated award history where awards exist.
- `data/intelligence_exports/monthly_tender_trends.csv`: month-level tender volume, average score, and unique buyer counts.
- `data/intelligence_exports/commercial_signal_summary.md`: human-readable summary for demos, client calls, and internal review.
- `data/hermes_handoff/hermes_company_targets.csv`: supplier and award-winner targets for enrichment/outreach preparation.
- `data/hermes_handoff/hermes_buyer_targets.csv`: buyer intelligence targets, including public-sector buyer labelling.
- `data/hermes_handoff/warehouse_targets_FOR_HERMES.csv`: simplified `company_name,domain` file for the Hermes runner.

## Usage

Run from `C:\Users\bilal\tender_engine_pilot`:

```powershell
python scripts\warehouse_intelligence_export.py --db "C:\Users\bilal\tender_engine\data\warehouse\procurement.duckdb" --output data\intelligence_exports --hermes-output data\hermes_handoff
```

Defaults point to the same local warehouse and output folders:

```powershell
python scripts\warehouse_intelligence_export.py
```

## Commercial Uses

Dashboard: use `top_buyers.csv`, `recent_high_score_tenders.csv`, and `monthly_tender_trends.csv` to show live-looking historical intelligence without exposing raw rows.

Pilot reports: use `commercial_signal_summary.md`, top buyers, and award winners to frame where ProcessEd finds commercially useful patterns.

Buyer intelligence: use `buyer_memory_summary.csv` and `top_buyers.csv` to identify repeat procurers, categories, and timing patterns.

Outreach: use Hermes handoff CSVs only. Blank domains mean Hermes may need manual or safe enrichment before contact discovery.

Future Ask ProcessEd / Azure / RAG: use these curated exports as governed seed context before adding retrieval over larger, access-controlled datasets.

## Caveats

These exports are derived summaries, not a replacement for the warehouse. Do not claim inferred incumbents, win probability, or buyer intent unless the claim is supported by exported evidence. Do not publish local file paths, raw JSON, credentials, logs, raw database files, or personal data that is not already appropriate for client use.
