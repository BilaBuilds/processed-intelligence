# Netherlands Source Inventory

Status: source planning inventory. Access notes and commercial value are planning assumptions, not verified live coverage.

## Source Coverage

| Source | Coverage | Access status | Legal/data risk | Commercial usefulness |
| --- | --- | --- | --- | --- |
| TenderNed | Dutch national publication platform for public procurement notices, including works, services, supplies, and contracting authority profiles. | Public portal access expected; automated access should be validated against current terms and robots guidance before production use. | Medium. Public notices are reusable for analysis, but scraping volume, attribution, and downstream redistribution need legal review. | Very high for Netherlands-specific opportunities and buyer discovery. |
| TED/EU notices | EU-level notices above procurement thresholds, including Dutch high-value works and cross-border infrastructure tenders. | Public web and API access expected; use official EU endpoints where possible. | Low to medium. Official EU notices are public, but enrichment, translations, and redistribution still require attribution and retention controls. | High for major infrastructure, frameworks, and cross-border supplier targeting. |
| EU Public Procurement Data Space | EU procurement analytics and harmonized datasets intended for cross-market procurement transparency. | Access model may vary by dataset and service; confirm registration/API requirements before production use. | Medium. Dataset licensing, permitted use, and data minimization should be reviewed before building commercial exports. | High for market sizing, buyer benchmarking, historical win/loss patterns, and CPV trend analysis. |
| Dutch buyer categories | Municipalities, provinces, water boards, ministries, Rijkswaterstaat, ports, public transport authorities, housing/public estate bodies, and utility-adjacent public entities. | Derived taxonomy can be maintained internally from public buyer names and source metadata. | Low if limited to public entity classification; medium if joined to contacts or private firm data. | Very high for routing opportunities to sector-specific campaigns. |
| CPV groups | Works and infrastructure CPVs including 45000000, 45100000, 45200000, 45220000, 45230000, 45231000, 45232000, 45233000, 45240000, 45300000, 50000000, 71000000, and 71500000. | Public code system. | Low. CPV codes are public taxonomy values. | Very high for repeatable search filters and product positioning. |

## Practical Source Strategy

Start with TenderNed and TED because they map directly to active opportunity discovery. Use the EU Public Procurement Data Space for market sizing and historical analytics once access and licensing are confirmed. Treat buyer categories and CPV groups as internal normalization layers rather than external sources.

## Dutch Buyer Categories

| Category | Example buyer type | Common opportunity themes |
| --- | --- | --- |
| Central government and agencies | Ministries, Rijkswaterstaat, national facilities bodies | Motorways, tunnels, waterways, bridges, major maintenance |
| Provinces | Provincial governments | Regional roads, cycleways, bridges, civil maintenance |
| Municipalities | Gemeenten and joint municipal services | Public realm, roads, sewerage, drainage, buildings maintenance |
| Water authorities | Waterschappen | Flood defences, pumping stations, water treatment, drainage |
| Ports and logistics bodies | Port authorities and public logistics operators | Quays, dredging, access roads, utilities, asset inspection |
| Public transport authorities | Regional transport bodies and operators | Stations, depots, track-adjacent works, accessibility upgrades |

## CPV Groups For Initial Filters

| CPV prefix | Use |
| --- | --- |
| 45000000 | Construction work |
| 45100000 | Site preparation |
| 45200000 | Complete or part construction and civil engineering |
| 45220000 | Engineering works and construction works |
| 45230000 | Pipelines, communication and power lines, roads, airfields and railways |
| 45231000 | Pipeline, piping, cable, and related works |
| 45232000 | Ancillary works for pipelines and cables |
| 45233000 | Construction, foundation, and surface works for highways and roads |
| 45240000 | Water projects |
| 45300000 | Building installation work |
| 50000000 | Repair and maintenance services |
| 71000000 | Architectural, construction, engineering, and inspection services |
| 71500000 | Construction-related services |

## Risk Controls

- Store only normalized demo/sample records in committed planning artifacts.
- Keep raw source payloads, credentials, customer notes, and operational exports outside Git.
- Add attribution fields before live publication.
- Re-check source terms before scheduling collection jobs.
