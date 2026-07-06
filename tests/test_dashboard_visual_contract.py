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


def test_dashboard_login_hashes_remain_present() -> None:
    html = read_dashboard()

    assert "SHA-256 credentials" in html
    assert "async function sha256" in html
    assert "crypto.subtle.digest" in html


def test_hostinger_bundle_dashboard_matches_source_dashboard() -> None:
    assert BUNDLE_DASHBOARD.exists()
    assert BUNDLE_DASHBOARD.read_text(encoding="utf-8") == read_dashboard()
