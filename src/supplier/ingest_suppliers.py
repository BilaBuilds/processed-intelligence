"""
src/supplier/ingest_suppliers.py
=================================
Stage 1 of the supplier intelligence layer: load raw supplier records
from disk and return them as plain dicts for the normalise stage.

Supported formats:
    CSV  — columns: supplier_id, name, region, capabilities, sectors,
                    accreditations, value_min, value_max, flags
    JSON — list of dicts with the same field names

Design rules:
    - Returns raw dicts only — no schema validation here
    - Never raises on a bad row; logs and counts instead
    - Reports a full IngestResult for manifest inclusion
    - Source file path and row number are attached to every record
      so normalize/match errors can be traced back to the source line
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("supplier.ingest")

SUPPORTED_EXTENSIONS = {".csv", ".json"}

REQUIRED_COLUMNS = {"supplier_id", "name"}


@dataclass
class IngestResult:
    source_file: str
    rows_read: int = 0
    rows_returned: int = 0
    rows_skipped: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.rows_returned > 0


def ingest_suppliers(
    source: Path | str,
    *,
    encoding: str = "utf-8-sig",  # utf-8-sig strips BOM from Excel-exported CSVs
) -> tuple[list[dict], IngestResult]:
    """
    Load raw supplier records from a CSV or JSON file.

    Args:
        source:   path to the supplier data file
        encoding: file encoding (default utf-8-sig to handle Excel BOM)

    Returns:
        (records, result) — list of raw dicts and an IngestResult summary

    Raises:
        FileNotFoundError: if the source file does not exist
        ValueError: if the file extension is not supported
    """
    path = Path(source)
    result = IngestResult(source_file=str(path))

    if not path.exists():
        raise FileNotFoundError(f"Supplier data file not found: {path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported supplier file format: {ext!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".csv":
        raw_records = _load_csv(path, encoding, result)
    else:
        raw_records = _load_json(path, encoding, result)

    log.info(
        "Supplier ingest: %s | read=%d returned=%d skipped=%d",
        path.name,
        result.rows_read,
        result.rows_returned,
        result.rows_skipped,
    )
    return raw_records, result


def _load_csv(path: Path, encoding: str, result: IngestResult) -> list[dict]:
    records: list[dict] = []
    try:
        with path.open(encoding=encoding, newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                result.warnings.append("CSV has no headers")
                return records

            missing_required = REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing_required:
                result.warnings.append(
                    f"CSV missing required columns: {sorted(missing_required)}"
                )

            for row_num, row in enumerate(reader, start=2):  # row 1 = header
                result.rows_read += 1
                cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                cleaned["source_file"] = str(path)
                cleaned["source_row"] = row_num

                skip_reason = _check_required(cleaned, row_num)
                if skip_reason:
                    result.rows_skipped += 1
                    result.skip_reasons.append(skip_reason)
                    continue

                records.append(cleaned)
                result.rows_returned += 1

    except UnicodeDecodeError as exc:
        result.warnings.append(f"Encoding error reading {path.name}: {exc}. Try encoding='latin-1'.")

    return records


def _load_json(path: Path, encoding: str, result: IngestResult) -> list[dict]:
    records: list[dict] = []
    try:
        raw = json.loads(path.read_text(encoding=encoding))
    except json.JSONDecodeError as exc:
        result.warnings.append(f"JSON parse error: {exc}")
        return records

    if not isinstance(raw, list):
        result.warnings.append("JSON supplier file must be a list of objects")
        return records

    for row_num, item in enumerate(raw, start=1):
        result.rows_read += 1
        if not isinstance(item, dict):
            result.rows_skipped += 1
            result.skip_reasons.append(f"row {row_num}: not a dict, got {type(item).__name__}")
            continue

        cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in item.items()}
        cleaned.setdefault("source_file", str(path))
        cleaned.setdefault("source_row", row_num)

        skip_reason = _check_required(cleaned, row_num)
        if skip_reason:
            result.rows_skipped += 1
            result.skip_reasons.append(skip_reason)
            continue

        records.append(cleaned)
        result.rows_returned += 1

    return records


def _check_required(row: dict, row_num: int) -> Optional[str]:
    """Return a skip reason string if required fields are missing, else None."""
    for col in REQUIRED_COLUMNS:
        if not row.get(col):
            return f"row {row_num}: missing required field '{col}'"
    return None
