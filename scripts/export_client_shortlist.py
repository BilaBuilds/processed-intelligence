"""
scripts/export_client_shortlist.py
====================================
Generate a polished, client-facing export from an existing client run artifact.

CLI usage:
    python scripts/export_client_shortlist.py --run-id 2026-04-19_025154 --client bilal_main
    python scripts/export_client_shortlist.py --run-id 2026-04-19_025154 --client bilal_main --format html
    python scripts/export_client_shortlist.py --run-id 2026-04-19_025154 --client bilal_main --format md

Reads from:
    data/runs/<run_id>/clients/<client_id>/client_summary.json
    data/runs/<run_id>/clients/<client_id>/client_shortlist.json

Writes to:
    data/runs/<run_id>/clients/<client_id>/export/shortlist_export.html
    data/runs/<run_id>/clients/<client_id>/export/shortlist_export.md

All data comes from existing artifacts — no re-run, no external calls, deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR  = Path(__file__).resolve().parent.parent
RUNS_DIR  = BASE_DIR / "data" / "runs"


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

def _load_branding() -> dict:
    path = BASE_DIR / "config" / "export_branding.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "brand_name":    "ProcessEd",
        "tagline":       "Tender intelligence for targeted public-sector opportunities",
        "contact_email": "",
    }


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_client_artifacts(run_dir: Path, client_id: str) -> tuple[dict, list[dict]]:
    client_dir = run_dir / "clients" / client_id
    summary_path  = client_dir / "client_summary.json"
    shortlist_path = client_dir / "client_shortlist.json"

    if not summary_path.exists():
        raise FileNotFoundError(
            f"client_summary.json not found: {summary_path}\n"
            f"Run the pipeline first, or check the client_id / run_id."
        )
    if not shortlist_path.exists():
        raise FileNotFoundError(
            f"client_shortlist.json not found: {shortlist_path}"
        )

    summary   = _load_json(summary_path)
    shortlist = _load_json(shortlist_path)
    if isinstance(shortlist, dict):
        shortlist = shortlist.get("tenders", [])
    if not isinstance(shortlist, list):
        shortlist = []
    return summary, shortlist


# ---------------------------------------------------------------------------
# Deterministic relevance line
# ---------------------------------------------------------------------------

def _relevance_line(tender: dict, subscribed_products: list[str]) -> str:
    """
    One-sentence relevance note derived purely from existing fields.
    No AI. No invented claims.
    """
    region   = (tender.get("region") or "").strip()
    buyer    = (tender.get("buyer_name") or tender.get("buyer") or "").strip()
    score    = tender.get("score") or 0
    category = (tender.get("procurement_category") or "").strip()
    products = [p.replace("_", " ") for p in subscribed_products] if subscribed_products else []
    product_str = products[0] if products else ""

    parts: list[str] = []
    if product_str:
        parts.append(f"Aligned with {product_str} scope")
    if region:
        parts.append(f"{region} coverage")
    if score:
        parts.append(f"score {score}")
    if not parts:
        parts.append("Meets current filter criteria")

    return ". ".join(parts) + "."


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------

def _fmt_value(tender: dict) -> str:
    v = tender.get("value_amount")
    if v is None:
        return "Value not disclosed"
    try:
        n = float(v)
        if n >= 1_000_000:
            return f"£{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"£{n/1_000:.0f}k"
        return f"£{n:.0f}"
    except (TypeError, ValueError):
        return "Value not disclosed"


def _fmt_deadline(tender: dict) -> str:
    raw = tender.get("deadline_at") or tender.get("deadline") or ""
    if not raw:
        return "Not specified"
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y")
    except Exception:
        return str(raw)[:10]


def _fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%-d %B %Y")
    except Exception:
        return iso[:10] if iso else ""


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{brand_name} – Shortlist for {display_name}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
          background: #f7f8fa; color: #1a2535; font-size: 14px; line-height: 1.6; }}
  .page {{ max-width: 860px; margin: 0 auto; padding: 40px 24px 60px; }}

  /* Header */
  .header {{ background: #1a3c5e; color: #fff; border-radius: 8px; padding: 32px 32px 28px; margin-bottom: 28px; }}
  .header-brand {{ font-size: 12px; letter-spacing: 0.1em; text-transform: uppercase;
                   color: #c9a84c; font-weight: 700; margin-bottom: 8px; }}
  .header-title {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  .header-subtitle {{ font-size: 13px; color: #a8bdd0; margin-bottom: 18px; }}
  .header-meta {{ font-size: 12px; color: #7fa8c8; }}

  /* Summary cards */
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                   gap: 14px; margin-bottom: 28px; }}
  .summary-card {{ background: #fff; border: 1px solid #dde2ea; border-radius: 8px;
                   padding: 16px 18px; }}
  .summary-card-value {{ font-size: 24px; font-weight: 700; color: #1a3c5e; }}
  .summary-card-label {{ font-size: 11px; color: #6b7a8d; text-transform: uppercase;
                         letter-spacing: 0.05em; margin-top: 2px; }}
  .summary-detail {{ background: #fff; border: 1px solid #dde2ea; border-radius: 8px;
                     padding: 16px 20px; margin-bottom: 28px; }}
  .summary-detail-row {{ display: flex; gap: 12px; flex-wrap: wrap; font-size: 13px;
                          margin-top: 6px; }}
  .detail-chip {{ background: #eef2f8; color: #1a3c5e; border-radius: 20px;
                  padding: 3px 10px; font-size: 12px; font-weight: 600; }}

  /* Section headers */
  .section-title {{ font-size: 13px; font-weight: 700; text-transform: uppercase;
                    letter-spacing: 0.06em; color: #6b7a8d; margin: 0 0 12px; }}

  /* Opportunity cards */
  .opp-card {{ background: #fff; border: 1px solid #dde2ea; border-radius: 8px;
               padding: 20px 22px; margin-bottom: 16px; }}
  .opp-card-title {{ font-size: 15px; font-weight: 700; color: #1a3c5e; margin-bottom: 4px; }}
  .opp-card-buyer {{ font-size: 13px; color: #4a6280; margin-bottom: 10px; }}
  .opp-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
  .opp-meta-item {{ font-size: 12px; background: #f0f4fb; border-radius: 4px;
                    padding: 3px 9px; color: #1a3c5e; }}
  .opp-meta-item.score {{ background: #1a3c5e; color: #fff; font-weight: 700; }}
  .opp-relevance {{ font-size: 12px; color: #5a7a5a; font-style: italic; margin-bottom: 8px; }}
  .opp-url {{ font-size: 12px; color: #3a72b0; word-break: break-all; }}
  .opp-url a {{ color: #3a72b0; }}

  /* Empty state */
  .empty-box {{ background: #fff; border: 1px solid #dde2ea; border-radius: 8px;
                padding: 36px 28px; text-align: center; margin-bottom: 28px; }}
  .empty-box-title {{ font-size: 16px; font-weight: 700; color: #1a3c5e; margin-bottom: 8px; }}
  .empty-box-text {{ font-size: 13px; color: #6b7a8d; max-width: 480px; margin: 0 auto; }}

  /* Actions */
  .actions-box {{ background: #f0f4fb; border: 1px solid #c9d6e8; border-radius: 8px;
                  padding: 20px 22px; margin-bottom: 28px; }}
  .actions-list {{ list-style: none; padding: 0; }}
  .actions-list li {{ font-size: 13px; padding: 5px 0; color: #2a3f5a; }}
  .actions-list li::before {{ content: "→ "; color: #c9a84c; font-weight: 700; }}

  /* Footer */
  .footer {{ text-align: center; font-size: 11px; color: #9aa5b4; padding-top: 24px;
             border-top: 1px solid #dde2ea; }}
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div class="header">
    <div class="header-brand">{brand_name}</div>
    <div class="header-title">{display_name} — Opportunity Shortlist</div>
    <div class="header-subtitle">{tagline}</div>
    <div class="header-meta">Generated {generated_date} &nbsp;·&nbsp; Run {run_id}</div>
  </div>

  <!-- Summary KPIs -->
  <div class="summary-grid">
    <div class="summary-card">
      <div class="summary-card-value">{item_count}</div>
      <div class="summary-card-label">Opportunities matched</div>
    </div>
    {score_range_card}
    {regions_card}
    {products_card}
  </div>

  {detail_block}

  <!-- Opportunities -->
  <p class="section-title">Matched opportunities</p>
  {opportunities_html}

  <!-- Recommended next actions -->
  <p class="section-title" style="margin-top:28px;">Recommended next actions</p>
  <div class="actions-box">
    <ul class="actions-list">
      <li>Review each opportunity for fit and bid / no-bid position</li>
      <li>Check submission deadline and portal requirements</li>
      <li>Review buyer history and prior procurement patterns</li>
      <li>Flag any opportunities for early qualification or site visit</li>
      <li>Reply to request a broader shortlist or filter adjustment</li>
    </ul>
  </div>

  <div class="footer">
    {brand_name} &nbsp;·&nbsp; {tagline}<br>
    {contact_line}
    This report is generated from live public procurement data and is provided for intelligence purposes only.
  </div>

</div>
</body>
</html>
"""

_OPP_CARD_TEMPLATE = """\
<div class="opp-card">
  <div class="opp-card-title">{title}</div>
  <div class="opp-card-buyer">{buyer}</div>
  <div class="opp-meta">
    <span class="opp-meta-item score">Score {score}</span>
    <span class="opp-meta-item">{region}</span>
    <span class="opp-meta-item">{value}</span>
    <span class="opp-meta-item">Deadline: {deadline}</span>
    {source_chip}
  </div>
  <div class="opp-relevance">{relevance}</div>
  {url_block}
</div>"""

_EMPTY_OPP_HTML = """\
<div class="empty-box">
  <div class="empty-box-title">No opportunities matched in this run</div>
  <div class="empty-box-text">
    No live tenders met your current filters in this pipeline run.
    Monitoring continues automatically. Filters or subscribed products can be
    broadened if needed — reply to discuss.
  </div>
</div>"""


def _build_html(summary: dict, shortlist: list[dict], branding: dict) -> str:
    display_name    = summary.get("display_name", "Client")
    run_id          = summary.get("run_id", "")
    item_count      = summary.get("item_count", 0)
    generated_at    = summary.get("generated_at", "")
    generated_date  = _fmt_date(generated_at)
    subscribed      = summary.get("subscribed_products", [])
    top_regions     = summary.get("top_regions", [])
    top_buyers      = summary.get("top_buyers", [])
    score_range     = summary.get("score_range")

    brand_name   = branding.get("brand_name", "ProcessEd")
    tagline      = branding.get("tagline", "")
    contact_email = branding.get("contact_email", "")
    contact_line = f'<a href="mailto:{contact_email}">{contact_email}</a> &nbsp;·&nbsp; ' if contact_email else ""

    # KPI cards
    score_range_card = ""
    if score_range:
        score_range_card = (
            f'<div class="summary-card">'
            f'<div class="summary-card-value">{score_range["min"]}–{score_range["max"]}</div>'
            f'<div class="summary-card-label">Score range</div></div>'
        )

    regions_card = ""
    if top_regions:
        regions_card = (
            f'<div class="summary-card">'
            f'<div class="summary-card-value">{len(top_regions)}</div>'
            f'<div class="summary-card-label">Regions</div></div>'
        )

    products_card = ""
    if subscribed:
        products_card = (
            f'<div class="summary-card">'
            f'<div class="summary-card-value">{len(subscribed)}</div>'
            f'<div class="summary-card-label">Products subscribed</div></div>'
        )

    # Detail block — buyers + regions chips
    detail_rows: list[str] = []
    if subscribed:
        chips = "".join(f'<span class="detail-chip">{p.replace("_"," ").title()}</span>' for p in subscribed)
        detail_rows.append(f'<div style="margin-bottom:8px;"><strong style="font-size:12px;color:#6b7a8d;text-transform:uppercase;letter-spacing:.05em;">Products</strong><div class="summary-detail-row">{chips}</div></div>')
    if top_regions:
        chips = "".join(f'<span class="detail-chip">{r}</span>' for r in top_regions)
        detail_rows.append(f'<div style="margin-bottom:8px;"><strong style="font-size:12px;color:#6b7a8d;text-transform:uppercase;letter-spacing:.05em;">Regions</strong><div class="summary-detail-row">{chips}</div></div>')
    if top_buyers:
        chips = "".join(f'<span class="detail-chip">{b}</span>' for b in top_buyers[:3])
        detail_rows.append(f'<div><strong style="font-size:12px;color:#6b7a8d;text-transform:uppercase;letter-spacing:.05em;">Top buyers</strong><div class="summary-detail-row">{chips}</div></div>')

    detail_block = ""
    if detail_rows:
        detail_block = f'<div class="summary-detail">{"".join(detail_rows)}</div>'

    # Opportunity cards
    if shortlist:
        opp_cards: list[str] = []
        for t in shortlist:
            title    = t.get("title") or "Untitled opportunity"
            buyer    = t.get("buyer_name") or t.get("buyer") or "Unknown buyer"
            region   = t.get("region") or "Region not specified"
            score    = t.get("score") or 0
            value    = _fmt_value(t)
            deadline = _fmt_deadline(t)
            source   = t.get("source") or ""
            url      = t.get("url") or t.get("source_url") or ""
            relevance = _relevance_line(t, subscribed)

            source_chip = f'<span class="opp-meta-item">{source}</span>' if source else ""
            url_block   = f'<div class="opp-url"><a href="{url}" target="_blank">{url[:80]}{"…" if len(url)>80 else ""}</a></div>' if url else ""

            opp_cards.append(_OPP_CARD_TEMPLATE.format(
                title=_esc(title), buyer=_esc(buyer), region=_esc(region),
                score=score, value=_esc(value), deadline=_esc(deadline),
                source_chip=source_chip, url_block=url_block,
                relevance=_esc(relevance),
            ))
        opportunities_html = "\n".join(opp_cards)
    else:
        opportunities_html = _EMPTY_OPP_HTML

    return _HTML_TEMPLATE.format(
        brand_name=brand_name, display_name=_esc(display_name),
        tagline=tagline, run_id=run_id, generated_date=generated_date,
        item_count=item_count,
        score_range_card=score_range_card, regions_card=regions_card, products_card=products_card,
        detail_block=detail_block,
        opportunities_html=opportunities_html,
        contact_line=contact_line,
    )


def _esc(text: str) -> str:
    """Minimal HTML escaping for safe interpolation."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def _build_markdown(summary: dict, shortlist: list[dict], branding: dict) -> str:
    display_name  = summary.get("display_name", "Client")
    run_id        = summary.get("run_id", "")
    item_count    = summary.get("item_count", 0)
    generated_at  = summary.get("generated_at", "")
    generated_date = _fmt_date(generated_at)
    subscribed    = summary.get("subscribed_products", [])
    top_regions   = summary.get("top_regions", [])
    top_buyers    = summary.get("top_buyers", [])
    score_range   = summary.get("score_range")
    brand_name    = branding.get("brand_name", "ProcessEd")
    tagline       = branding.get("tagline", "")
    contact_email = branding.get("contact_email", "")

    lines: list[str] = []

    # Header
    lines += [
        f"# {brand_name} — {display_name}: Opportunity Shortlist",
        "",
        f"*{tagline}*",
        "",
        f"**Generated:** {generated_date}  ",
        f"**Run ID:** `{run_id}`",
        "",
        "---",
        "",
    ]

    # Summary
    lines += ["## Summary", ""]
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Opportunities matched | **{item_count}** |")
    if score_range:
        lines.append(f"| Score range | {score_range['min']} – {score_range['max']} |")
    if subscribed:
        lines.append(f"| Products subscribed | {', '.join(p.replace('_',' ').title() for p in subscribed)} |")
    if top_regions:
        lines.append(f"| Top regions | {', '.join(top_regions)} |")
    if top_buyers:
        lines.append(f"| Top buyers | {', '.join(top_buyers[:3])} |")
    lines.append("")

    # Opportunities
    lines += ["---", "", "## Matched Opportunities", ""]

    if not shortlist:
        lines += [
            "> **No opportunities matched in this run.**",
            ">",
            "> No live tenders met your current filters. Monitoring continues automatically.",
            "> Filters or subscribed products can be broadened if needed — reply to discuss.",
            "",
        ]
    else:
        for i, t in enumerate(shortlist, 1):
            title    = t.get("title") or "Untitled opportunity"
            buyer    = t.get("buyer_name") or t.get("buyer") or "Unknown buyer"
            region   = t.get("region") or "Region not specified"
            score    = t.get("score") or 0
            value    = _fmt_value(t)
            deadline = _fmt_deadline(t)
            url      = t.get("url") or t.get("source_url") or ""
            relevance = _relevance_line(t, subscribed)

            lines.append(f"### {i}. {title}")
            lines.append("")
            lines.append(f"**Buyer:** {buyer}  ")
            lines.append(f"**Region:** {region}  ")
            lines.append(f"**Value:** {value}  ")
            lines.append(f"**Deadline:** {deadline}  ")
            lines.append(f"**Score:** {score}")
            lines.append("")
            lines.append(f"*{relevance}*")
            if url:
                lines.append(f"")
                lines.append(f"[View notice]({url})")
            lines.append("")

    # Actions
    lines += [
        "---",
        "",
        "## Recommended Next Actions",
        "",
        "- Review each opportunity for fit and bid / no-bid position",
        "- Check submission deadline and portal requirements",
        "- Review buyer history and prior procurement patterns",
        "- Flag any opportunities for early qualification or site visit",
        "- Reply to request a broader shortlist or filter adjustment",
        "",
        "---",
        "",
    ]

    if contact_email:
        lines.append(f"*{brand_name} — {tagline}*  ")
        lines.append(f"*Contact: {contact_email}*")
    else:
        lines.append(f"*{brand_name} — {tagline}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def export(run_id: str, client_id: str, fmt: str = "html") -> Path:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    summary, shortlist = load_client_artifacts(run_dir, client_id)
    branding = _load_branding()

    export_dir = run_dir / "clients" / client_id / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        content = _build_html(summary, shortlist, branding)
        out_path = export_dir / "shortlist_export.html"
    elif fmt == "md":
        content = _build_markdown(summary, shortlist, branding)
        out_path = export_dir / "shortlist_export.md"
    else:
        raise ValueError(f"Unsupported format: {fmt!r} — use 'html' or 'md'")

    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a client-facing shortlist export.")
    parser.add_argument("--run-id",  required=True, help="Run ID, e.g. 2026-04-19_025154")
    parser.add_argument("--client",  required=True, help="Client ID, e.g. bilal_main")
    parser.add_argument("--format",  default="html", choices=["html", "md"], help="Export format")
    args = parser.parse_args()

    try:
        out_path = export(args.run_id, args.client, args.format)
        print(f"Export written: {out_path}")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
