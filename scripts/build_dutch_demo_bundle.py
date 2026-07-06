from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities.json"
SEGMENTS_PATH = ROOT / "data" / "outreach" / "netherlands_target_segments.csv"
EXPORT_DIR = ROOT / "data" / "export" / "dutch_demo_bundle"
JSON_PATH = EXPORT_DIR / "dutch_dashboard_data.json"
JS_PATH = EXPORT_DIR / "dutch_dashboard_data.js"
HTML_PATH = EXPORT_DIR / "index.html"


def load_opportunities() -> list[dict]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as fixture_file:
        data = json.load(fixture_file)
    if not isinstance(data, list):
        raise ValueError("Dutch demo opportunities fixture must contain a list.")
    return data


def load_segments() -> list[dict]:
    if not SEGMENTS_PATH.exists():
        return []
    with SEGMENTS_PATH.open("r", encoding="utf-8", newline="") as segment_file:
        return list(csv.DictReader(segment_file))


def build_kpis(opportunities: list[dict]) -> dict:
    fit_scores = [float(item["fit_score"]) for item in opportunities]
    total_value_eur = sum(float(item["estimated_value_eur"]) for item in opportunities)
    high_urgency = sum(1 for item in opportunities if item["urgency"] == "high")
    cross_border = sum(1 for item in opportunities if str(item["id"]).startswith("EU-DEMO"))
    return {
        "total_opportunities": len(opportunities),
        "netherlands_specific": len(opportunities) - cross_border,
        "cross_border_relevant": cross_border,
        "average_fit_score": round(sum(fit_scores) / len(fit_scores), 1) if fit_scores else 0,
        "high_urgency": high_urgency,
        "total_estimated_value_eur": int(total_value_eur),
    }


def build_source_coverage(opportunities: list[dict]) -> list[dict]:
    source_counts = Counter(item["source"] for item in opportunities)
    coverage = []
    for source, count in sorted(source_counts.items()):
        coverage.append(
            {
                "source": source,
                "sample_records": count,
                "access_status": "Planning/demo only; confirm live access and terms before production.",
                "data_status": "sample_demo_not_verified_live_coverage",
            }
        )
    return coverage


def build_bundle() -> dict:
    opportunities = load_opportunities()
    opportunities = sorted(opportunities, key=lambda item: (-float(item["fit_score"]), item["deadline"]))
    return {
        "metadata": {
            "name": "ProcessEd Intelligence Netherlands Demo Bundle",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "data_status": "sample_demo_not_verified_live_coverage",
            "source_fixture": str(FIXTURE_PATH.relative_to(ROOT)).replace("\\", "/"),
            "note": "Sample/demo data only. Not verified live tender coverage.",
        },
        "kpis": build_kpis(opportunities),
        "source_coverage": build_source_coverage(opportunities),
        "outreach_segments": load_segments(),
        "opportunities": opportunities,
    }


def render_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ProcessEd Netherlands Demo Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #16202a;
      --muted: #637083;
      --line: #d9e1e8;
      --paper: #f6f8fa;
      --panel: #ffffff;
      --accent: #0b6e69;
      --accent-2: #b24a3b;
      --accent-3: #2f5f9f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--paper);
    }
    header {
      padding: 28px clamp(16px, 4vw, 48px) 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0 0 8px; font-size: clamp(28px, 4vw, 44px); letter-spacing: 0; }
    h2 { margin: 0 0 14px; font-size: 22px; letter-spacing: 0; }
    p { color: var(--muted); line-height: 1.45; }
    main { padding: 24px clamp(16px, 4vw, 48px) 48px; }
    .notice {
      max-width: 960px;
      margin: 0;
      color: #6f3f12;
      font-weight: 700;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 28px;
    }
    .kpi, .card, .source, .segment {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .kpi strong { display: block; font-size: 28px; color: var(--accent); }
    .kpi span, .meta { color: var(--muted); font-size: 13px; }
    .section { margin-top: 30px; }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }
    .card h3 { margin: 0 0 8px; font-size: 18px; }
    .pillrow { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      color: var(--muted);
      background: #fbfcfd;
    }
    .score {
      color: #fff;
      background: var(--accent);
      border-radius: 6px;
      padding: 5px 8px;
      font-weight: 700;
      display: inline-block;
      margin-bottom: 8px;
    }
    .urgent-high { border-left: 5px solid var(--accent-2); }
    .urgent-medium { border-left: 5px solid var(--accent-3); }
    .urgent-low { border-left: 5px solid var(--accent); }
    .sources, .segments {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }
    a { color: var(--accent-3); }
  </style>
</head>
<body>
  <header>
    <h1>Netherlands Demo Dashboard</h1>
    <p class="notice">Sample/demo data only. This dashboard is not verified live tender coverage.</p>
  </header>
  <main>
    <section class="grid" id="kpis"></section>
    <section class="section">
      <h2>Opportunity Cards</h2>
      <div class="cards" id="opportunities"></div>
    </section>
    <section class="section">
      <h2>Source Coverage</h2>
      <div class="sources" id="sources"></div>
    </section>
    <section class="section">
      <h2>Outreach Segments</h2>
      <div class="segments" id="segments"></div>
    </section>
  </main>
  <script src="dutch_dashboard_data.js"></script>
  <script>
    const data = window.DUTCH_DASHBOARD_DATA;
    const fmt = new Intl.NumberFormat("en-GB");
    const money = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
    const kpis = [
      ["Total opportunities", data.kpis.total_opportunities],
      ["Netherlands-specific", data.kpis.netherlands_specific],
      ["EU/cross-border", data.kpis.cross_border_relevant],
      ["Average fit score", data.kpis.average_fit_score],
      ["High urgency", data.kpis.high_urgency],
      ["Estimated value", money.format(data.kpis.total_estimated_value_eur)]
    ];
    document.getElementById("kpis").innerHTML = kpis.map(([label, value]) => `<div class="kpi"><strong>${value}</strong><span>${label}</span></div>`).join("");
    document.getElementById("opportunities").innerHTML = data.opportunities.map((item) => `
      <article class="card urgent-${item.urgency}">
        <span class="score">${item.fit_score} fit</span>
        <h3>${item.title}</h3>
        <div class="meta">${item.buyer} | ${item.region} | ${item.deadline}</div>
        <p>${item.summary_en}</p>
        <div class="pillrow">
          <span class="pill">${item.category}</span>
          <span class="pill">${item.source}</span>
          <span class="pill">${money.format(item.estimated_value_eur)}</span>
        </div>
        <p><strong>Action:</strong> ${item.recommended_action}</p>
        <p class="meta">${item.data_status}</p>
      </article>
    `).join("");
    document.getElementById("sources").innerHTML = data.source_coverage.map((item) => `
      <article class="source">
        <h3>${item.source}</h3>
        <p>${fmt.format(item.sample_records)} sample records</p>
        <p class="meta">${item.access_status}</p>
      </article>
    `).join("");
    document.getElementById("segments").innerHTML = data.outreach_segments.map((item) => `
      <article class="segment">
        <h3>${item.segment_name}</h3>
        <p>${item.positioning}</p>
        <div class="pillrow">
          <span class="pill">${item.priority}</span>
          <span class="pill">${item.cpv_focus}</span>
        </div>
      </article>
    `).join("");
  </script>
</body>
</html>
"""


def write_bundle(bundle: dict) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    JS_PATH.write_text(
        "window.DUTCH_DASHBOARD_DATA = "
        + json.dumps(bundle, indent=2, sort_keys=True)
        + ";\n",
        encoding="utf-8",
    )
    HTML_PATH.write_text(render_html(), encoding="utf-8")


def main() -> None:
    bundle = build_bundle()
    write_bundle(bundle)
    print(
        "Dutch demo bundle built: "
        f"{bundle['kpis']['total_opportunities']} opportunities, "
        f"{bundle['kpis']['netherlands_specific']} NL-specific, "
        f"{bundle['kpis']['cross_border_relevant']} EU/cross-border, "
        f"avg fit {bundle['kpis']['average_fit_score']}."
    )
    print(f"Dashboard: {HTML_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
