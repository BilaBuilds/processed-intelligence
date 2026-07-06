from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hostinger_upload" / "index.html"
BUNDLE = ROOT / "data" / "export" / "hostinger_upload_bundle" / "index.html"


def read_source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_landing_pages_exist_and_match() -> None:
    assert SOURCE.exists()
    assert BUNDLE.exists()
    assert BUNDLE.read_text(encoding="utf-8") == read_source()


def test_metadata_and_navigation_contract() -> None:
    html = read_source()

    assert "<title>ProcessEd" in html
    assert 'rel="icon"' in html
    assert 'href="dashboard.html"' in html
    assert "Win contracts before the" in html


def test_live_demo_metrics_and_ctas_are_present() -> None:
    html = read_source()

    for token in (
        "50",
        "21",
        "45",
        "5",
        "19",
        "7",
        "16%",
        "Gemeente Helmond",
        "Gemeente Lelystad",
        "Stichting BOOR",
    ):
        assert token in html

    assert "mailto:info@processedcivils.com?subject=ProcessEd%20Pilot%20Access%20Request" in html
    assert "mailto:info@processedcivils.com?subject=ProcessEd%202-Week%20Pilot%20Review" in html


def test_static_only_no_framework_or_server_dependency() -> None:
    html = read_source().lower()

    for forbidden in (
        "react.development",
        "react.production",
        "import react",
        "next.js",
        "next/script",
        "vue.global",
        "astro-island",
        "from flask",
        "django",
        "cdn.",
        "unpkg.com",
        "jsdelivr",
    ):
        assert forbidden not in html


def test_claim_safety_and_vps_note() -> None:
    html = read_source().lower()

    for forbidden in (
        "guaranteed win",
        "guaranteed tender",
        "guarantee tender wins",
        "paying clients",
        "automated bid submission",
        "legal advice",
        "procurement advice",
    ):
        assert forbidden not in html

    assert "vps verification pending" in html
    assert "production vps pipeline verification pending" in html
