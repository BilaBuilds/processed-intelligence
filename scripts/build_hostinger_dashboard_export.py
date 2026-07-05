from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUTS = [
    Path("C:/Dev/dutch_output/dutch_tenders.json"),
    Path("C:/Dev/dutch_output/dutch_tenders.jsonl"),
    BASE_DIR / "data" / "export" / "tenderned_latest.json",
    BASE_DIR / "data" / "dashboard" / "tenderned_latest.json",
    BASE_DIR / "data" / "export" / "dashboard_data.json",
    BASE_DIR / "data" / "dashboard" / "dashboard_data.json",
    BASE_DIR / "dashboard_data.json",
]

JS_ASSIGNMENT_RE = re.compile(r"window\.([A-Za-z_$][\w$]*)\s*=")
CONSTRUCTION_KEYWORDS = (
    "bouw",
    "renovatie",
    "reconstructie",
    "aannemer",
    "ingenieursdiensten",
    "riolering",
    "watergangen",
    "wegen",
    "onderhoud",
    "vastgoed",
    "infrastructuur",
)
PUBLIC_BUYER_KEYWORDS = (
    "gemeente",
    "provincie",
    "ministerie",
    "rijkswaterstaat",
    "waterschap",
    "universiteit",
)
PRODUCT_RAILS = {
    "Construction / Build": ("bouw", "nieuwbouw", "renovatie", "vastgoed", "aannemer"),
    "Civils / Infrastructure": ("civils", "infrastructuur", "riolering", "watergangen", "wegen", "reconstructie"),
    "ICT / Digital": ("ict", "digital", "software", "hardware", "werkplek", "data", "cloud", "systeem"),
    "Professional Services": ("advies", "consultancy", "ingenieursdiensten", "onderzoek", "diensten"),
    "Facilities / Maintenance": ("facilities", "onderhoud", "beheer", "schoonmaak", "installatie"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_file(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            item = json.loads(text)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def load_input(path: Path) -> tuple[Any, str]:
    if path.suffix.lower() == ".jsonl":
        return load_jsonl_file(path), str(path)
    return load_json_file(path), str(path)


def find_input(explicit_input: Path | None, output_dir: Path, dashboard_dir: Path) -> tuple[Any, str]:
    if explicit_input:
        candidates = [
            explicit_input,
            output_dir / "tenderned_latest.json",
            dashboard_dir / "tenderned_latest.json",
            output_dir / "dashboard_data.json",
            dashboard_dir / "dashboard_data.json",
            BASE_DIR / "dashboard_data.json",
        ]
    else:
        candidates = [
            Path("C:/Dev/dutch_output/dutch_tenders.json"),
            Path("C:/Dev/dutch_output/dutch_tenders.jsonl"),
            output_dir / "tenderned_latest.json",
            dashboard_dir / "tenderned_latest.json",
            output_dir / "dashboard_data.json",
            dashboard_dir / "dashboard_data.json",
            BASE_DIR / "dashboard_data.json",
        ]
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.stat().st_size > 0:
            return load_input(candidate)
    return {"tenders": [], "opportunities": []}, "empty_fallback"


def extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    latest = payload.get("latestRun") if isinstance(payload.get("latestRun"), dict) else {}
    for key_payload in (
        latest.get("tenders"),
        latest.get("opportunities"),
        payload.get("tenders"),
        payload.get("opportunities"),
    ):
        if isinstance(key_payload, list):
            return [item for item in key_payload if isinstance(item, dict)]
    return []


def first_present(record: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def normalize_tender(record: dict[str, Any], index: int) -> dict[str, Any]:
    source = str(first_present(record, ["source"], "tenderned") or "tenderned")
    country = str(first_present(record, ["country"], "NL") or "NL")
    source_id = first_present(record, ["source_id", "id", "notice_id", "publicatieId"], "")
    source_id = str(source_id or "")
    title = str(first_present(record, ["title", "aanbestedingNaam"], "") or "")
    buyer = str(first_present(record, ["buyer", "buyer_name", "opdrachtgeverNaam"], "") or "")
    published = first_present(record, ["published_at", "publication_date", "publicatieDatum"], None)
    deadline = first_present(record, ["deadline", "sluitingsDatum"], None)
    procedure = first_present(record, ["procedure", "procedure_name", "procedure_code"], None)
    contract_type = first_present(record, ["contract_type", "type_name", "type_code"], None)
    url = first_present(record, ["url", "publicatieUrl", "link"], None)
    region = first_present(record, ["region", "nuts_region", "location"], None)
    value = first_present(record, ["value", "value_amount", "estimated_value"], None)
    score = first_present(record, ["score", "match_score"], None)

    stable_id = f"{source}:{source_id}" if source_id else f"{source}:row-{index}"
    normalized = {
        "id": stable_id,
        "source_id": source_id,
        "source": source,
        "country": country,
        "title": title,
        "buyer": buyer,
        "region": region or ("Netherlands" if country == "NL" else ""),
        "deadline": deadline,
        "value": value,
        "publication_date": published,
        "published_at": published,
        "procedure": procedure,
        "contract_type": contract_type,
        "url": url,
        "score": score,
    }
    if "raw" in record:
        normalized["raw"] = record["raw"]
    normalized = enrich_tender(normalized)
    return normalized


def parse_sort_key(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def deadline_is_future(value: Any) -> bool:
    parsed = parse_sort_key(value)
    if parsed == datetime.min.replace(tzinfo=timezone.utc):
        return False
    return parsed > datetime.now(timezone.utc)


def calculate_score(tender: dict[str, Any]) -> int:
    current = tender.get("score")
    try:
        if current not in (None, ""):
            return max(0, min(100, int(float(current))))
    except (TypeError, ValueError):
        pass

    score = 0
    title = str(tender.get("title") or "").lower()
    buyer = str(tender.get("buyer") or "").lower()
    contract_type = str(tender.get("contract_type") or "").lower()

    if contract_type == "works" or contract_type == "w":
        score += 20
    if any(keyword in title for keyword in CONSTRUCTION_KEYWORDS):
        score += 15
    if any(keyword in buyer for keyword in PUBLIC_BUYER_KEYWORDS):
        score += 10
    if deadline_is_future(tender.get("deadline")):
        score += 10
    return min(score, 100)


def decision_for_score(score: int) -> str:
    if score >= 35:
        return "Review"
    if score >= 20:
        return "Monitor"
    return "Low fit"


def confidence_for_tender(tender: dict[str, Any]) -> str:
    if tender.get("title") and tender.get("buyer") and tender.get("deadline"):
        return "medium"
    return "low"


def enrich_tender(tender: dict[str, Any]) -> dict[str, Any]:
    score = calculate_score(tender)
    decision = decision_for_score(score)
    tender["score"] = score
    tender["decision"] = tender.get("decision") or decision
    tender["verdict"] = tender.get("verdict") or decision
    tender["confidence"] = tender.get("confidence") or confidence_for_tender(tender)
    tender.setdefault("region", "Netherlands" if tender.get("country") == "NL" else "")
    tender.setdefault("value", None)
    tender.setdefault("url", None)
    tender.setdefault("deadline", None)
    tender.setdefault("published_at", tender.get("publication_date"))
    tender.setdefault("publication_date", tender.get("published_at"))
    tender.setdefault("procedure", None)
    tender.setdefault("contract_type", None)
    tender["summary"] = tender.get("summary") or build_opportunity_summary(tender)
    tender["description"] = tender.get("description") or tender["summary"]
    tender["rationale"] = tender.get("rationale") or build_rationale(tender)
    tender["next_step"] = tender.get("next_step") or build_next_step(tender)
    return tender


def format_display_date(value: Any) -> str:
    parsed = parse_sort_key(value)
    if parsed == datetime.min.replace(tzinfo=timezone.utc):
        return "no published deadline"
    return parsed.strftime("%d %b %y")


def build_opportunity_summary(tender: dict[str, Any]) -> str:
    buyer = tender.get("buyer") or "Unknown buyer"
    deadline = format_display_date(tender.get("deadline")) if tender.get("deadline") else "no deadline published"
    decision = tender.get("decision") or "Monitor"
    return (
        f"Dutch public-sector opportunity from {buyer}. "
        f"Deadline {deadline}. "
        f"Classified as {decision} based on construction/civils fit signals."
    )


def build_rationale(tender: dict[str, Any]) -> str:
    score = int(tender.get("score") or 0)
    if score >= 45:
        return "Strong fit from Dutch public-sector buyer, deadline visibility, and construction or infrastructure keywords."
    if score >= 20:
        return "Relevant Dutch opportunity with enough fit signals to monitor or qualify."
    return "Low current fit signal; keep visible for market awareness."


def build_next_step(tender: dict[str, Any]) -> str:
    score = int(tender.get("score") or 0)
    if score >= 45:
        return "Review scope and qualify for outreach."
    if score >= 20:
        return "Monitor and check buyer fit."
    return "No immediate action."
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for index, record in enumerate(records):
        normalized = normalize_tender(record, index)
        key = (normalized["source"], normalized["source_id"] or normalized["id"])
        if key not in deduped:
            deduped[key] = normalized
    tenders = list(deduped.values())
    tenders.sort(key=lambda item: parse_sort_key(item.get("published_at") or item.get("publication_date")), reverse=True)
    return tenders


def build_kpis(tenders: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    buyers = {str(item.get("buyer") or "").strip() for item in tenders if str(item.get("buyer") or "").strip()}
    shortlist_count = sum(1 for item in tenders if int(item.get("score") or 0) >= 20)
    avg_fit_score = calculate_avg_fit_score(tenders)
    hot_outreach_count = sum(1 for item in tenders if int(item.get("score") or 0) >= 45)
    warm_buyers = len(build_warm_buyers(tenders))
    timing_ready = len(build_timing_ready(tenders))
    products = len(build_product_rails(tenders))
    return {
        "total_tenders": len(tenders),
        "total_opportunities": len(tenders),
        "nl_opportunities": sum(1 for item in tenders if item.get("country") == "NL"),
        "uk_opportunities": sum(1 for item in tenders if item.get("country") == "UK"),
        "unique_buyers": len(buyers),
        "with_deadline": sum(1 for item in tenders if item.get("deadline")),
        "shortlist_count": shortlist_count,
        "buyer_count": len(buyers),
        "pipeline_runs": 1 if tenders else 0,
        "avg_fit_score": avg_fit_score,
        "hot_outreach_count": hot_outreach_count,
        "warm_buyers": warm_buyers,
        "timing_ready": timing_ready,
        "products": products,
        "generated_at": generated_at,
    }


def calculate_avg_fit_score(tenders: list[dict[str, Any]]) -> int:
    scored = [int(item.get("score") or 0) for item in tenders]
    if not scored:
        return 0
    return round(sum(scored) / len(scored))


def build_top_buyers(tenders: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    cards = build_buyer_cards(tenders)
    return [
        {
            "buyer": card["buyer"],
            "tender_count": card["tender_count"],
            "count": card["tender_count"],
            "latest_deadline": card["latest_deadline"],
            "country": card["country"],
            "source": card["source"],
        }
        for card in cards[:limit]
    ]


def build_buyer_cards(tenders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for tender in tenders:
        buyer = str(tender.get("buyer") or "").strip()
        if buyer:
            grouped.setdefault(buyer, []).append(tender)

    cards: list[dict[str, Any]] = []
    for buyer, items in grouped.items():
        deadlines = [item.get("deadline") for item in items if item.get("deadline")]
        latest_deadline = max(deadlines, key=parse_sort_key) if deadlines else None
        best_score = max(int(item.get("score") or 0) for item in items)
        cards.append(
            {
                "key": re.sub(r"[^a-z0-9]+", "_", buyer.lower()).strip("_"),
                "name": buyer,
                "buyer": buyer,
                "buyer_name": buyer,
                "tender_count": len(items),
                "latest_deadline": latest_deadline,
                "country": first_present(items[0], ["country"], "NL"),
                "source": first_present(items[0], ["source"], "tenderned"),
                "score": best_score,
                "opportunities": len(items),
            }
        )
    cards.sort(key=lambda card: (-card["tender_count"], str(card["buyer"]).lower()))
    return cards


def build_hot_outreach(tenders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in tenders if int(item.get("score") or 0) >= 45]


def build_warm_buyers(tenders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relevant = [item for item in tenders if int(item.get("score") or 0) >= 20]
    return build_buyer_cards(relevant)


def build_timing_ready(tenders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in tenders
        if int(item.get("score") or 0) >= 35 and deadline_is_future(item.get("deadline"))
    ]


def product_bucket(tender: dict[str, Any]) -> str:
    text = " ".join(
        str(tender.get(key) or "").lower()
        for key in ("title", "description", "summary", "contract_type", "procedure")
    )
    for name, keywords in PRODUCT_RAILS.items():
        if any(keyword in text for keyword in keywords):
            return name
    return "Other"


def build_product_rails(tenders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for tender in tenders:
        grouped.setdefault(product_bucket(tender), []).append(tender)
    rails = []
    for name, items in grouped.items():
        rails.append(
            {
                "id": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
                "name": name,
                "count": len(items),
                "tenders": items,
                "top_score": max((int(item.get("score") or 0) for item in items), default=0),
            }
        )
    rails.sort(key=lambda item: (-item["count"], item["name"]))
    return rails


def build_pipeline_model() -> dict[str, Any]:
    return {
        "run_id": "latest",
        "loop_steps": 1,
        "post_run_steps": 1,
        "fatal_steps": 0,
        "non_fatal_steps": ["static_hostinger_export"],
        "supplier_source": "tenderned_json",
        "notifier_channels": ["hostinger_static"],
        "runtime_verified": False,
        "vps_verified": False,
    }


def build_dashboard_payload(
    tenders: list[dict[str, Any]],
    *,
    data_source: str,
    limit: int = 200,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or utc_now()
    visible = tenders[:limit]
    shortlist_all = [item for item in tenders if int(item.get("score") or 0) >= 20]
    shortlist = shortlist_all[:limit]
    buyer_cards = build_buyer_cards(tenders)
    warm_buyers = build_warm_buyers(tenders)
    hot_outreach = build_hot_outreach(tenders)
    timing_ready = build_timing_ready(tenders)
    product_rails = build_product_rails(tenders)
    pipeline_model = build_pipeline_model()
    top_buyers = build_top_buyers(tenders)
    kpis = build_kpis(tenders, generated)
    avg_fit_score = kpis["avg_fit_score"]
    summary = {
        "total_available": len(tenders),
        "included": len(visible),
        "data_source": data_source,
        "generated_at": generated,
        "countries": dict(Counter(item.get("country") or "" for item in tenders)),
        "tenders": len(tenders),
        "opportunities": len(tenders),
        "buyers": len(buyer_cards),
        "shortlist": len(shortlist_all),
        "avg_fit_score": avg_fit_score,
        "hot_outreach": len(hot_outreach),
        "warm_buyers": len(warm_buyers),
        "timing_ready": len(timing_ready),
        "products": len(product_rails),
    }
    return {
        "generated_at": generated,
        "generatedAt": generated,
        "status": "ready",
        "source": "processed_intelligence",
        "dashboard_version": "hostinger_static_v2",
        "total_tenders": len(tenders),
        "total_opportunities": len(tenders),
        "shortlist_count": len(shortlist_all),
        "buyer_count": len(buyer_cards),
        "client_count": 0,
        "pipeline_runs": 1 if tenders else 0,
        "avg_fit_score": avg_fit_score,
        "hot_outreach_count": len(hot_outreach),
        "warm_buyers_count": len(warm_buyers),
        "timing_ready_count": len(timing_ready),
        "products_count": len(product_rails),
        "loop_steps": pipeline_model["loop_steps"],
        "post_run_steps": pipeline_model["post_run_steps"],
        "fatal_steps": pipeline_model["fatal_steps"],
        "supplier_source": pipeline_model["supplier_source"],
        "notifier_channels": pipeline_model["notifier_channels"],
        "pipeline_model": pipeline_model,
        "latestRunId": "latest",
        "latestRun": {
            "id": "latest",
            "runId": "latest",
            "status": "ready",
            "generated_at": generated,
            "finished_at": generated,
            "manifest": {
                "status": "ready",
                "shortlist_count": len(shortlist_all),
                "buyer_watchlist_count": len(buyer_cards),
                "client_count": 0,
                "pipeline_runs": 1 if tenders else 0,
                "ingest_total_count": len(tenders),
                "avg_fit_score": avg_fit_score,
                "hot_outreach_count": len(hot_outreach),
                "warm_buyers": len(warm_buyers),
                "timing_ready": len(timing_ready),
            },
            "tenders": visible,
            "opportunities": visible,
            "shortlist": shortlist,
            "buyers": buyer_cards,
            "buyerCards": buyer_cards,
            "clients": [],
            "products": product_rails,
            "product_rails": product_rails,
            "hot_outreach": hot_outreach,
            "outreach_queue": hot_outreach,
            "warm_buyers": warm_buyers,
            "timing_ready": timing_ready,
            "buyerTiming": {"signals": []},
            "buyerTimingBacktest": {},
            "commercialRadar": {"focus": [], "focus_summary": []},
            "outreachQueue": {"records": [], "counts": {}},
            "summary": summary,
        },
        "tenders": visible,
        "opportunities": visible,
        "shortlist": shortlist,
        "buyers": buyer_cards,
        "buyerCards": buyer_cards,
        "top_buyers": top_buyers,
        "hot_outreach": hot_outreach,
        "outreach_queue": hot_outreach,
        "warm_buyers": warm_buyers,
        "timing_ready": timing_ready,
        "products": product_rails,
        "product_rails": product_rails,
        "kpis": kpis,
        "system_health": {
            "status": "ready",
            "data_source": data_source,
            "vps_verified": False,
            "hostinger_ready": True,
            "notes": [
                "Static Hostinger export generated locally.",
                "VPS sync was not verified in this session.",
                "Dashboard includes tenders/opportunities aliases for compatibility.",
            ],
        },
        "alerts": [],
        "clients": [],
        "products": product_rails,
        "runHistory": [
            {
                "run_id": "latest",
                "status": "ready",
                "shortlist_count": len(shortlist_all),
                "ingest_total_count": len(tenders),
                "finished_at": generated,
            }
        ] if tenders else [],
    }


def build_tenderned_payload(tenders: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "source": "tenderned",
        "country": "NL",
        "latestRun": {
            "tenders": tenders,
            "opportunities": tenders,
        },
        "tenders": tenders,
        "opportunities": tenders,
    }


def detect_existing_window_aliases(paths: list[Path]) -> list[str]:
    aliases = {"PROCESSED_DASHBOARD_DATA", "dashboardData", "DASHBOARD_DATA"}
    for path in paths:
        if not path.exists():
            continue
        try:
            for match in JS_ASSIGNMENT_RE.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                aliases.add(match.group(1))
        except OSError:
            continue
    return sorted(aliases)


def js_content(payload: dict[str, Any], aliases: list[str]) -> str:
    json_blob = json.dumps(payload, ensure_ascii=False, indent=2)
    lines = [f"window.PROCESSED_DASHBOARD_DATA = {json_blob};"]
    for alias in aliases:
        if alias == "PROCESSED_DASHBOARD_DATA":
            continue
        lines.append(f"window.{alias} = window.PROCESSED_DASHBOARD_DATA;")
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], tenderned_payload: dict[str, Any], output_dir: Path, dashboard_dir: Path) -> list[Path]:
    bundle_dir = output_dir / "hostinger_upload_bundle"
    targets_json = [
        output_dir / "dashboard_data.json",
        dashboard_dir / "dashboard_data.json",
        bundle_dir / "dashboard_data.json",
    ]
    aliases = detect_existing_window_aliases([output_dir / "dashboard_data.js", dashboard_dir / "dashboard_data.js"])
    js = js_content(payload, aliases)
    targets_js = [
        output_dir / "dashboard_data.js",
        dashboard_dir / "dashboard_data.js",
        bundle_dir / "dashboard_data.js",
    ]
    tenderned_targets = [
        output_dir / "tenderned_latest.json",
        dashboard_dir / "tenderned_latest.json",
        bundle_dir / "tenderned_latest.json",
    ]

    written: list[Path] = []
    for path in targets_json:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    for path in targets_js:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(js, encoding="utf-8")
        written.append(path)
    for path in tenderned_targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tenderned_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def build_export(input_path: Path | None, output_dir: Path, dashboard_dir: Path, limit: int = 200) -> tuple[dict[str, Any], list[Path]]:
    payload_raw, source = find_input(input_path, output_dir, dashboard_dir)
    records = extract_records(payload_raw)
    tenders = normalize_records(records)
    generated = utc_now()
    payload = build_dashboard_payload(tenders, data_source=source, limit=limit, generated_at=generated)
    tenderned_payload = build_tenderned_payload(tenders, generated)
    written = write_outputs(payload, tenderned_payload, output_dir, dashboard_dir)
    return payload, written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Hostinger-ready static dashboard exports.")
    parser.add_argument("--input", type=Path, default=None, help="Optional explicit input JSON/JSONL file.")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "data" / "export")
    parser.add_argument("--dashboard-dir", type=Path, default=BASE_DIR / "data" / "dashboard")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv)

    payload, written = build_export(args.input, args.output_dir, args.dashboard_dir, limit=args.limit)
    scored = sorted(
        (payload.get("tenders") or []),
        key=lambda item: int(item.get("score") or 0),
        reverse=True,
    )
    print(f"total_tenders={payload.get('total_tenders', 0)}")
    print(f"total_opportunities={payload.get('total_opportunities', 0)}")
    print(f"unique_buyers={(payload.get('kpis') or {}).get('unique_buyers', 0)}")
    print(f"shortlist_count={payload.get('shortlist_count', 0)}")
    print(f"avg_fit_score={payload.get('avg_fit_score', 0)}")
    print(f"hot_outreach_count={payload.get('hot_outreach_count', 0)}")
    print(f"warm_buyers_count={len(payload.get('warm_buyers') or [])}")
    print(f"timing_ready_count={len(payload.get('timing_ready') or [])}")
    print(f"products_count={len(payload.get('products') or [])}")
    print(f"score_gt_0={sum(1 for item in payload.get('tenders') or [] if int(item.get('score') or 0) > 0)}")
    print("top_5_opportunities_with_summary=")
    for item in scored[:5]:
        print(
            json.dumps(
                {
                    "source_id": item.get("source_id"),
                    "title": item.get("title"),
                    "buyer": item.get("buyer"),
                    "score": item.get("score"),
                    "decision": item.get("decision"),
                    "summary": item.get("summary"),
                },
                ensure_ascii=False,
            )
        )
    print(f"Hostinger dashboard export ready: {len(payload.get('tenders') or [])} visible tender(s)")
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
