# Cloud Credit Strategy

## Current Cloud Strategy

Azure is the first hosted product surface for ProcessEd Intelligence.

The first Azure deployment target is Azure Static Web Apps, which hosts the demo and client-facing portal from the static `web/` bundle. This keeps the hosted surface simple while the local machine remains responsible for ingestion, enrichment, scoring, and dashboard data generation.

Future Azure services may include:

- App Service or Container Apps for backend/API workloads
- PostgreSQL for application data
- Azure AI for product AI features
- Azure AI Search for retrieval and document search
- Blob Storage for static artifacts and generated exports
- Azure Monitor for logs and operational visibility
- Key Vault for managed secrets

Azure usage also creates practical Microsoft Founders Hub credit-unlock evidence: a deployed product surface, clear GitHub workflow, and a staged path from static demo to hosted backend.

## Google Cloud Credit Strategy

Google Cloud credits are reserved for AI and enrichment experimentation after the Azure demo is live.

Near-term Google Cloud use cases:

- Vertex AI enrichment
- Tender classification
- Buyer intelligence enrichment
- Model comparison
- Extraction experiments
- Optional Cloud Run or BigQuery experiments later

Do not deploy the same public static demo to Google Cloud yet. Do not split production hosting across Azure and Google at this stage.

## Architecture Rule

The local machine remains the intelligence engine for now.

GitHub remains the source of truth for deployable code and static assets.

Azure is the hosted product and client-facing layer.

Google Cloud is the AI and enrichment experiment layer.

Keep credentials out of Git. Use environment variables, local secret stores, or cloud-managed secret services when a service needs credentials.

## Warnings

Do not commit secrets.

Do not commit `.env` files.

Do not include raw warehouse files, local databases, or private source exports in the cloud demo.

Avoid duplicate cloud hosting until there is a clear product, reliability, compliance, or cost reason.
