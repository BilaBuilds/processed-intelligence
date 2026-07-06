from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCORED_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_scored.json"
SUMMARY_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_score_summary.json"
BUNDLE_DIR = ROOT / "data" / "export" / "dach_demo_bundle"
INDEX_PATH = BUNDLE_DIR / "index.html"
JSON_PATH = BUNDLE_DIR / "dach_dashboard_data.json"
JS_PATH = BUNDLE_DIR / "dach_dashboard_data.js"

SOURCE = "dach_demo_fixture"
DISCLAIMER = (
    "DACH demo sample generated from fixture data. Not a live feed. "
    "No live scraping performed. Not bid advice."
)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as data_file:
        return json.load(data_file)


def build_payload() -> dict[str, Any]:
    summary = load_json(SUMMARY_PATH)
    tenders = load_json(SCORED_PATH)

    return {
        "generated_at": summary["generated_at"],
        "summary": summary,
        "tenders": tenders,
        "disclaimer": DISCLAIMER,
        "source": SOURCE,
        "scoring_version": summary["scoring_version"],
    }


def build_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ProcessEd DACH Intelligence Demo</title>
  <script src="dach_dashboard_data.js"></script>
  <style>
    :root {
      --navy-950: #071426;
      --navy-900: #0b1f38;
      --navy-800: #123154;
      --navy-700: #183f68;
      --gold: #d6a84f;
      --gold-soft: #f0d59b;
      --ink: #f7fbff;
      --muted: #aebdd0;
      --line: rgba(255, 255, 255, 0.13);
      --panel: rgba(255, 255, 255, 0.075);
      --panel-strong: rgba(255, 255, 255, 0.12);
      --shadow: 0 22px 70px rgba(0, 0, 0, 0.34);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at 18% 8%, rgba(214, 168, 79, 0.2), transparent 28%),
        linear-gradient(135deg, var(--navy-950) 0%, var(--navy-900) 48%, #0a1829 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }

    button,
    select {
      font: inherit;
    }

    .shell {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 44px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 18px 0 26px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 800;
      color: #fff;
    }

    .brand-mark {
      display: grid;
      width: 38px;
      height: 38px;
      place-items: center;
      border: 1px solid rgba(214, 168, 79, 0.62);
      background: linear-gradient(145deg, rgba(214, 168, 79, 0.26), rgba(255, 255, 255, 0.06));
      color: var(--gold-soft);
      font-size: 14px;
      font-weight: 900;
      box-shadow: 0 12px 34px rgba(0, 0, 0, 0.24);
    }

    .status {
      color: var(--gold-soft);
      font-size: 13px;
      font-weight: 700;
      text-align: right;
    }

    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.18fr) minmax(300px, 0.82fr);
      gap: 26px;
      align-items: stretch;
      padding: 34px;
      border: 1px solid var(--line);
      background:
        linear-gradient(140deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.035)),
        linear-gradient(90deg, rgba(11, 31, 56, 0.96), rgba(18, 49, 84, 0.82));
      box-shadow: var(--shadow);
    }

    h1 {
      margin: 0 0 14px;
      max-width: 780px;
      font-size: clamp(34px, 5vw, 62px);
      line-height: 0.98;
      letter-spacing: 0;
    }

    .hero-copy {
      max-width: 700px;
      margin: 0;
      color: #d8e2ef;
      font-size: clamp(17px, 2vw, 21px);
      line-height: 1.55;
    }

    .disclaimer {
      margin-top: 24px;
      padding: 14px 16px;
      border-left: 3px solid var(--gold);
      background: rgba(214, 168, 79, 0.12);
      color: #ffe8b5;
      font-weight: 750;
      line-height: 1.45;
    }

    .hero-panel {
      display: grid;
      align-content: space-between;
      gap: 18px;
      min-height: 270px;
      padding: 24px;
      border: 1px solid rgba(214, 168, 79, 0.28);
      background: rgba(7, 20, 38, 0.46);
    }

    .hero-panel strong {
      display: block;
      color: var(--gold-soft);
      font-size: 42px;
      line-height: 1;
    }

    .hero-panel span {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }

    .kpis {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin: 20px 0;
    }

    .kpi {
      min-height: 104px;
      padding: 18px;
      border: 1px solid var(--line);
      background: var(--panel);
    }

    .kpi-value {
      display: block;
      margin-bottom: 8px;
      color: #fff;
      font-size: 30px;
      font-weight: 850;
      line-height: 1;
    }

    .kpi-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      line-height: 1.35;
      text-transform: uppercase;
    }

    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: end;
      justify-content: space-between;
      gap: 14px;
      margin: 28px 0 18px;
      padding: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.055);
    }

    .control-group {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }

    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    select {
      min-width: 170px;
      min-height: 42px;
      padding: 0 38px 0 12px;
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 0;
      color: #fff;
      background: var(--navy-800);
    }

    .result-count {
      color: #dce6f2;
      font-size: 14px;
      font-weight: 750;
    }

    .cards {
      display: grid;
      gap: 14px;
    }

    .tender-card {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 160px;
      gap: 18px;
      padding: 20px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.088), rgba(255, 255, 255, 0.045));
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.16);
    }

    .card-head {
      display: flex;
      flex-wrap: wrap;
      gap: 9px;
      margin-bottom: 10px;
    }

    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #dce8f8;
      background: rgba(255, 255, 255, 0.06);
      font-size: 12px;
      font-weight: 850;
    }

    .tag.priority-HIGH {
      color: #071426;
      border-color: var(--gold);
      background: var(--gold);
    }

    .tag.priority-MEDIUM {
      color: #fff2c8;
      border-color: rgba(214, 168, 79, 0.55);
      background: rgba(214, 168, 79, 0.18);
    }

    .tag.priority-LOW,
    .tag.priority-MONITOR {
      color: #c9d6e6;
    }

    .tender-title {
      margin: 0 0 8px;
      color: #fff;
      font-size: clamp(19px, 2.3vw, 26px);
      line-height: 1.18;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 12px 18px;
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }

    .reasons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 14px 0 0;
      padding: 0;
      list-style: none;
    }

    .reasons li {
      padding: 7px 10px;
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #dbe6f4;
      background: rgba(7, 20, 38, 0.36);
      font-size: 13px;
      line-height: 1.25;
    }

    .score-box {
      display: grid;
      align-content: center;
      justify-items: center;
      gap: 8px;
      min-height: 150px;
      border: 1px solid rgba(214, 168, 79, 0.32);
      background: rgba(214, 168, 79, 0.1);
      text-align: center;
    }

    .score {
      color: var(--gold-soft);
      font-size: 48px;
      font-weight: 900;
      line-height: 1;
    }

    .action {
      max-width: 130px;
      color: #dce6f2;
      font-size: 13px;
      font-weight: 800;
      line-height: 1.3;
    }

    .empty {
      display: none;
      padding: 32px;
      border: 1px solid var(--line);
      color: var(--muted);
      background: var(--panel);
      text-align: center;
    }

    .footer-note {
      margin: 28px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      text-align: center;
    }

    @media (max-width: 920px) {
      .hero {
        grid-template-columns: 1fr;
      }

      .kpis {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .tender-card {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 620px) {
      .shell {
        width: min(100% - 20px, 1180px);
        padding-top: 10px;
      }

      .topbar,
      .controls {
        align-items: stretch;
        flex-direction: column;
      }

      .status {
        text-align: left;
      }

      .hero {
        padding: 22px;
      }

      .kpis {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      select {
        width: 100%;
      }

      .control-group,
      label {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">PE</span><span>ProcessEd Intelligence</span></div>
      <div class="status">Standalone DACH fixture demo</div>
    </header>

    <section class="hero" aria-labelledby="page-title">
      <div>
        <h1 id="page-title">ProcessEd DACH Intelligence Demo</h1>
        <p class="hero-copy">Fixture-only DACH procurement intelligence sample for construction and civils teams.</p>
        <p class="disclaimer" id="disclaimer"></p>
      </div>
      <aside class="hero-panel" aria-label="Demo data status">
        <div>
          <strong id="heroTotal">0</strong>
          <span>scored fixture records across Germany, Austria, and Switzerland</span>
        </div>
        <div>
          <strong id="heroScore">0</strong>
          <span>average fit score from transparent heuristic scoring</span>
        </div>
      </aside>
    </section>

    <section class="kpis" aria-label="Dashboard KPIs">
      <div class="kpi"><span class="kpi-value" id="kpiTotal">0</span><span class="kpi-label">Total tenders</span></div>
      <div class="kpi"><span class="kpi-value" id="kpiHigh">0</span><span class="kpi-label">HIGH opportunities</span></div>
      <div class="kpi"><span class="kpi-value" id="kpiMedium">0</span><span class="kpi-label">MEDIUM opportunities</span></div>
      <div class="kpi"><span class="kpi-value" id="kpiCountries">0</span><span class="kpi-label">Countries covered</span></div>
      <div class="kpi"><span class="kpi-value" id="kpiAverage">0</span><span class="kpi-label">Average fit score</span></div>
      <div class="kpi"><span class="kpi-value" id="kpiTiming">0</span><span class="kpi-label">Timing-ready count</span></div>
    </section>

    <section class="controls" aria-label="Dashboard filters">
      <div class="control-group">
        <label for="countryFilter">Country
          <select id="countryFilter">
            <option>All</option>
            <option>Germany</option>
            <option>Austria</option>
            <option>Switzerland</option>
          </select>
        </label>
        <label for="priorityFilter">Priority
          <select id="priorityFilter">
            <option>All</option>
            <option>HIGH</option>
            <option>MEDIUM</option>
            <option>LOW</option>
            <option>MONITOR</option>
          </select>
        </label>
      </div>
      <div class="result-count" id="resultCount">0 records shown</div>
    </section>

    <section class="cards" id="cards" aria-label="DACH opportunity cards"></section>
    <p class="empty" id="emptyState">No fixture records match the selected filters.</p>
    <p class="footer-note">Source label: dach_demo_fixture. Scoring version: <span id="scoringVersion"></span>.</p>
  </main>

  <script>
    const payload = window.PROCESSED_DACH_DASHBOARD_DATA;
    const tenders = payload.tenders || [];
    const summary = payload.summary || {};
    const countryFilter = document.getElementById("countryFilter");
    const priorityFilter = document.getElementById("priorityFilter");
    const cards = document.getElementById("cards");
    const emptyState = document.getElementById("emptyState");
    const resultCount = document.getElementById("resultCount");

    function text(value, fallback = "Not published") {
      return value === null || value === undefined || value === "" ? fallback : String(value);
    }

    function formatDate(value) {
      if (!value) return "Not published";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
    }

    function formatValue(tender) {
      if (tender.value === null || tender.value === undefined || tender.value === "") return "Value not published";
      const amount = Number(tender.value);
      if (Number.isNaN(amount)) return `${tender.value} ${text(tender.currency, "")}`.trim();
      return `${amount.toLocaleString("en-GB")} ${text(tender.currency, "")}`.trim();
    }

    function setText(id, value) {
      document.getElementById(id).textContent = value;
    }

    function renderKpis() {
      const countByPriority = summary.count_by_priority || {};
      setText("disclaimer", payload.disclaimer);
      setText("heroTotal", summary.total_tenders || tenders.length);
      setText("heroScore", summary.average_fit_score || 0);
      setText("kpiTotal", summary.total_tenders || tenders.length);
      setText("kpiHigh", countByPriority.HIGH || 0);
      setText("kpiMedium", countByPriority.MEDIUM || 0);
      setText("kpiCountries", Object.keys(summary.count_by_country || {}).length);
      setText("kpiAverage", summary.average_fit_score || 0);
      setText("kpiTiming", summary.timing_ready_count || 0);
      setText("scoringVersion", payload.scoring_version || "unknown");
    }

    function cardFor(tender) {
      const reasons = (tender.reasons || []).map((reason) => `<li>${reason}</li>`).join("");
      return `
        <article class="tender-card">
          <div>
            <div class="card-head">
              <span class="tag priority-${tender.priority}">${tender.priority}</span>
              <span class="tag">${tender.country}</span>
              <span class="tag">${payload.source}</span>
            </div>
            <h2 class="tender-title">${tender.title}</h2>
            <p class="meta">
              <span>${text(tender.buyer)}</span>
              <span>${text(tender.region)}</span>
              <span>Deadline: ${formatDate(tender.deadline)}</span>
              <span>Value: ${formatValue(tender)}</span>
            </p>
            <ul class="reasons">${reasons}</ul>
          </div>
          <div class="score-box">
            <div class="score">${tender.fit_score}</div>
            <div class="action">${tender.next_action}</div>
          </div>
        </article>
      `;
    }

    function renderCards() {
      const country = countryFilter.value;
      const priority = priorityFilter.value;
      const filtered = tenders.filter((tender) => {
        const countryMatch = country === "All" || tender.country === country;
        const priorityMatch = priority === "All" || tender.priority === priority;
        return countryMatch && priorityMatch;
      });

      cards.innerHTML = filtered.map(cardFor).join("");
      emptyState.style.display = filtered.length ? "none" : "block";
      resultCount.textContent = `${filtered.length} ${filtered.length === 1 ? "record" : "records"} shown`;
    }

    countryFilter.addEventListener("change", renderCards);
    priorityFilter.addEventListener("change", renderCards);
    renderKpis();
    renderCards();
  </script>
</body>
</html>
"""


def export_bundle() -> dict[str, str]:
    payload = build_payload()
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    JSON_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    JS_PATH.write_text(
        "window.PROCESSED_DACH_DASHBOARD_DATA = "
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    INDEX_PATH.write_text(build_index_html(), encoding="utf-8")

    return {
        "index": str(INDEX_PATH),
        "json": str(JSON_PATH),
        "js": str(JS_PATH),
    }


def main() -> None:
    result = export_bundle()
    print(f"Exported DACH static dashboard bundle to {BUNDLE_DIR}")
    print(f"HTML: {result['index']}")
    print(f"JSON: {result['json']}")
    print(f"JS: {result['js']}")


if __name__ == "__main__":
    main()
