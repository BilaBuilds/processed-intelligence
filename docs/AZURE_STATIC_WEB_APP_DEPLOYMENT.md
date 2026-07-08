# Azure Static Web App Deployment

## Purpose

This deployment bundle hosts the public ProcessEd Intelligence landing page and static dashboard demo. It is a client-facing static layer only. The local machine remains the intelligence engine for ingestion, enrichment, scoring, and dashboard data generation.

## Recommended Azure Service

Use Azure Static Web Apps with GitHub as the deployment source.

Recommended build settings:

- App location: `web`
- API location: none / blank
- Output location: blank / not applicable for plain static HTML
- Build command: none

The deployable files are:

- `web/index.html`
- `web/dashboard.html`
- `web/dashboard_data.js`
- `web/staticwebapp.config.json`

## Safety Boundaries

The dashboard login is client-side demo gating only. It is not real authentication and must not be treated as access control for private data.

Do not deploy raw data, `.env` files, local databases, warehouse files, cache folders, credentials, API keys, or secrets. The static bundle should contain only public/demo-safe HTML, JavaScript, and assets needed by Azure Static Web Apps.

No Python runtime, local filesystem, database, or backend API is required by this static demo.

## Later Stages

1. API backend
2. PostgreSQL
3. Azure AI / Ask ProcessEd
4. Real authentication
