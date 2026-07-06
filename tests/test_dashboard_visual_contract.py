from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "hostinger_upload" / "dashboard.html"
BUNDLE_DASHBOARD = ROOT / "data" / "export" / "hostinger_upload_bundle" / "dashboard.html"


def read_dashboard() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_dashboard_keeps_static_hostinger_data_contract() -> None:
    html = read_dashboard()

    assert '<script src="dashboard_data.js"></script>' in html
    assert "window.PROCESSED_DASHBOARD_DATA" in html
    assert "window.dashboardData" in html
    assert "window.DASHBOARD_DATA" in html


def test_dashboard_keeps_confirmed_intelligence_bindings() -> None:
    html = read_dashboard()

    for token in (
        "hot_outreach",
        "warm_buyers",
        "timing_ready",
        "avg_fit_score",
        "pipeline_model",
        "supplier_source",
        "notifier_channels",
    ):
        assert token in html


def test_dashboard_has_landing_page_visual_tokens() -> None:
    html = read_dashboard()

    assert "Hostinger landing-page restyle" in html
    assert "#172A3E" in html
    assert "#15263A" in html
    assert "#F4B247" in html
    assert "#F2A93B" in html
    assert "#EDF1F2" in html
    assert "#E5EAEC" in html
    assert "backdrop-filter: blur" in html
    assert "overflow-x: hidden" in html


def test_dashboard_remains_static_without_app_framework_dependency() -> None:
    html = read_dashboard().lower()

    assert "import react" not in html
    assert "react.development" not in html
    assert "next.config" not in html
    assert "from flask" not in html


def test_dashboard_clarifies_buyer_watchlist_not_sales_outreach() -> None:
    html = read_dashboard()

    assert "Buyer watchlist" in html
    assert "High-signal buyers" in html
    assert "public-sector buyer accounts" in html
    assert "client sales prospects" in html
    assert "Tracked public buyers" in html
    assert "Review timing-ready public opportunities" in html
    assert "delivery is currently via static Hostinger export" in html
    assert "Outreach queue" not in html
    assert "Discord-first" not in html


def test_dashboard_hides_avatar_builder_from_visible_navigation() -> None:
    html = read_dashboard()

    assert "label: 'Avatar builder'" not in html
    assert 'label: "Avatar builder"' not in html


def test_dashboard_uses_stronger_static_login_hashes() -> None:
    html = read_dashboard()

    assert "SHA-256 credentials" in html
    assert "async function sha256" in html
    assert "crypto.subtle.digest" in html
    assert "0ac07aee36b54773b9bc20c3a309943b10ba5aad0e4ccf380e27ec915913f69a" in html
    assert "a37bc73934a121f27264bc8513222184cd1bab8bb228016cce8f93fbf3bb0a83" in html
    assert "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918" not in html
    assert "04f8996da763b7a969b1028ee3007569eaf3a635486ddab211d512c85b9df8fb" not in html


def test_buyer_intelligence_table_uses_public_demo_language() -> None:
    html = read_dashboard()

    assert "Public-sector buyer watchlist built from the current TenderNed demo export" in html
    assert "No scored opportunity linked yet" in html
    assert "TenderNed public data" in html
    assert "No dossier path available" not in html
    assert "No quick actions available" not in html
    assert "Fit 0%" not in html
    assert "Action state" not in html
    assert "Admin" not in html


def test_hostinger_bundle_dashboard_matches_source_dashboard() -> None:
    assert BUNDLE_DASHBOARD.exists()
    assert BUNDLE_DASHBOARD.read_text(encoding="utf-8") == read_dashboard()
