from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests
from defusedxml import ElementTree
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2"
RAW_XML_DIR = Path("data/dutch/raw/tenderned_xml")
NORMALIZED_JSONL_PATH = Path("data/dutch/processed/tenderned_publications_normalized.jsonl")
READINESS_PATH = Path("data/dutch/source_readiness/tenderned_xml_readiness.json")
MISSING_CREDENTIALS_MESSAGE = (
    "TenderNed XML credentials not configured; skipping live fetch."
)


def extract_publicatie_id(url_or_id: str) -> str:
    value = str(url_or_id or "").strip()
    if not value:
        raise ValueError("TenderNed publicatieId is required")

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        query = parse_qs(parsed.query)
        for key in ("publicatieId", "publicatieid", "publicationId", "id"):
            if query.get(key):
                return query[key][0].strip()

        path_parts = [part for part in parsed.path.split("/") if part]
        for marker in ("publicaties", "publicatie", "publications", "publication"):
            if marker in path_parts:
                index = path_parts.index(marker)
                if index + 1 < len(path_parts):
                    return path_parts[index + 1].strip()
        if path_parts:
            return path_parts[-1].strip()

    return value


def fetch_publication_xml(
    publicatie_id: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    load_env: bool = True,
) -> dict[str, Any]:
    if load_env:
        load_dotenv()

    username = os.getenv("TENDERNED_XML_USERNAME")
    password = os.getenv("TENDERNED_XML_PASSWORD")
    base_url = os.getenv("TENDERNED_XML_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    normalized_id = extract_publicatie_id(publicatie_id)
    source_url = (
        f"{base_url}/publicaties/{quote(normalized_id, safe='')}/public-xml"
    )

    if not username or not password:
        LOGGER.info(MISSING_CREDENTIALS_MESSAGE)
        return {
            "status": "skipped",
            "reason": "missing_credentials",
            "message": MISSING_CREDENTIALS_MESSAGE,
            "publicatieId": normalized_id,
            "source_url": source_url,
        }

    client = session or requests.Session()
    try:
        response = client.get(
            source_url,
            auth=(username, password),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        LOGGER.warning("TenderNed XML fetch failed for %s: %s", normalized_id, exc)
        return {
            "status": "error",
            "reason": "request_failed",
            "message": str(exc),
            "publicatieId": normalized_id,
            "source_url": source_url,
        }

    if response.status_code in {401, 403}:
        LOGGER.warning(
            "TenderNed XML fetch unauthorized for %s: HTTP %s",
            normalized_id,
            response.status_code,
        )
        return {
            "status": "error",
            "reason": "unauthorized",
            "http_status": response.status_code,
            "message": "TenderNed XML request was not authorized.",
            "publicatieId": normalized_id,
            "source_url": source_url,
        }

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning(
            "TenderNed XML fetch failed for %s: HTTP %s",
            normalized_id,
            response.status_code,
        )
        return {
            "status": "error",
            "reason": "http_error",
            "http_status": response.status_code,
            "message": str(exc),
            "publicatieId": normalized_id,
            "source_url": source_url,
        }

    return {
        "status": "ok",
        "publicatieId": normalized_id,
        "xml_text": response.text,
        "source_url": source_url,
    }


def parse_publication_xml(xml_text: str) -> dict[str, Any]:
    root = ElementTree.fromstring(xml_text.encode("utf-8"))
    values = _flatten_xml(root)
    links = _extract_links(root)
    lots = _extract_lots(root)

    parsed = {
        "title": _first_value(
            values,
            "title",
            "name",
            "procurementprojectname",
            "tender_title",
            "objectdesctitle",
        ),
        "description": _first_value(
            values,
            "description",
            "descriptiontext",
            "shortdescription",
            "procurementprojectdescription",
            "objectdescshortdescr",
        ),
        "buyer": _first_value(
            values,
            "buyer",
            "contractingauthority",
            "contractingpartyname",
            "officialname",
            "name",
        ),
        "cpv_codes": _cpv_codes(root, values),
        "publication_date": _first_value(
            values,
            "publicationdate",
            "noticedispatchdate",
            "dispatchdate",
            "dateofpublication",
        ),
        "deadline_date": _first_value(
            values,
            "deadlinedate",
            "tendersreceiptdates",
            "receiptdatetenders",
            "submissiondeadline",
        ),
        "procedure_type": _first_value(
            values,
            "proceduretype",
            "typeofprocedure",
            "procedurecode",
        ),
        "notice_type": _first_value(
            values,
            "noticetype",
            "noticekind",
            "formtype",
        ),
        "contract_value": _first_value(
            values,
            "contractvalue",
            "estimatedvalue",
            "totalvalue",
            "value",
        ),
        "currency": _first_value(values, "currency", "currencyid"),
        "lots": lots,
        "links": links,
    }
    return parsed


def normalize_publication(parsed_xml: dict[str, Any]) -> dict[str, Any]:
    publicatie_id = parsed_xml.get("publicatieId") or parsed_xml.get("publicatie_id")
    raw_xml_path = parsed_xml.get("raw_xml_path")
    source_url = parsed_xml.get("source_url")

    return {
        "publicatieId": publicatie_id,
        "source": "tenderned_xml",
        "country": "NL",
        "language": parsed_xml.get("language") or "nl",
        "title": parsed_xml.get("title"),
        "description": parsed_xml.get("description"),
        "buyer": parsed_xml.get("buyer"),
        "cpv_codes": parsed_xml.get("cpv_codes") or [],
        "publication_date": parsed_xml.get("publication_date"),
        "deadline_date": parsed_xml.get("deadline_date"),
        "procedure_type": parsed_xml.get("procedure_type"),
        "notice_type": parsed_xml.get("notice_type"),
        "contract_value": _numeric_value(parsed_xml.get("contract_value")),
        "currency": parsed_xml.get("currency"),
        "lots": parsed_xml.get("lots") or [],
        "links": parsed_xml.get("links") or [],
        "source_url": source_url,
        "raw_xml_path": str(raw_xml_path) if raw_xml_path else None,
    }


def save_raw_xml(
    publicatie_id: str,
    xml_text: str,
    *,
    raw_dir: str | Path = RAW_XML_DIR,
) -> Path:
    normalized_id = extract_publicatie_id(publicatie_id)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized_id)
    output_dir = Path(raw_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_id}.xml"
    output_path.write_text(xml_text, encoding="utf-8")
    return output_path


def append_normalized_publication(
    publication: dict[str, Any],
    *,
    output_path: str | Path = NORMALIZED_JSONL_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(publication, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    return path


def _flatten_xml(root: ElementTree.Element) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for element in root.iter():
        key = _local_name(element.tag)
        text = (element.text or "").strip()
        if text:
            values.setdefault(key, []).append(text)
        for attr_key, attr_value in element.attrib.items():
            attr_text = str(attr_value).strip()
            if attr_text:
                values.setdefault(_local_name(attr_key), []).append(attr_text)
    return values


def _first_value(values: dict[str, list[str]], *keys: str) -> str | None:
    wanted = {_normalize_key(key) for key in keys}
    for key, candidates in values.items():
        if key in wanted and candidates:
            return candidates[0]
    return None


def _cpv_codes(
    root: ElementTree.Element,
    values: dict[str, list[str]],
) -> list[str]:
    codes: set[str] = set()
    for element in root.iter():
        tag = _local_name(element.tag)
        if "cpv" not in tag:
            continue
        text = (element.text or "").strip()
        if text:
            codes.update(re.findall(r"\b\d{8}\b", text))
        for attr_value in element.attrib.values():
            codes.update(re.findall(r"\b\d{8}\b", str(attr_value)))

    for key, candidates in values.items():
        if "cpv" in key or key in {"code", "mainvocabularycode"}:
            for value in candidates:
                codes.update(re.findall(r"\b\d{8}\b", value))
    return sorted(codes)


def _extract_links(root: ElementTree.Element) -> list[str]:
    links: set[str] = set()
    for element in root.iter():
        for value in list(element.attrib.values()) + [(element.text or "")]:
            text = str(value).strip()
            if text.startswith(("http://", "https://")):
                links.add(text)
    return sorted(links)


def _extract_lots(root: ElementTree.Element) -> list[dict[str, Any]]:
    lots: list[dict[str, Any]] = []
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag not in {"lot", "procurementprojectlot", "tenderlot"}:
            continue
        lot_values = _flatten_xml(element)
        lot = {
            "id": _first_value(lot_values, "id", "lotid"),
            "title": _first_value(lot_values, "title", "name"),
            "description": _first_value(lot_values, "description", "descriptiontext"),
            "cpv_codes": _cpv_codes(element, lot_values),
            "contract_value": _numeric_value(
                _first_value(lot_values, "contractvalue", "estimatedvalue", "value")
            ),
        }
        if any(value for value in lot.values()):
            lots.append(lot)
    return lots


def _local_name(tag: str) -> str:
    return _normalize_key(tag.rsplit("}", maxsplit=1)[-1])


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value).replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None
