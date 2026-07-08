import json
from pathlib import Path

from scripts.dashboard_intelligence import (
    ASSIGNMENT_PREFIX,
    build_dashboard_payload,
    load_dashboard_js,
    value_label,
    write_dashboard_js,
)


def _payload(tenders):
    return {
        "generated_at": "2025-06-04T12:00:00Z",
        "latestRun": {
            "generated_at": "2025-06-04T12:00:00Z",
            "manifest": {},
            "tenders": tenders,
        },
    }


def test_nl_construction_terms_are_icp_matched_and_score_above_65():
    data = build_dashboard_payload(
        _payload(
            [
                {
                    "id": "nl-1",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Renovatie brug en riolering openbare ruimte",
                    "buyer": "Gemeente Voorbeeldstad",
                    "deadline": "2025-07-15T10:00:00",
                    "publication_date": "2025-06-01",
                }
            ]
        )
    )

    tender = data["latestRun"]["tenders"][0]
    assert tender["icp_match"] is True
    assert tender["score"] >= 65
    assert tender["shortlist"] is True


def test_shortlisted_cannot_exceed_icp_matched():
    data = build_dashboard_payload(
        _payload(
            [
                {
                    "id": "nl-1",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Nieuwbouw civiel werk",
                    "buyer": "Rijkswaterstaat",
                    "deadline": "2025-07-01",
                },
                {
                    "id": "nl-2",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Kantoorartikelen",
                    "buyer": "Gemeente Voorbeeldstad",
                    "deadline": "2025-07-01",
                },
            ]
        )
    )

    metrics = data["latestRun"]["metrics"]
    assert metrics["icp_matched"] >= metrics["shortlisted"]


def test_expired_april_may_deadlines_do_not_count_as_active_or_shortlisted():
    data = build_dashboard_payload(
        _payload(
            [
                {
                    "id": "expired-april",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Civiel onderhoud wegen",
                    "buyer": "Provincie Test",
                    "deadline": "2025-04-30",
                },
                {
                    "id": "expired-may",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Renovatie kade",
                    "buyer": "Havenbedrijf Test",
                    "deadline": "2025-05-31",
                },
            ]
        )
    )

    assert {row["status"] for row in data["latestRun"]["tenders"]} == {"expired"}
    assert data["latestRun"]["metrics"]["active_opportunities"] == 0
    assert data["latestRun"]["metrics"]["shortlisted"] == 0


def test_buyers_export_contains_buyer_level_records():
    data = build_dashboard_payload(
        _payload(
            [
                {
                    "id": "a",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Civiel onderhoud watergangen",
                    "buyer": "Gemeente A",
                    "deadline": "2025-07-01",
                    "publication_date": "2025-06-02",
                },
                {
                    "id": "b",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Ingenieursdiensten openbare ruimte",
                    "buyer": "Gemeente A",
                    "deadline": "2025-08-01",
                    "publication_date": "2025-06-03",
                },
            ]
        )
    )

    buyers = data["latestRun"]["buyers"]
    assert len(buyers) == 1
    assert buyers[0]["buyer"] == "Gemeente A"
    assert buyers[0]["opportunity_count"] == 2
    assert buyers[0]["active_opportunities"] == 2
    assert "recommended_action" in buyers[0]


def test_value_unknown_displays_cleanly_when_missing():
    assert value_label(None) == "Value unknown"
    assert value_label("") == "Value unknown"


def test_existing_dashboard_json_loads(tmp_path: Path):
    path = tmp_path / "dashboard_data.js"
    original = _payload(
        [
            {
                "id": "nl-1",
                "source": "tenderned",
                "country": "NL",
                "title": "Rijkswaterstaat infrastructuur onderhoud",
                "buyer": "Rijkswaterstaat",
                "deadline": "2025-07-01",
            }
        ]
    )
    path.write_text(f"{ASSIGNMENT_PREFIX}{json.dumps(original)};\n", encoding="utf-8")

    loaded = load_dashboard_js(path)
    normalized = build_dashboard_payload(loaded)
    write_dashboard_js(path, normalized)

    reloaded = load_dashboard_js(path)
    assert reloaded["latestRun"]["metrics"]["tenders_ingested"] == 1
    assert reloaded["latestRun"]["tenders"][0]["value_label"] == "Value unknown"
