from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_HTML = BASE_DIR / "hostinger_upload" / "dashboard.html"
REQUIRED_REFERENCES = [
    "hot_outreach",
    "warm_buyers",
    "timing_ready",
    "avg_fit_score",
    "pipeline_model",
    "supplier_source",
    "notifier_channels",
    "window.PROCESSED_DASHBOARD_DATA",
    "window.dashboardData",
    "window.DASHBOARD_DATA",
    "[ProcessEd dashboard mapping]",
]


def main() -> int:
    if not DASHBOARD_HTML.exists():
        print(f"missing dashboard file: {DASHBOARD_HTML}")
        return 1

    text = DASHBOARD_HTML.read_text(encoding="utf-8", errors="ignore")
    missing = [needle for needle in REQUIRED_REFERENCES if needle not in text]
    if missing:
        print("missing dashboard binding references:")
        for needle in missing:
            print(f"- {needle}")
        return 1

    print(f"dashboard frontend bindings verified: {DASHBOARD_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
