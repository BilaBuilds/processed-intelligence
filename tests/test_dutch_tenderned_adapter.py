from __future__ import annotations

import importlib.util
from pathlib import Path


ADAPTER_PATH = Path("C:/Dev/dutch_adapter.py")


def load_adapter():
    spec = importlib.util.spec_from_file_location("dutch_adapter", ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_item(**overrides):
    item = {
        "publicatieId": "431953",
        "aanbestedingNaam": "Werkplek-hardware",
        "opdrachtgeverNaam": "Gemeente Sudwest-Fryslan",
        "sluitingsDatum": "2026-09-11T14:00:00",
        "publicatieDatum": "2026-07-05",
        "opdrachtBeschrijving": "Levering van hardware.",
        "typeOpdracht": {"code": "L"},
        "procedure": {"code": "OPE"},
        "digitaal": True,
        "europees": True,
        "publicatiestatus": {"code": "PUB"},
        "url": "https://example.test/tender/431953",
    }
    item.update(overrides)
    return item


def test_parser_handles_content_array() -> None:
    adapter = load_adapter()

    tenders = adapter.PublicatiesParser.parse_response({"content": [sample_item()]})

    assert len(tenders) == 1
    assert tenders[0].source == "tenderned"
    assert tenders[0].country == "NL"
    assert tenders[0].source_id == "431953"
    assert tenders[0].type_code == "L"
    assert tenders[0].procedure_code == "OPE"


def test_parser_handles_missing_fields() -> None:
    adapter = load_adapter()

    tenders = adapter.PublicatiesParser.parse_response({"content": [{"publicatieId": "missing-fields"}]})

    assert len(tenders) == 1
    tender = tenders[0]
    assert tender.source_id == "missing-fields"
    assert tender.title == ""
    assert tender.buyer == ""
    assert tender.publication_date == ""
    assert tender.deadline is None
    assert tender.type_code == ""
    assert tender.procedure_code == ""


def test_parser_deduplicates_source_id() -> None:
    adapter = load_adapter()

    tenders = adapter.PublicatiesParser.parse_response(
        {
            "content": [
                sample_item(publicatieId="dup", aanbestedingNaam="First"),
                sample_item(publicatieId="dup", aanbestedingNaam="Second"),
                sample_item(publicatieId="unique", aanbestedingNaam="Third"),
            ]
        }
    )

    assert [t.source_id for t in tenders] == ["dup", "unique"]
    assert tenders[0].title == "First"


def test_export_has_dashboard_aliases(tmp_path: Path) -> None:
    adapter = load_adapter()
    tenders = adapter.PublicatiesParser.parse_response({"content": [sample_item()]})
    output = tmp_path / "dutch_tenders.json"

    adapter.export_to_json(tenders, str(output))

    payload = adapter.json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "tenderned"
    assert payload["country"] == "NL"
    assert len(payload["latestRun"]["tenders"]) == 1
    assert payload["latestRun"]["opportunities"] == payload["latestRun"]["tenders"]
    assert payload["opportunities"] == payload["tenders"]


def test_xml_enrichment_skips_cleanly_without_credentials(monkeypatch) -> None:
    adapter = load_adapter()
    tenders = adapter.PublicatiesParser.parse_response({"content": [sample_item()]})
    monkeypatch.delenv("TENDERNED_XML_USERNAME", raising=False)
    monkeypatch.delenv("TENDERNED_XML_PASSWORD", raising=False)
    monkeypatch.delenv("TENDERNED_USERNAME", raising=False)
    monkeypatch.delenv("TENDERNED_PASSWORD", raising=False)

    result = adapter.enrich_with_xml_if_credentials(tenders)

    assert result["status"] == "skipped"
    assert result["reason"] == "missing_credentials"
    assert result["tenders"] == tenders
