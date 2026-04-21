import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List

from .schema import RegulationRecord, record_to_dict

logger = logging.getLogger(__name__)

BOOSTED_AUTHORITIES = {"Environment Agency", "HSE", "MHCLG", "Planning Portal"}
BOOSTED_IMPACT_TYPES = {"code_change", "permit", "safety"}
BOOSTED_REGIONS = {"London", "West Midlands", "Oxfordshire"}
RECENT_DAYS = 30


def _is_recent(published_at: str) -> bool:
    if not published_at:
        return False
    try:
        pub_date = datetime.strptime(published_at, "%Y-%m-%d").date()
        return (date.today() - pub_date).days <= RECENT_DAYS
    except ValueError:
        return False


def score_record(record: RegulationRecord) -> RegulationRecord:
    score = 0
    reasons = []

    # +20 per trade_tag matched, cap at 40
    tag_boost = min(len(record.trade_tags) * 20, 40)
    if tag_boost > 0:
        score += tag_boost
        for tag in record.trade_tags:
            reasons.append(f"matched: {tag}")

    # +15 if region in boosted set
    if record.region in BOOSTED_REGIONS:
        score += 15
        reasons.append(f"region: {record.region}")

    # +10 if impact_type is boosted
    if record.impact_type in BOOSTED_IMPACT_TYPES:
        score += 10
        reasons.append(f"impact: {record.impact_type}")

    # +10 if authority is boosted
    if record.authority in BOOSTED_AUTHORITIES:
        score += 10
        reasons.append(f"authority: {record.authority}")

    # +5 if published within last 30 days
    if _is_recent(record.published_at):
        score += 5
        reasons.append("recent: published within 30 days")

    score = min(score, 100)

    return RegulationRecord(
        id=record.id,
        title=record.title,
        authority=record.authority,
        region=record.region,
        published_at=record.published_at,
        effective_at=record.effective_at,
        url=record.url,
        summary=record.summary,
        source=record.source,
        trade_tags=record.trade_tags,
        impact_type=record.impact_type,
        raw_text=record.raw_text,
        relevance_score=score,
        relevance_reasons=reasons,
    )


def run_match(
    normalized: List[RegulationRecord],
    run_dir: Path,
    dry_run: bool = False,
) -> List[RegulationRecord]:
    scored = [score_record(r) for r in normalized]

    if not dry_run:
        out_path = run_dir / "scored_regulations.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in scored:
                f.write(json.dumps(record_to_dict(rec), ensure_ascii=True) + "\n")
        logger.info(f"[match] wrote {len(scored)} scored records to {out_path}")

    return scored
