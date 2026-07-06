from __future__ import annotations

from datetime import datetime
from hashlib import sha1
from typing import Any


VALID_COUNTRIES = {"Germany", "Austria", "Switzerland"}
DEFAULT_LANGUAGES = {
    "Germany": "de",
    "Austria": "de",
    "Switzerland": "unknown",
}
DEFAULT_CURRENCIES = {
    "Germany": "EUR",
    "Austria": "EUR",
    "Switzerland": "CHF",
}


def _first_present(raw: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return default


def _parse_date(value: Any) -> str | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    return text


def _numeric_or_none(value: Any) -> int | float | None:
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return value

    text = str(value).strip().replace(" ", "")
    if not text:
        return None

    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None

    return int(number) if number.is_integer() else number


def _listify(value: Any) -> list[str]:
    if value in (None, ""):
        return []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    if not text:
        return []

    separators = [";", ","]
    values = [text]
    for separator in separators:
        if separator in text:
            values = text.split(separator)
            break

    return [item.strip() for item in values if item.strip()]


def _raw_source_ref(raw: dict[str, Any], source_name: str) -> str:
    notice_id = _first_present(raw, ["notice_id", "id", "reference", "raw_id"], "")
    source_url = _first_present(raw, ["source_url", "url", "link"], "")
    if notice_id:
        return f"{source_name}:{notice_id}"
    if source_url:
        digest = sha1(str(source_url).encode("utf-8")).hexdigest()[:12]
        return f"{source_name}:url:{digest}"
    digest = sha1(repr(sorted(raw.items())).encode("utf-8")).hexdigest()[:12]
    return f"{source_name}:raw:{digest}"


def _stable_id(raw: dict[str, Any], source_name: str, country: str) -> str:
    notice_id = _first_present(raw, ["notice_id", "id", "reference", "raw_id"], "")
    seed = "|".join(
        [
            country,
            source_name,
            str(notice_id),
            str(_first_present(raw, ["published_at", "publication_date"], "")),
            str(_first_present(raw, ["title", "name"], "")),
        ]
    )
    return f"dach-{sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def normalize_dach_tender(
    raw: dict[str, Any], source_name: str, country: str
) -> dict[str, Any]:
    if country not in VALID_COUNTRIES:
        raise ValueError(f"Unsupported DACH country: {country}")

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        raise TypeError("raw tender must be a dictionary")

    language = _first_present(raw, ["language", "lang"], DEFAULT_LANGUAGES[country])
    currency = _first_present(raw, ["currency"], DEFAULT_CURRENCIES[country])
    cpv_codes = _listify(_first_present(raw, ["cpv_codes", "cpv"], []))

    return {
        "id": _first_present(raw, ["normalized_id"], _stable_id(raw, source_name, country)),
        "title": _first_present(raw, ["title", "name"], ""),
        "buyer": _first_present(raw, ["buyer", "authority", "client"], ""),
        "country": country,
        "region": _first_present(raw, ["region", "state", "canton"], ""),
        "language": language,
        "source": _first_present(raw, ["source"], source_name),
        "source_url": _first_present(raw, ["source_url", "url", "link"], ""),
        "notice_id": _first_present(raw, ["notice_id", "id", "reference"], ""),
        "published_at": _parse_date(_first_present(raw, ["published_at", "publication_date"], None)),
        "deadline": _parse_date(_first_present(raw, ["deadline", "due_date", "closing_date"], None)),
        "value": _numeric_or_none(_first_present(raw, ["value", "estimated_value", "budget"], None)),
        "currency": currency,
        "cpv_codes": cpv_codes,
        "description": _first_present(raw, ["description", "summary"], ""),
        "procurement_stage": _first_present(raw, ["procurement_stage", "stage"], "unknown"),
        "fit_score": _numeric_or_none(raw.get("fit_score")),
        "priority": _first_present(raw, ["priority"], "UNSCORED"),
        "reasons": _listify(raw.get("reasons")),
        "raw_source_ref": _raw_source_ref(raw, source_name),
    }
