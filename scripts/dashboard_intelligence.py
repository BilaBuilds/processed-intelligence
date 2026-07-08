"""Normalize static dashboard exports without touching the core pipeline.

This module upgrades the Hostinger dashboard data layer after a raw export has
been produced. It keeps the original tender rows, adds product-facing fields,
builds buyer intelligence, and rewrites KPI values from the normalized data.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ASSIGNMENT_PREFIX = "window.PROCESSED_DASHBOARD_DATA = "

DIRECT_TERMS = {
    "nieuwbouw",
    "renovatie",
    "bouwkundig",
    "aannemer",
    "reconstructie",
    "riolering",
    "ontsluitingsweg",
    "rijkswaterstaat",
    "haven",
    "infrastructuur",
    "watergangen",
    "openbare ruimte",
    "civiel",
    "wegen",
    "brug",
    "kade",
    "public works",
    "highways",
    "drainage",
    "civil infrastructure",
}

ADJACENT_TERMS = {
    "werktuigbouwkundig",
    "elektrotechnisch",
    "ingenieursdiensten",
    "onderhoud",
    "engineering",
    "building",
    "facilities",
    "public sector",
}

INFRA_PHRASES = {
    "energie grid",
    "smart energy grid",
    "energy grid",
}

BUYER_SIGNAL_TERMS = {
    "rijkswaterstaat",
    "havenbedrijf",
    "gemeente",
    "provincie",
    "waternet",
    "hoogheemraadschap",
    "rijksvastgoedbedrijf",
}

SHORTLIST_THRESHOLD = 75


def load_dashboard_js(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if stripped.startswith(ASSIGNMENT_PREFIX):
        stripped = stripped[len(ASSIGNMENT_PREFIX) :]
    stripped = _first_json_object(stripped)
    return json.loads(stripped)


def write_dashboard_js(path: Path, data: dict[str, Any]) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(
        f"{ASSIGNMENT_PREFIX}{rendered};\n"
        "window.DASHBOARD_DATA = window.PROCESSED_DASHBOARD_DATA;\n"
        "window.dashboardData = window.PROCESSED_DASHBOARD_DATA;\n",
        encoding="utf-8",
    )


def _first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("Dashboard JS does not contain an object assignment.")
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("Dashboard JS object assignment is incomplete.")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def parse_datetime(value: Any, export_date: datetime | None = None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidates = [text, text.replace("Z", "+00:00")]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        candidates.append(f"{text}T23:59:59+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    short_match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", text)
    if short_match:
        day, month, year = short_match.groups()
        inferred_year = int(year) if year else (export_date or datetime.now(timezone.utc)).year
        if inferred_year < 100:
            inferred_year += 2000
        try:
            return datetime(inferred_year, int(month), int(day), 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def date_label(value: Any) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "Deadline unknown"
    return parsed.strftime("%d %b %Y")


def value_label(value: Any) -> str:
    if value in (None, "", "—", "-"):
        return "Value unknown"
    if isinstance(value, (int, float)) and value > 0:
        numeric = float(value)
    else:
        numeric_text = re.sub(r"[^0-9.]", "", str(value))
        numeric = float(numeric_text) if numeric_text else 0
    if numeric <= 0:
        return "Value unknown"
    if numeric >= 1_000_000:
        return f"£{numeric / 1_000_000:.1f}m"
    if numeric >= 1_000:
        return f"£{round(numeric / 1_000):,}k"
    return f"£{numeric:,.0f}"


def market_country(item: dict[str, Any]) -> str:
    text = normalize_text(
        " ".join(
            str(item.get(key, ""))
            for key in ("country", "market", "source", "region", "id", "source_id")
        )
    )
    if "nl" in text or "netherlands" in text or "tenderned" in text:
        return "NL"
    return str(item.get("country") or "UK").upper()


def term_hits(text: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if term in text)


def classify_relevance(item: dict[str, Any]) -> tuple[int, bool, list[str], str]:
    text = normalize_text(
        " ".join(
            str(item.get(key, ""))
            for key in (
                "title",
                "buyer",
                "buyer_name",
                "summary",
                "description",
                "rationale",
                "contract_type",
                "procedure",
            )
        )
    )
    direct_hits = term_hits(text, DIRECT_TERMS)
    adjacent_hits = term_hits(text, ADJACENT_TERMS)
    infra_hits = term_hits(text, INFRA_PHRASES)
    buyer_hits = term_hits(text, BUYER_SIGNAL_TERMS)
    hits = direct_hits + adjacent_hits + infra_hits + buyer_hits

    has_deadline = bool(item.get("deadline") or item.get("deadline_at"))
    has_buyer = bool(item.get("buyer") or item.get("buyer_name") or item.get("authority"))

    existing_score = _bounded_score(item.get("score") or item.get("fit_score") or item.get("commercial_score"))
    if direct_hits or infra_hits:
        score = 80
        score += min(10, (len(direct_hits) + len(infra_hits) - 1) * 4)
        score += 3 if has_buyer else 0
        score += 2 if has_deadline else 0
        reason = "Direct construction, civils, infrastructure, or public works signal."
    elif adjacent_hits and buyer_hits:
        score = 68 + min(8, len(adjacent_hits) * 3)
        reason = "Adjacent engineering/facilities signal from a relevant public buyer."
    elif adjacent_hits:
        score = 55 + min(9, len(adjacent_hits) * 3)
        reason = "Medium relevance adjacent construction or engineering signal."
    elif buyer_hits:
        score = 45 + min(8, len(buyer_hits) * 2)
        reason = "Relevant public-sector buyer signal; opportunity needs qualification."
    else:
        score = min(existing_score, 34)
        reason = "No strong construction or civils ICP signal detected."

    score = max(existing_score if existing_score >= 65 and hits else 0, score)
    score = max(0, min(95, int(round(score))))
    return score, score >= 45 and bool(hits), hits, reason


def _bounded_score(value: Any) -> int:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return 0
    if raw <= 1:
        raw *= 100
    return max(0, min(100, int(round(raw))))


def status_for(item: dict[str, Any], export_dt: datetime) -> str:
    deadline = parse_datetime(item.get("deadline") or item.get("deadline_at"), export_dt)
    if deadline is None:
        return "unknown_deadline"
    return "expired" if deadline < export_dt else "active"


def normalize_opportunity(item: dict[str, Any], export_dt: datetime) -> dict[str, Any]:
    row = deepcopy(item)
    score, icp_match, signals, reason = classify_relevance(row)
    status = status_for(row, export_dt)
    shortlist = bool(icp_match and status != "expired" and score >= SHORTLIST_THRESHOLD)
    country = market_country(row)

    row["score"] = score
    row["buyer"] = row.get("buyer") or row.get("buyer_name") or row.get("authority") or "Unknown buyer"
    row["title"] = row.get("title") or row.get("name") or row.get("notice_title") or "Untitled opportunity"
    row["country"] = country
    row["market"] = country
    row["source"] = row.get("source") or ("tenderned" if country == "NL" else "unknown")
    row["status"] = status
    row["icp_match"] = icp_match
    row["shortlist"] = shortlist
    row["value_label"] = value_label(row.get("value_amount", row.get("value")))
    row["deadline_label"] = date_label(row.get("deadline") or row.get("deadline_at"))
    row["relevance_reason"] = reason
    row["fit_signals"] = signals
    row["next_action"] = _next_action(row, score, status, shortlist)
    return row


def _next_action(row: dict[str, Any], score: int, status: str, shortlist: bool) -> str:
    if status == "expired":
        return "Archive; deadline has passed."
    if shortlist:
        return "Shortlist for bid/no-bid review."
    if score >= 55:
        return "Qualify scope and buyer fit."
    if row.get("icp_match"):
        return "Monitor as a weak ICP signal."
    return "No immediate action."


def build_buyer_intelligence(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in opportunities:
        buyer = str(item.get("buyer") or "Unknown buyer").strip()
        grouped[buyer].append(item)

    buyers = []
    for buyer, rows in grouped.items():
        active_rows = [row for row in rows if row.get("status") != "expired"]
        scores = [int(row.get("score") or 0) for row in rows]
        active_scores = [int(row.get("score") or 0) for row in active_rows]
        signals = Counter(signal for row in rows for signal in row.get("fit_signals", []))
        deadline_dates = [
            parsed
            for parsed in (parse_datetime(row.get("deadline") or row.get("deadline_at")) for row in active_rows)
            if parsed is not None
        ]
        seen_dates = [
            parsed
            for parsed in (parse_datetime(row.get("published_at") or row.get("publication_date")) for row in rows)
            if parsed is not None
        ]
        latest_deadline = max(deadline_dates, default=None)
        last_seen = max(seen_dates, default=None)
        avg_score = round(sum(active_scores or scores) / max(1, len(active_scores or scores)))
        buyers.append(
            {
                "buyer": buyer,
                "country": rows[0].get("country") or rows[0].get("market") or "UK",
                "region": rows[0].get("region") or "National",
                "opportunity_count": len(rows),
                "active_opportunities": len(active_rows),
                "average_score": avg_score,
                "top_categories": [name for name, _ in signals.most_common(4)] or ["general procurement"],
                "latest_deadline": latest_deadline.isoformat() if latest_deadline else None,
                "latest_deadline_label": date_label(latest_deadline.isoformat() if latest_deadline else None),
                "last_seen": last_seen.isoformat() if last_seen else None,
                "last_seen_label": date_label(last_seen.isoformat() if last_seen else None),
                "recommended_action": _buyer_action(avg_score, len(active_rows)),
            }
        )
    return sorted(buyers, key=lambda row: (row["average_score"], row["active_opportunities"]), reverse=True)


def _buyer_action(avg_score: int, active_count: int) -> str:
    if active_count and avg_score >= 75:
        return "Prioritise for immediate bid/no-bid review."
    if active_count and avg_score >= 55:
        return "Qualify active opportunities and buyer route."
    if active_count:
        return "Monitor; weak or adjacent signals only."
    return "Archive for buyer history."


def build_dashboard_payload(data: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(data)
    latest_run = output.setdefault("latestRun", {})
    generated_at = output.get("generated_at") or output.get("generatedAt") or latest_run.get("generated_at")
    export_dt = parse_datetime(generated_at) or datetime.now(timezone.utc)

    raw_tenders = latest_run.get("tenders") or output.get("tenders") or []
    opportunities = [normalize_opportunity(item, export_dt) for item in raw_tenders if isinstance(item, dict)]
    active_opportunities = [item for item in opportunities if item.get("status") != "expired"]
    icp_matched = [item for item in active_opportunities if item.get("icp_match")]
    shortlisted = [item for item in active_opportunities if item.get("shortlist")]
    buyers = build_buyer_intelligence(opportunities)
    avg_score = round(
        sum(int(item.get("score") or 0) for item in active_opportunities) / max(1, len(active_opportunities))
    )
    country_counts = Counter(item.get("country") or item.get("market") or "UK" for item in opportunities)

    latest_run["tenders"] = opportunities
    latest_run["buyers"] = buyers
    latest_run["buyer_intelligence"] = buyers
    latest_run["generated_at"] = generated_at or export_dt.isoformat()
    latest_run["metrics"] = {
        "tenders_ingested": len(opportunities),
        "icp_matched": len(icp_matched),
        "shortlisted": len(shortlisted),
        "avg_score": avg_score,
        "active_opportunities": len(active_opportunities),
        "expired_opportunities": len(opportunities) - len(active_opportunities),
        "buyer_count": len(buyers),
    }
    latest_run.setdefault("manifest", {}).update(
        {
            "ingest_total_count": len(opportunities),
            "icp_match_count": len(icp_matched),
            "shortlist_count": len(shortlisted),
            "buyer_watchlist_count": len(buyers),
            "avg_fit_score": avg_score,
        }
    )

    output["dashboard_version"] = "hostinger_static_v3_intelligence"
    output["total_tenders"] = len(opportunities)
    output["total_opportunities"] = len(opportunities)
    output["icp_match_count"] = len(icp_matched)
    output["shortlist_count"] = len(shortlisted)
    output["buyer_count"] = len(buyers)
    output["avg_fit_score"] = avg_score
    output["buyer_intelligence"] = buyers
    output["country_counts"] = dict(country_counts)
    output["market_notice"] = "No UK records in this export" if country_counts.get("UK", 0) == 0 else ""
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize dashboard intelligence export.")
    parser.add_argument("path", nargs="?", default="dashboard_data.js")
    args = parser.parse_args()
    path = Path(args.path)
    data = load_dashboard_js(path)
    normalized = build_dashboard_payload(data)
    write_dashboard_js(path, normalized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
