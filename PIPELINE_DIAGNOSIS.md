# Tender Engine Pipeline — Diagnosis & Status

**Last Updated:** 17 April 2026  
**Current Run Status:** `success_with_warnings` (notify fails in sandbox — works on local machine)  
**Pipeline Health:** ✅ All core steps stable | ✅ Buyer Intel layer live | ✅ 44/44 tests passing

---

## Pipeline Step Order

```
ingest → normalize → match → context → buyer_intel → patterns → select → decision → dedupe → notify
```

| Step | Module | Fatal? | Notes |
|------|--------|--------|-------|
| ingest | src.ingest | Yes | FTS + Contracts Finder scrape |
| normalize | src.normalize | Yes | Dedup fields, decode ONS regions |
| match | src.match | Yes | Keyword scoring, disqualifiers |
| context | src.context | Yes | Trade classification, strategic fit |
| buyer_intel | src.buyer_intel | **No** | Accumulate history + Gemini briefs |
| patterns | src.patterns | No | Historical pattern signals |
| select | src.select | Yes | Shortlist by score/value band |
| decision | src.decision | Yes | BID / REVIEW / NO_BID verdict |
| dedupe | src.dedupe | Yes | Suppress already-seen tenders |
| notify | src.notify.discord | No | Discord webhook alerts |

---

## Active Issues

### 1. Discord Notify: Network Blocked in Sandbox (EXTERNAL)
**Status:** Not fixable in sandbox — works correctly on local machine  
**Root Cause:** Cowork sandbox outbound proxy blocks `discord.com`  
**Impact:** Notifications not sent during sandbox test runs; core pipeline unaffected  
**Action:** Run pipeline on local machine (`python run_pipeline.py`) to receive Discord alerts

---

## Fixed Issues

### FTS 0 Records on Incremental Runs (FIXED 17 April)
**Problem:** Frequent runs created a near-zero FTS window (1–3 minutes), returning 0 records.  
**Root Cause:** `determine_windows()` used the watermark directly — when pipeline runs every few minutes, window shrinks to match.  
**Fix:** Added minimum window floor (`TENDER_FTS_MIN_WINDOW_HOURS`, default 4h).  
**File:** `src/fts_scraper.py` → `determine_windows()`  
**Config:** `TENDER_FTS_MIN_WINDOW_HOURS=4`

### context.py Crashes on FTS Tenders with None Fields (FIXED 17 April)
**Problem:** FTS tenders (fat: prefix) frequently have `None` description, `None` region, `None` risk_flags.  
`tender.get("description", "")` returns `None` (not `""`) when the key exists but is set to `None`.  
**Fix:** Replaced all `tender.get(field, "")` with `tender.get(field) or ""` throughout `context.py`.  
**Files:** `src/context.py` (lines 127, 230, 259, 312, 332, 364–366)  
**Validated:** Against 471 real FTS tenders — 0 errors

### Discord `_post_payload` Silent Failures (FIXED 17 April)
**Problem:** `_post_payload` returned `bool`, error detail was lost. Manifest showed no error info.  
**Fix:** Changed return type to `tuple[bool, str]`. Error detail now logged and written to `manifest["notify_error_detail"]`.  
**Files:** `src/notify/discord.py`, `run_pipeline.py`, `tests/test_notify_discord.py`

### Artifact Cleanup Permission Error (FIXED 8 April)
**Problem:** `cleanup_old_run_artifacts()` raised `PermissionError` on sandbox-owned files.  
**Fix:** Wrapped `unlink()` in `except (PermissionError, OSError)`.  
**File:** `run_pipeline.py` → `cleanup_old_run_artifacts()`

---

## New Features (17 April)

### Buyer Intelligence Layer
**File:** `src/buyer_intel.py`  
**What it does:**
1. **Accumulates** every processed tender into `state/buyer_history.jsonl` (buyer, value, region, score, deadline, date seen)
2. **Synthesises** a Gemini intelligence brief for each shortlisted buyer (min 2 records needed, cache TTL 7 days)
3. **Attaches** the brief to the opportunity record — appears in Discord alerts as "📊 Buyer Intel"

**Config required:** `GEMINI_API_KEY` in `config/.env` (free tier from aistudio.google.com)  
**Model used:** `gemini-2.0-flash-lite` (free tier: ~1,500 req/day, well within 3x/day pipeline volume)  
**Non-fatal:** pipeline continues normally if Gemini is unavailable  
**Manifest fields:** `buyer_intel_status`, `buyer_intel_accumulated`, `buyer_intel_unique_buyers`, `buyer_intel_briefs_attached`

---

## Scheduled Runs

**File:** `schedule_pipeline.ps1`  
Run once as Administrator to register three daily Windows Task Scheduler jobs:

| Task | Time | Log |
|------|------|-----|
| ProcessEd_Morning | 06:00 daily | `logs/pipeline_YYYY-MM-DD.log` |
| ProcessEd_Midday | 13:00 daily | `logs/pipeline_YYYY-MM-DD.log` |
| ProcessEd_Evening | 20:00 daily | `logs/pipeline_YYYY-MM-DD.log` |

```powershell
# Run once in PowerShell as Administrator:
cd C:\Users\bilal\tender_engine
.\schedule_pipeline.ps1
```

To remove all tasks:
```powershell
Unregister-ScheduledTask -TaskName "ProcessEd_Morning","ProcessEd_Midday","ProcessEd_Evening" -Confirm:$false
```

---

## Environment Variables

```
TENDER_WEBHOOK_URL=<discord_webhook>
TENDER_MIN_SCORE=20
TENDER_SHORTLIST_N=10
TENDER_NOTIFY_N=5
TENDER_DECISION_BID_MIN_SCORE=35
TENDER_DECISION_REVIEW_MIN_SCORE=22
TENDER_RAW_RETENTION_DAYS=7
TENDER_FTS_MIN_WINDOW_HOURS=4     # prevents near-zero FTS windows
GEMINI_API_KEY=<from aistudio.google.com>  # buyer intel synthesis
```

---

## Run History

| Date | Run ID | FTS | CF | Shortlist | New | Status |
|------|--------|-----|----|-----------|-----|--------|
| 17 Apr | 2026-04-17_162618 | 212 | 100 | 4 | 4 | success_with_warnings |
| 17 Apr | 2026-04-17_150946 | 0 (window narrow) | 100 | 1 | 1 | success_with_warnings |
| 17 Apr (failed) | 2026-04-17_150804 | 471 | — | — | — | failed (context crash) |
| 16 Apr (failed) | 2026-04-16_235745 | 1042 | — | — | — | failed (context crash) |
| 15 Apr | 2026-04-15_032806 | 932 | 100 | 10 | 10 | success_with_warnings |
| 3 Apr | 2026-04-03_193755 | — | 677 | 10 | 10 | success_with_warnings |

---

## Test Suite

**44/44 passing** as of 17 April 2026

```
tests/test_context.py                  1 test
tests/test_decision.py                 3 tests
tests/test_dedupe.py                   1 test
tests/test_fts_scraper_modes.py        5 tests
tests/test_leads_compliance.py         5 tests
tests/test_match_disqualifiers.py      2 tests
tests/test_normalize_regions.py        2 tests
tests/test_notify_discord.py          10 tests
tests/test_outreach_cli.py             2 tests
tests/test_outreach_db.py              2 tests
tests/test_outreach_samples.py         2 tests
tests/test_outreach_service.py         4 tests
tests/test_patterns.py                 2 tests
tests/test_run_pipeline_manifest.py    2 tests
tests/test_select_filters.py           1 test
```

---

## Next Steps (Pending)

1. **Populate `state/job_history.json`** — add 3–5 real past contracts (trade, value, region, client) to unlock delivery fit scoring
2. **Second sector config** — create `config/social_housing_niche.yaml` for Social Housing & Retrofit
3. **Negative keyword tuning** — reduce false positives by expanding `DISQUALIFY_KEYWORDS` in `match.py`
