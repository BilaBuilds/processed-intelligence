import hashlib
from dataclasses import dataclass, field
from typing import List


VALID_REGIONS = {"London", "West Midlands", "Oxfordshire", "National", "Unknown"}
VALID_IMPACT_TYPES = {
    "code_change", "permit", "environment", "safety",
    "planning", "consultation", "other"
}


@dataclass
class RegulationRecord:
    id: str
    title: str
    authority: str
    region: str
    published_at: str
    effective_at: str
    url: str
    summary: str
    source: str
    trade_tags: List[str]
    impact_type: str
    raw_text: str
    relevance_score: int
    relevance_reasons: List[str]

    def __post_init__(self):
        missing = []
        required_str = ["id", "title", "authority", "region", "published_at",
                        "effective_at", "url", "summary", "source", "impact_type", "raw_text"]
        for f in required_str:
            if getattr(self, f) is None:
                missing.append(f)
        if self.trade_tags is None:
            missing.append("trade_tags")
        if self.relevance_reasons is None:
            missing.append("relevance_reasons")
        if self.relevance_score is None:
            missing.append("relevance_score")
        if missing:
            raise ValueError(f"RegulationRecord missing required fields: {missing}")


def make_record_id(url: str, title: str, published_date: str) -> str:
    payload = (url + title + published_date).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def validate_record(record: dict) -> List[str]:
    errors = []
    required_fields = [
        "id", "title", "authority", "region", "published_at", "effective_at",
        "url", "summary", "source", "trade_tags", "impact_type", "raw_text",
        "relevance_score", "relevance_reasons"
    ]
    for f in required_fields:
        if f not in record:
            errors.append(f"missing field: {f}")
    return errors


def record_to_dict(record: RegulationRecord) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "authority": record.authority,
        "region": record.region,
        "published_at": record.published_at,
        "effective_at": record.effective_at,
        "url": record.url,
        "summary": record.summary,
        "source": record.source,
        "trade_tags": record.trade_tags,
        "impact_type": record.impact_type,
        "raw_text": record.raw_text,
        "relevance_score": record.relevance_score,
        "relevance_reasons": record.relevance_reasons,
    }


def dict_to_record(d: dict) -> RegulationRecord:
    errors = validate_record(d)
    if errors:
        raise ValueError(f"Invalid record dict: {errors}")
    return RegulationRecord(
        id=d["id"],
        title=d["title"],
        authority=d["authority"],
        region=d["region"],
        published_at=d["published_at"],
        effective_at=d["effective_at"],
        url=d["url"],
        summary=d["summary"],
        source=d["source"],
        trade_tags=list(d["trade_tags"]),
        impact_type=d["impact_type"],
        raw_text=d["raw_text"],
        relevance_score=int(d["relevance_score"]),
        relevance_reasons=list(d["relevance_reasons"]),
    )
