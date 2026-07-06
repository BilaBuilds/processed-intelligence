from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.dach.normalize_dach_tender import normalize_dach_tender


class DACHAdapterBase:
    """Base structure for future DACH adapters.

    This class intentionally does not implement network access.
    """

    source_name: str
    country: str

    def __init__(self, source_name: str, country: str) -> None:
        self.source_name = source_name
        self.country = country

    def fetch_raw(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Live source fetching is not implemented yet.")

    def normalize(self, raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            normalize_dach_tender(raw, self.source_name, self.country)
            for raw in raw_items
        ]

    def export(self, raw_items: list[dict[str, Any]], output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = self.normalize(raw_items)
        output_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return output_path
