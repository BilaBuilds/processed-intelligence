import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CLAWSHIELD = Path(__file__).parent.parent / "security" / "clawshield.sh"


def _clawshield_scan(text: str) -> Tuple[str, str]:
    """Returns (status, categories). status: ok|review|blocked."""
    try:
        result = subprocess.run(
            ["bash", str(CLAWSHIELD), "scan"],
            input=text.encode("utf-8", errors="replace"),
            capture_output=True,
            timeout=10,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        status = "ok"
        categories = "none"
        for line in output.splitlines():
            if line.startswith("STATUS="):
                status = line.split("=", 1)[1].strip()
            elif line.startswith("CATEGORIES="):
                categories = line.split("=", 1)[1].strip()
        return status, categories
    except Exception as e:
        logger.warning(f"clawshield scan failed: {e} — treating as ok")
        return "ok", "none"


def _fetch_source(source: dict, limit: Optional[int] = None) -> Tuple[List[dict], str, Optional[str]]:
    """Fetch and parse a single source. Returns (raw_records, status, error_msg)."""
    url = source["url"]
    authority = source.get("authority", "Unknown")
    region = source.get("region", "National")
    source_key = source["key"]
    fetch_limit = limit if limit is not None else source.get("fetch_limit", 20)

    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "OpenClaw-RegBot/1.0"})
        resp.raise_for_status()
    except Exception as e:
        return [], "error", str(e)

    source_type = source.get("type", "html")
    if source_type == "json":
        try:
            data = resp.json()
        except Exception as e:
            return [], "error", f"json parse error: {e}"
        html_fragment = data.get("search_results", "")
        if not html_fragment:
            return [], "ok", None
        soup = BeautifulSoup(html_fragment, "html.parser")
    else:
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            return [], "error", f"parse error: {e}"

    raw_records = []

    # Extract links with titles - heuristic: find <a> tags with meaningful text
    links = soup.find_all("a", href=True)
    seen_urls = set()
    for link in links:
        if len(raw_records) >= fetch_limit:
            break

        href = link.get("href", "").strip()
        title = link.get_text(separator=" ", strip=True)

        if not title or len(title) < 10:
            continue
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue

        # Resolve relative URLs
        if href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        elif not href.startswith("http"):
            continue

        if href in seen_urls:
            continue
        seen_urls.add(href)

        # Get surrounding text as body snippet
        parent = link.parent
        body_text = ""
        if parent:
            body_text = parent.get_text(separator=" ", strip=True)[:2000]

        # Look for a date near this link
        date_text = ""
        if parent:
            date_candidates = parent.find_all(
                lambda tag: tag.name in ["time", "span", "p"] and
                any(c in tag.get("class", []) for c in ["date", "published", "updated", "metadata"])
            )
            if date_candidates:
                date_text = date_candidates[0].get_text(strip=True)

        raw_text = f"{title}\n{body_text}"[:2000]

        # ClawShield scan
        shield_status, categories = _clawshield_scan(raw_text)
        if shield_status == "blocked":
            logger.warning(
                f"[ingest] clawshield BLOCKED record from {source_key}: "
                f"title='{title[:60]}' categories={categories}"
            )
            continue

        record = {
            "title": title,
            "url": href,
            "authority": authority,
            "region": region,
            "source": source_key,
            "raw_text": raw_text,
            "date_hint": date_text,
            "shield_status": shield_status,
            "shield_categories": categories,
        }
        raw_records.append(record)

    return raw_records, "ok", None


def run_ingest(
    sources: List[dict],
    run_dir: Path,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Tuple[List[dict], Dict[str, dict]]:
    """
    Ingest all enabled sources.
    Returns (all_raw_records, source_health).
    """
    all_records = []
    source_health = {}

    for source in sources:
        if not source.get("enabled", True):
            source_health[source["key"]] = {"status": "skipped", "fetched": 0, "error": None}
            continue

        logger.info(f"[ingest] fetching source: {source['key']} — {source['url']}")
        records, status, error = _fetch_source(source, limit=limit)

        source_health[source["key"]] = {
            "status": status,
            "fetched": len(records),
            "error": error,
        }

        if status == "error":
            logger.warning(f"[ingest] source {source['key']} failed: {error}")
        else:
            logger.info(f"[ingest] source {source['key']}: fetched {len(records)} records")
            all_records.extend(records)

    if not dry_run:
        raw_path = run_dir / "raw_regulations.jsonl"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with open(raw_path, "w", encoding="utf-8") as f:
            for record in all_records:
                f.write(json.dumps(record, ensure_ascii=True) + "\n")
        logger.info(f"[ingest] wrote {len(all_records)} raw records to {raw_path}")

    return all_records, source_health
