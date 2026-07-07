# Azure Startup Credit Unlock Pack

## Company Summary

ProcessEd Intelligence builds procurement intelligence for contractors and suppliers. The product turns official tender sources, buyer history, award history, evidence-backed enrichment, and client preferences into opportunity alerts, buyer briefs, and bid/no-bid intelligence.

## Azure Architecture

- Azure Static Web Apps: hosted landing page and demo/client portal surface
- Azure Functions: future API and scheduled source orchestration
- Azure Database for PostgreSQL: procurement warehouse and normalized tender intelligence
- Azure Blob Storage: raw source payload storage and document packs
- Azure AI services or Azure OpenAI: extraction, classification, summarization, and evidence-backed briefing generation
- Application Insights: telemetry, reliability, and product usage reporting
- Key Vault: credentials, API keys, and TenderNed Basic Auth secrets

## Services Planned

- Static demo portal for prospects and Microsoft review
- Client dashboard with sanitized opportunity views
- TenderNed XML ingestion after credentials are issued
- UK and EU official-source ingestion jobs
- Evidence ledger and source provenance API
- Weekly intelligence brief generator
- Usage and customer-value telemetry

## Screenshots Placeholder

Add screenshots of:

- Landing page
- Demo dashboard
- Opportunity detail
- Evidence/source trace
- Weekly brief output

## Usage Metrics Placeholder

Track:

- Demo portal visits
- Opportunity views
- Briefs generated
- Alerts sent
- Source records ingested
- Client shortlist actions
- Azure compute/storage/database usage

## Customer Traction Placeholder

Track:

- Active pilots
- Prospect demos completed
- Construction niches covered
- Paid discovery calls or LOIs
- Weekly brief recipients
- Feedback examples showing saved research time or better bid selection

## Roadmap

1. Static Azure-hosted product surface from GitHub
2. Sanitized demo dashboard and data bundle
3. Azure-hosted API for read-only demo intelligence
4. PostgreSQL warehouse migration for normalized tender records
5. TenderNed XML connector live mode after credentials
6. Evidence-backed client portal with authentication
7. Automated brief generation and telemetry

## Why More Azure Credits Are Needed

Additional credits are needed to prove a credible hosted procurement intelligence platform, not just a local script. The near-term spend will support a secure demo portal, managed database, raw document storage, scheduled ingestion, AI extraction/classification, monitoring, and customer-facing telemetry while pilots are still pre-revenue or early revenue.
