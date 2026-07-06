# Warehouse Buyer Intelligence Report

This report is based on historical local warehouse analysis from derived CSV/JSON/Markdown exports. It does not use or include raw database files.

## Verified Warehouse Scope

| Table | Verified Rows |
| --- | ---: |
| tenders | 15,786 |
| awards | 10,325 |
| buyer_memory | 2,274 |
| run_log | 201 |

## What This Pack Can Safely Support

- Buyer prioritisation from historical tender frequency.
- Buyer-account research and briefing preparation.
- Dashboard/pilot proof that ProcessEd has local historical procurement memory.
- Evidence-backed sales conversations about buyer patterns.
- Future Ask ProcessEd/RAG seed material using curated exports rather than raw databases.

## What This Pack Does Not Claim

- It does not claim paying clients.
- It does not claim guaranteed tender wins.
- It does not claim full production automation.
- It does not force Hermes outreach from unsafe supplier data.
- It does not replace live validation of tender deadlines, scope, portal status, or buyer instructions.

## Top Buyer Targets By Historical Tender Count

| Rank | Buyer | Tender Count | First Seen | Last Seen | Avg Score |
| ---: | --- | ---: | --- | --- | ---: |
| 1 | Buckinghamshire Council - e-Tendering System | 180 | 2026-04-17 | 2026-05-14 | 5.00 |
| 2 | Department for Education | 170 | 2026-04-10 | 2026-05-22 | 9.46 |
| 3 | NHS England | 149 | 2026-04-13 | 2026-05-22 | 9.69 |
| 4 | Ministry of Defence | 138 | 2026-04-01 | 2026-05-22 | 5.91 |
| 5 | UK Research & Innovation (UKRI) | 123 | 2026-04-10 | 2026-05-22 | 6.26 |
| 6 | Derbyshire County Council | 122 | 2026-04-13 | 2026-05-22 | 9.89 |
| 7 | Hampshire County Council | 122 | 2026-04-14 | 2026-05-22 | 3.01 |
| 8 | The North Yorkshire Council | 119 | 2026-04-14 | 2026-05-22 | 11.55 |
| 9 | Nuclear Restoration Services Limited | 115 | 2026-04-13 | 2026-05-22 | 7.35 |
| 10 | Ministry of Justice | 110 | 2026-04-10 | 2026-05-22 | 10.08 |

## Monthly Tender Trend Snapshot

| Month | Tender Count | Avg Score | Unique Buyers |
| --- | ---: | ---: | ---: |
| 2026-05 | 8917 | 9.40 | 1725 |
| 2026-04 | 6790 | 9.03 | 1579 |
| 2026-03 | 6 | 57.00 | 6 |

## Recent High-Score Tender Examples

These are historical warehouse rows from derived exports, not a live opportunity promise.

| Title | Buyer | Score | Published |
| --- | --- | ---: | --- |
| IWM/2627/Dux/3499: Airspace Mezzanine Gallery Refurbishment at IWM Duxford | Imperial War Museums | 75.00 | 2026-04-22 |
| Tender for Demolition of existing cricket pavilion for replacement cricket pavilion and storage unit at King George V Playing Field, St Peters Road, Huntingdon, PE29 7DA | Huntingdon Town Council | 70.00 | 2026-04-14 |
| Extension and associated works to 23 Barnett Field | Ashford Borough Council | 70.00 | 2026-05-01 |
| Tender for Demolition of existing cricket pavilion for replacement cricket pavilion and storage unit at King George V Playing Field, St Peters Road, Huntingdon, PE29 7DA | Huntingdon Town Council | 70.00 | 2026-05-14 |
| Building Safety Act Principle Designer Cath Lab 3 Refurbishment | Guy's and St Thomas' NHS Foundation Trust | 70.00 | 2026-05-15 |
| Building Safety Act Principle Designer Cath Lab 3 Refurbishment | Guy's and St Thomas' NHS Foundation Trust | 70.00 | 2026-05-15 |
| Refurbishment and Upgarde of Noup Head Lighthouse | Northern Lighthouse Board | 65.00 | 2026-05-26 22:39:40.949816 |
| Highways Maintenance, Civil Engineering | London Borough of Bexley | 65.00 | 2026-05-07 |

## Buyer Intelligence Use Cases

1. Build a shortlist of repeat buyers where a contractor has relevant geography and work category fit.
2. Create buyer briefings that show procurement activity and recent examples before a sales call.
3. Use `data/pilot/top_50_buyer_targets.csv` as an internal account-prioritisation file.
4. Use `data/pilot/buyer_intelligence_sample.csv` as a small demo artefact for pilot conversations.

## Caveats And Controls

The source export warned that Hermes supplier/company targets are not currently safe because supplier data is not usable enough for outreach. That is the correct decision. Buyer intelligence can proceed, but supplier outreach should wait until supplier names and domains are independently verified.

No raw DB files are included. No secrets are included. All claims should be described as historical local warehouse analysis until live pipeline validation and production automation are separately evidenced.
