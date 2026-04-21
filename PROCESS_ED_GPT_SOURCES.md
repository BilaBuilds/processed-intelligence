# ProcessEd - GPT Project Sources

Use these files as your core "Sources" in the ChatGPT Project.

## 1) Core pipeline code (upload all)

- `run_pipeline.py`
- `src/ingest.py`
- `src/normalize.py`
- `src/match.py`
- `src/select.py`
- `src/dedupe.py`
- `src/fts_scraper.py`
- `src/notify/base.py`
- `src/notify/discord.py`

## 2) Operations scripts (upload all)

- `audit.ps1`
- `set_webhook.ps1`

## 3) Configuration templates (upload safe template only)

- `config/.env.example`

Do not upload secrets:
- `config/.env` (contains runtime values)
- `state/sent_log.sqlite`
- any file with real webhook URLs/tokens

## 4) Example outputs (upload 1-2 recent runs only, optional)

From one recent run folder in `data/runs/<run_id>/`:
- `run_manifest.json` (required if sharing examples)
- `shortlist.json` (optional)
- `new_tenders.json` (optional)

Avoid uploading every historical run to keep context clean.

## 5) Nice-to-have context docs (optional)

Create and upload if useful:
- architecture note
- scoring policy note
- go/no-go checklist
- commercialization plan

