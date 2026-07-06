from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class HermesMemoryStore:
    def __init__(self, root: Path = Path("data/hermes/memory")) -> None:
        self.root = root
        self.events_path = self.root / "events.jsonl"
        self.company_memory_path = self.root / "company_memory.json"
        self.contact_memory_path = self.root / "contact_memory.json"

    def record_run(
        self,
        run_id: str,
        enriched_csv: Path,
        summary: dict[str, Any],
    ) -> None:
        rows = self._read_rows(enriched_csv)
        self._append_event(
            {
                "type": "hermes_run",
                "run_id": run_id,
                "summary": summary,
            }
        )
        self._update_company_memory(rows, run_id)
        self._update_contact_memory(rows, run_id)

    def record_draft_sync(
        self,
        run_dir: Path,
        created: int,
        skipped: int,
    ) -> None:
        self._append_event(
            {
                "type": "draft_sync",
                "run_dir": run_dir.as_posix(),
                "created": created,
                "skipped": skipped,
            }
        )

    def _read_rows(self, enriched_csv: Path) -> list[dict[str, str]]:
        if not enriched_csv.exists():
            return []
        with enriched_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
            return [dict(row) for row in csv.DictReader(csv_file)]

    def _append_event(self, event: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            **event,
        }
        with self.events_path.open("a", encoding="utf-8") as events_file:
            events_file.write(json.dumps(event, sort_keys=True))
            events_file.write("\n")

    def _update_company_memory(
        self,
        rows: list[dict[str, str]],
        run_id: str,
    ) -> None:
        memory = self._load_json_object(self.company_memory_path)
        for row in rows:
            company = row.get("company") or row.get("company_name")
            if not company:
                continue
            key = company.casefold()
            existing = memory.get(key, {})
            runs = existing.get("runs", [])
            if run_id not in runs:
                runs.append(run_id)
            memory[key] = {
                "company": company,
                "domain": row.get("domain"),
                "best_contact": row.get("name") or existing.get("best_contact"),
                "best_email": row.get("email") or existing.get("best_email"),
                "best_phone": row.get("phone") or existing.get("best_phone"),
                "best_quality_score": max(
                    self._safe_float(existing.get("best_quality_score")),
                    self._safe_float(row.get("quality_score")),
                ),
                "last_source": row.get("source") or existing.get("last_source"),
                "last_recommended_action": row.get("recommended_action")
                or existing.get("last_recommended_action"),
                "runs": runs[-20:],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        self._write_json(self.company_memory_path, memory)

    def _update_contact_memory(
        self,
        rows: list[dict[str, str]],
        run_id: str,
    ) -> None:
        memory = self._load_json_object(self.contact_memory_path)
        for row in rows:
            email = row.get("email")
            if not email:
                continue
            key = email.casefold()
            runs = memory.get(key, {}).get("runs", [])
            if run_id not in runs:
                runs.append(run_id)
            memory[key] = {
                "email": email,
                "name": row.get("name"),
                "company": row.get("company") or row.get("company_name"),
                "phone": row.get("phone"),
                "last_quality_score": self._safe_float(row.get("quality_score")),
                "last_recommended_action": row.get("recommended_action"),
                "runs": runs[-20:],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        self._write_json(self.contact_memory_path, memory)

    def _load_json_object(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
