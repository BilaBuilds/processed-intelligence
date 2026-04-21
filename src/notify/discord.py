"""
src/notify/discord.py
=====================
Discord webhook notifier.

Config (environment variables):
    TENDER_WEBHOOK_URL   - Discord webhook URL (required)
    TENDER_NOTIFY_N      - Max opportunities per notification (default 5)

Features:
    - One summary message per run followed by one message per tender
    - Decision-led embeds for BID/REVIEW opportunities
    - Compact plain-text fallback per tender if embed rendering fails
    - Rate-limit aware with conservative retry handling
    - Never fails the core pipeline
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from src.notify.base import BaseNotifier

log = logging.getLogger("notify.discord")

MAX_RETRIES = 3
RETRY_BACKOFF = 2
POST_DELAY = 1.2
MAX_EMBEDS_TO_SEND = 10
COLOR_BID = 0x2E8B57
COLOR_REVIEW = 0xD9A441
VALID_WEBHOOK_HOSTS = {"discord.com", "ptb.discord.com", "canary.discord.com"}
WEBHOOK_PATH_RE = re.compile(r"^/api/webhooks/\d+/[A-Za-z0-9._-]+/?$")
PLACEHOLDER_MARKERS = {
    "YOUR_ROTATED_URL",
    "REAL_ROTATED_WEBHOOK",
    "YOUR_WEBHOOK_ID",
    "YOUR_WEBHOOK_TOKEN",
    "YOUR_NEW_WEBHOOK_ID",
    "YOUR_NEW_TOKEN",
    "PASTE",
    "EXAMPLE",
}


class DiscordNotifier(BaseNotifier):
    @property
    def name(self) -> str:
        return "discord"

    def _get_webhook_url(self) -> str:
        for key in (
            "TENDER_WEBHOOK_URL",
            "TENDER_DISCORD_WEBHOOK_URL",
            "DISCORD_WEBHOOK_URL",
        ):
            value = os.getenv(key, "").strip()
            if value:
                return value
        return ""

    def _validate_webhook_url(self, webhook_url: str) -> None:
        if not webhook_url:
            raise ValueError("TENDER_WEBHOOK_URL is missing.")
        if "<" in webhook_url or ">" in webhook_url:
            raise ValueError("TENDER_WEBHOOK_URL contains placeholder angle brackets.")

        uppercase = webhook_url.upper()
        if any(marker in uppercase for marker in PLACEHOLDER_MARKERS):
            raise ValueError("TENDER_WEBHOOK_URL still contains placeholder text.")

        parsed = urlparse(webhook_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("TENDER_WEBHOOK_URL is not a valid HTTPS URL.")
        if parsed.netloc.lower() not in VALID_WEBHOOK_HOSTS:
            raise ValueError("TENDER_WEBHOOK_URL must use a Discord webhook host.")
        if not WEBHOOK_PATH_RE.match(parsed.path):
            raise ValueError("TENDER_WEBHOOK_URL must match /api/webhooks/<id>/<token>.")

    def is_configured(self) -> bool:
        try:
            self._validate_webhook_url(self._get_webhook_url())
            return True
        except ValueError:
            return False

    def _top_n(self) -> int:
        raw = os.getenv("TENDER_NOTIFY_N") or os.getenv("TENDER_TOP_N") or "5"
        try:
            parsed = int(raw)
        except ValueError:
            log.warning("Discord: invalid TENDER_NOTIFY_N value %r - defaulting to 5.", raw)
            parsed = 5
        return min(parsed, MAX_EMBEDS_TO_SEND)

    def _filter_opportunities(self, opportunities: list[dict]) -> list[dict]:
        filtered = []
        for opp in opportunities:
            verdict = str(opp.get("decision_verdict") or "").upper()
            if verdict in {"BID", "REVIEW"}:
                filtered.append(opp)
        return filtered[: self._top_n()]

    def _safe_text(self, raw: object, default: str = "Unknown") -> str:
        if raw is None:
            return default
        text = str(raw).strip()
        return text if text else default

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def _humanize_code(self, code: object) -> str:
        return self._safe_text(code, default="unknown").replace("_", " ")

    def _safe_value(self, raw: object, currency: object = "GBP") -> str:
        if raw is None or raw == "":
            return "Unknown"
        try:
            amount = float(raw)
            label = f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"
            return f"{self._safe_text(currency, 'GBP')} {label}"
        except (ValueError, TypeError):
            return "Unknown"

    def _safe_deadline(self, opportunity: dict) -> str:
        raw = opportunity.get("deadline_at") or opportunity.get("deadline")
        if not raw:
            return "Unknown"
        return self._safe_text(str(raw)[:10], default="Unknown")

    def _decision_color(self, verdict: str) -> int:
        if verdict == "BID":
            return COLOR_BID
        return COLOR_REVIEW

    def _why_lines(self, opportunity: dict) -> list[str]:
        reasons = [self._humanize_code(item) for item in (opportunity.get("decision_reasons") or []) if item]
        if reasons:
            return reasons[:3]

        context = opportunity.get("context", {}) or {}
        recommendation_reason = context.get("recommendation_reason")
        if recommendation_reason:
            return [self._humanize_code(recommendation_reason)]
        narrative = self._safe_text(context.get("narrative"), default="")
        if narrative:
            return [self._truncate(narrative, 160)]
        return ["Decision-ready match from current shortlist"]

    def _risk_lines(self, opportunity: dict) -> list[str]:
        risks = [self._humanize_code(item) for item in (opportunity.get("risk_flags") or []) if item]
        if risks:
            return risks[:3]
        return ["No material delivery risks flagged"]

    def build_run_summary(
        self,
        opportunities: list[dict],
        run_id: str,
        *,
        evaluated_count: int | None = None,
    ) -> dict:
        verdict_counts = {"BID": 0, "REVIEW": 0}
        for opp in opportunities:
            verdict = str(opp.get("decision_verdict") or "").upper()
            if verdict in verdict_counts:
                verdict_counts[verdict] += 1

        actionable_count = len(opportunities)
        evaluated_total = actionable_count if evaluated_count is None else evaluated_count
        not_posted = max(evaluated_total - actionable_count, 0)
        content = (
            f"Tender pipeline | Run {run_id}\n"
            f"Evaluated: {evaluated_total} | Actionable: {actionable_count}\n"
            f"BID: {verdict_counts['BID']} | REVIEW: {verdict_counts['REVIEW']} | Not posted: {not_posted}\n"
            "Top matches posted below."
        )
        return {"content": content}

    def build_tender_embed(self, opportunity: dict, run_id: str) -> dict:
        verdict = str(opportunity.get("decision_verdict") or "REVIEW").upper()
        title = self._truncate(self._safe_text(opportunity.get("title"), "Untitled tender"), 256)
        url = opportunity.get("url") or opportunity.get("source_url")
        buyer = self._safe_text(opportunity.get("buyer_name") or opportunity.get("buyer"))
        region = self._safe_text(opportunity.get("region"))
        deadline = self._safe_deadline(opportunity)
        value = self._safe_value(
            opportunity.get("value_amount") if opportunity.get("value_amount") is not None else opportunity.get("value"),
            opportunity.get("value_currency") or opportunity.get("currency"),
        )
        score = self._safe_text(opportunity.get("score"))
        confidence = self._safe_text(opportunity.get("decision_confidence"))
        why_text = self._truncate("; ".join(self._why_lines(opportunity)), 400)
        risk_text = self._truncate("; ".join(self._risk_lines(opportunity)), 300)
        buyer_intel = opportunity.get("buyer_intel_brief", "")

        footer_text = self._truncate(
            f"ProcessEd | {run_id} | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            2048,
        )

        description = f"Why: {why_text}\nRisks: {risk_text}"
        if buyer_intel:
            description += f"\n\n📊 **Buyer Intel:**\n{self._truncate(buyer_intel, 800)}"

        embed = {
            "title": title,
            "color": self._decision_color(verdict),
            "description": self._truncate(description, 4096),
            "fields": [
                {"name": "Decision", "value": verdict, "inline": True},
                {"name": "Confidence", "value": confidence, "inline": True},
                {"name": "Score", "value": score, "inline": True},
                {"name": "Buyer", "value": self._truncate(buyer, 1024), "inline": True},
                {"name": "Region", "value": region, "inline": True},
                {"name": "Deadline", "value": deadline, "inline": True},
                {"name": "Value", "value": value, "inline": True},
            ],
            "footer": {"text": footer_text},
        }
        if url:
            embed["url"] = url
        return {"embeds": [embed]}

    def build_tender_fallback_text(self, opportunity: dict, run_id: str) -> dict:
        verdict = str(opportunity.get("decision_verdict") or "REVIEW").upper()
        text = "\n".join(
            [
                f"{verdict} | {self._safe_text(opportunity.get('title'), 'Untitled tender')}",
                f"Buyer: {self._safe_text(opportunity.get('buyer_name') or opportunity.get('buyer'))}",
                f"Region: {self._safe_text(opportunity.get('region'))} | Deadline: {self._safe_deadline(opportunity)}",
                f"Value: {self._safe_value(opportunity.get('value_amount') if opportunity.get('value_amount') is not None else opportunity.get('value'), opportunity.get('value_currency') or opportunity.get('currency'))}",
                f"Score: {self._safe_text(opportunity.get('score'))} | Confidence: {self._safe_text(opportunity.get('decision_confidence'))}",
                f"Why: {self._truncate('; '.join(self._why_lines(opportunity)), 220)}",
                f"Risks: {self._truncate('; '.join(self._risk_lines(opportunity)), 180)}",
                self._safe_text(opportunity.get("url") or opportunity.get("source_url"), default=""),
            ]
        ).strip()
        return {"content": self._truncate(text, 1800)}

    def _post_payload(self, payload: dict, webhook_url: str) -> tuple[bool, str]:
        """
        POST payload to webhook.
        Returns (success: bool, error_detail: str).
        error_detail is empty string on success.
        """
        last_error = ""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(webhook_url, json=payload, timeout=10)
                if response.status_code == 429:
                    retry_after = POST_DELAY
                    try:
                        retry_after = float(response.json().get("retry_after", POST_DELAY))
                    except Exception:
                        header_value = response.headers.get("Retry-After")
                        if header_value:
                            retry_after = float(header_value)
                    log.warning(
                        "Discord rate-limited - retrying in %.1fs (attempt %d/%d)",
                        retry_after,
                        attempt,
                        MAX_RETRIES,
                    )
                    last_error = f"rate_limited (429)"
                    time.sleep(retry_after)
                    continue

                if 200 <= response.status_code < 300:
                    return True, ""

                body_preview = self._truncate((response.text or "").strip().replace("\n", " "), 240)
                last_error = f"HTTP {response.status_code}: {body_preview or '(empty)'}"
                if response.status_code in {400, 401, 403, 404, 405}:
                    log.error(
                        "Discord webhook rejected (HTTP %d) — check webhook URL is valid and not deleted. Response: %s",
                        response.status_code,
                        body_preview or "(empty)",
                    )
                    return False, last_error

                wait = RETRY_BACKOFF ** attempt
                log.error(
                    "Discord POST failed (HTTP %d) on attempt %d/%d. Response: %s - retrying in %.1fs",
                    response.status_code,
                    attempt,
                    MAX_RETRIES,
                    body_preview or "(empty)",
                    wait,
                )
                time.sleep(wait)
            except requests.ConnectionError as exc:
                wait = RETRY_BACKOFF ** attempt
                last_error = f"ConnectionError: {exc}"
                log.error(
                    "Discord POST connection error on attempt %d/%d: %s — check network/webhook URL. Retrying in %.1fs",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
            except requests.RequestException as exc:
                wait = RETRY_BACKOFF ** attempt
                last_error = f"{type(exc).__name__}: {exc}"
                log.error(
                    "Discord POST exception on attempt %d/%d: %s - retrying in %.1fs",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)

        log.error("Discord: all %d attempts failed. Last error: %s", MAX_RETRIES, last_error)
        return False, last_error

    def send(self, opportunities: list[dict], run_id: str) -> bool:
        filtered = self._filter_opportunities(opportunities)
        if not filtered:
            log.info("Discord: no BID/REVIEW opportunities to send.")
            return True

        webhook_url = self._get_webhook_url()
        try:
            self._validate_webhook_url(webhook_url)
        except ValueError as exc:
            log.error("Discord: webhook misconfigured - %s. Skipping notify.", exc)
            return False

        log.info(
            "Discord: sending %d of %d opportunities for run %s.",
            len(filtered),
            len(opportunities),
            run_id,
        )

        summary_payload = self.build_run_summary(filtered, run_id, evaluated_count=len(opportunities))
        ok, err = self._post_payload(summary_payload, webhook_url)
        if not ok:
            log.error("Discord: failed to post run summary. Detail: %s", err)
            return False
        time.sleep(POST_DELAY)

        failures = 0
        for index, opportunity in enumerate(filtered, start=1):
            try:
                payload = self.build_tender_embed(opportunity, run_id)
            except Exception as exc:
                log.warning("Discord: embed build failed for tender %d (%s). Using fallback text.", index, exc)
                payload = self.build_tender_fallback_text(opportunity, run_id)

            ok, err = self._post_payload(payload, webhook_url)
            if not ok:
                failures += 1
                log.error(
                    "Discord: failed to post tender %d/%d. Detail: %s",
                    index,
                    len(filtered),
                    err,
                )
            if index < len(filtered):
                time.sleep(POST_DELAY)

        if failures:
            log.error("Discord: sent with %d failed tender message(s).", failures)
            return False

        log.info("Discord: sent summary + %d tender alert(s).", len(filtered))
        return True
