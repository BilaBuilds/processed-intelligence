"""
src/context.py
==============
Step 3b - Context & Narrative Layer

Reads scored tenders and augments with:
    - Trade classification (civils, drainage, groundworks, public realm, mixed)
    - Strategic fit scoring (delivery_fit, buyer_history, scope_match, win_probability)
    - Human-readable narrative explaining why tender matters
    - Clear recommendation (BID, REVIEW, SKIP)

Feeds into decision.py and notify.py for better alerts and product positioning.

Config files required:
    - config/civils_niche.yaml       (trade definitions + exclusions)
    - state/job_history.json         (your past wins)
    - state/buyer_profiles.json      (buyer procurement patterns)
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("context")


def load_yaml_config(path: Path) -> dict:
    """Simple YAML parser for our specific config (no external deps)."""
    if not path.exists():
        log.warning(f"Config not found: {path}")
        return {}

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Fallback: simple dict parsing if yaml not available
        log.warning("PyYAML not available, using fallback parser")
        return {}


def load_json_state(path: Path, default: Any = None) -> Any:
    """Load JSON state file safely."""
    if not path.exists():
        return default or []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load {path}: {e}")
        return default or []


class ContextBuilder:
    """Builds narrative + strategic fit context for tenders."""

    def __init__(self, config_dir: Path, state_dir: Path):
        self.config_dir = config_dir
        self.state_dir = state_dir

        # Load config and state
        # Prefer niche.yaml from the active sector pack; fall back to legacy civils_niche.yaml
        niche_path = self._resolve_niche_path(config_dir)
        self.niche_config = load_yaml_config(niche_path)
        self.job_history = load_json_state(state_dir / "job_history.json", [])
        self.buyer_profiles = load_json_state(state_dir / "buyer_profiles.json", {})

        # Build lookup tables
        self._init_lookups()

    @staticmethod
    def _resolve_niche_path(config_dir: Path) -> Path:
        """Return the niche YAML path for the active sector pack, or legacy fallback."""
        try:
            from src.sector_pack import get_pack
            pack = get_pack()
            if pack.niche_yaml_path.exists():
                return pack.niche_yaml_path
        except Exception:
            pass
        # Legacy fallback
        return config_dir / "civils_niche.yaml"

    def _init_lookups(self):
        """Build keyword sets and buyer lookup from config."""
        self.include_trades = set()
        self.exclude_keywords = set()
        self.buyer_lookup = {}

        # Trade keywords to include
        trades = self.niche_config.get("trades", {})
        for trade_name, trade_def in trades.items():
            keywords = trade_def.get("keywords", [])
            self.include_trades.update(keywords)

        # Exclusions to skip entirely
        exclusions = self.niche_config.get("exclusions", {})
        self.exclude_keywords.update(exclusions.get("keywords", []))

        # Buyer patterns
        for buyer_name, profile in self.buyer_profiles.items():
            self.buyer_lookup[buyer_name.lower()] = profile

    def classify_trade(self, text: str) -> dict:
        """Classify tender into trade categories."""
        text_lower = text.lower()

        matched_trades = []
        trades_config = self.niche_config.get("trades", {})

        for trade_name, trade_def in trades_config.items():
            keywords = trade_def.get("keywords", [])
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                    matched_trades.append(trade_name)
                    break  # Only count each trade once

        # Determine primary and secondary
        if not matched_trades:
            matched_trades = ["mixed"]

        return {
            "primary": matched_trades[0] if matched_trades else "mixed",
            "all": matched_trades,
            "is_core_niche": len(matched_trades) > 0 and "mixed" not in matched_trades,
        }

    def score_delivery_fit(self, tender: dict) -> tuple[int, str]:
        """
        Score how well this tender matches your past delivery patterns.
        0-100, based on job history similarity (value, trade, geography).
        """
        if not self.job_history:
            return 0, "no_history"

        tender_value = tender.get("value_amount") or tender.get("value")
        tender_region = (tender.get("region") or "").lower()
        tender_text = ((tender.get("title") or "") + " " + (tender.get("description") or "")).lower()

        matches = 0
        max_matches = len(self.job_history)

        for past_job in self.job_history:
            score_this = 0

            # Trade match (worth 40 points)
            past_trade = str(past_job.get("type", "")).lower()
            if past_trade and past_trade in tender_text:
                score_this += 40

            # Value band match (worth 30 points)
            past_value = past_job.get("value")
            if past_value and tender_value:
                try:
                    pv = float(past_value)
                    tv = float(tender_value)
                    # Within +/- 50% of past value
                    if (pv * 0.5) <= tv <= (pv * 1.5):
                        score_this += 30
                except (ValueError, TypeError):
                    pass

            # Geography match (worth 20 points)
            past_region = str(past_job.get("region", "")).lower()
            if past_region and past_region in tender_region:
                score_this += 20

            # Client type match (worth 10 points)
            past_client = str(past_job.get("client", "")).lower()
            if past_client and past_client in tender_text:
                score_this += 10

            if score_this > 0:
                matches += 1

        # Normalize: if any past job matched significantly, boost
        if matches > 0:
            fit_score = int((matches / max_matches) * 100)
            fit_score = min(fit_score, 85)  # Cap at 85 (don't oversell)
            return fit_score, f"{matches}_similar_past_jobs"

        return 0, "no_matching_history"

    def score_buyer_history(self, tender: dict) -> tuple[int, str]:
        """
        Score how much you know about this buyer.
        0-100, based on buyer_profiles and job_history references.
        """
        buyer_name = tender.get("buyer_name") or tender.get("buyer")
        if not buyer_name:
            return 0, "buyer_unknown"

        buyer_lower = buyer_name.lower()

        # Check if in buyer profiles
        if buyer_lower in self.buyer_lookup:
            profile = self.buyer_lookup[buyer_lower]
            # Score: if you know the buyer, score higher
            return 70, f"known_buyer_{profile.get('frequency', 'regular')}"

        # Check if mentioned in job history
        has_history = any(
            buyer_lower in str(job.get("client", "")).lower()
            for job in self.job_history
        )
        if has_history:
            return 60, "previous_work_with_buyer"

        # Unknown buyer
        return 0, "buyer_not_in_history"

    def score_scope_match(self, tender: dict, trade_class: dict) -> tuple[int, str]:
        """
        Score how well the tender scope matches your typical delivery capability.
        0-100, based on trade, value, package type.
        """
        score = 0
        breakdown = []

        # Trade fit
        if trade_class["is_core_niche"]:
            score += 50
            breakdown.append("core_trade")
        else:
            score += 20
            breakdown.append("adjacent_trade")

        # Value fit (SME band)
        value_score = tender.get("score_breakdown", {}).get("value", 0)
        if value_score >= 20:
            score += 30
            breakdown.append("value_in_band")
        elif value_score >= 10:
            score += 15
            breakdown.append("value_acceptable")
        else:
            score += 0
            breakdown.append("value_marginal")

        # Package type (framework better than one-off)
        title = ((tender.get("title") or "") + " " + (tender.get("description") or "")).lower()
        if "framework" in title or "dps" in title:
            score += 20
            breakdown.append("recurring_opportunity")

        return min(score, 100), ",".join(breakdown)

    def estimate_win_probability(
        self,
        tender: dict,
        trade_class: dict,
        delivery_fit: int,
        buyer_history: int,
        scope_match: int
    ) -> tuple[int, str]:
        """
        Estimate win probability as a 0-100 score.
        Heuristic: blend of your capability signals + tender attractiveness.
        """
        # Tender score (market attractiveness for your niche)
        tender_score = tender.get("score", 0)

        # Your fit signals (capability + history)
        your_signals = (delivery_fit + buyer_history + scope_match) / 3

        # Win probability = blend
        base = (tender_score * 0.4) + (your_signals * 0.6)

        # Adjust for risk flags
        risks = tender.get("risk_flags") or []
        risk_penalty = len(risks) * 5

        win_prob = max(0, int(base - risk_penalty))
        win_prob = min(win_prob, 95)  # Never guarantee >95%

        return win_prob, f"tender_score_{tender_score}_your_fit_{int(your_signals)}"

    def build_narrative(
        self,
        tender: dict,
        trade_class: dict,
        delivery_fit: int,
        buyer_history: int,
        scope_match: int,
        win_prob: int,
    ) -> str:
        """Generate a human-readable narrative explaining the tender's value."""
        lines = []

        buyer = tender.get("buyer_name") or tender.get("buyer") or "Unknown buyer"
        value = tender.get("value_amount") or tender.get("value") or "N/A"
        if value != "N/A":
            try:
                value = f"£{int(float(value)):,}"
            except (ValueError, TypeError):
                pass

        # Lead
        trade_str = trade_class["primary"].replace("_", " ").title()
        lines.append(f"{trade_str} opportunity")
        lines.append(f"Buyer: {buyer} | Value: {value}")

        # Why it matters (signal-based)
        signals = []
        if delivery_fit > 50:
            signals.append(f"strong match to past work ({delivery_fit}% delivery fit)")
        elif delivery_fit > 0:
            signals.append(f"relevant to your experience ({delivery_fit}% fit)")

        if buyer_history > 50:
            signals.append("buyer you know")

        if scope_match > 50:
            signals.append(f"within your typical scope ({scope_match}% fit)")

        if scope_match > 60 or win_prob > 60:
            signals.append(f"good win probability ({win_prob}%)")

        if signals:
            lines.append("Why relevant: " + ", ".join(signals))

        # Risks
        risks = tender.get("risk_flags") or []
        if risks:
            risk_str = ", ".join(risks[:2])
            lines.append(f"⚠️ Risks: {risk_str}")

        return " | ".join(lines)

    def make_recommendation(
        self,
        tender: dict,
        score: int,
        delivery_fit: int,
        buyer_history: int,
        scope_match: int,
        win_prob: int,
    ) -> tuple[str, str]:
        """
        Recommend BID, REVIEW, or SKIP.
        Returns (recommendation, reason).
        """
        risks = tender.get("risk_flags") or []
        decision_verdict = tender.get("decision_verdict", "REVIEW")

        # Hard filters
        if "deadline_passed" in risks:
            return "SKIP", "deadline_passed"

        if decision_verdict == "NO_BID":
            return "SKIP", f"pipeline_no_bid"

        # Soft recommendation
        if (
            delivery_fit > 60
            and scope_match > 50
            and win_prob > 55
            and decision_verdict == "BID"
        ):
            return "BID", "strong_fit_and_capability"

        if (
            score > 40
            and (delivery_fit > 40 or buyer_history > 40)
            and decision_verdict in ("BID", "REVIEW")
        ):
            return "REVIEW", "moderate_fit_check_manually"

        # Default
        return "SKIP", f"low_overall_fit"

    def augment_tender(self, tender: dict) -> dict:
        """Add all context fields to tender record."""
        # Classify trade
        searchable = " ".join(filter(None, [
            tender.get("title") or "",
            tender.get("description") or "",
        ]))
        trade_class = self.classify_trade(searchable)

        # Score strategic fit
        delivery_fit, delivery_reason = self.score_delivery_fit(tender)
        buyer_history, buyer_reason = self.score_buyer_history(tender)
        scope_match, scope_reason = self.score_scope_match(tender, trade_class)
        win_prob, win_reason = self.estimate_win_probability(
            tender, trade_class, delivery_fit, buyer_history, scope_match
        )

        # Narrative + recommendation
        narrative = self.build_narrative(
            tender, trade_class, delivery_fit, buyer_history, scope_match, win_prob
        )
        recommendation, rec_reason = self.make_recommendation(
            tender, tender.get("score", 0),
            delivery_fit, buyer_history, scope_match, win_prob
        )

        # Augment record
        tender["context"] = {
            "trade_classification": trade_class,
            "strategic_fit": {
                "delivery_fit_score": delivery_fit,
                "delivery_fit_reason": delivery_reason,
                "buyer_history_score": buyer_history,
                "buyer_history_reason": buyer_reason,
                "scope_match_score": scope_match,
                "scope_match_reason": scope_reason,
                "win_probability": win_prob,
                "win_probability_reason": win_reason,
            },
            "narrative": narrative,
            "recommendation": recommendation,
            "recommendation_reason": rec_reason,
        }

        return tender


def run(context_dict: dict) -> dict:
    """
    Pipeline step: augment all scored tenders with context.

    Input:  context_dict["scored_file"] (from match.py)
    Output: context_dict with new "context_file" key
    """
    scored_file: Path = context_dict["scored_file"]
    run_dir: Path = context_dict["run_dir"]
    config_dir: Path = context_dict.get("config_dir", Path("config"))
    state_dir: Path = context_dict.get("state_dir", Path("state"))

    context_file = run_dir / "context_tenders.jsonl"

    # Initialize context builder
    builder = ContextBuilder(config_dir, state_dir)

    augmented = []
    with open(scored_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("Skipping malformed JSON line in %s: %s", scored_file.name, exc)
                continue
            augmented_rec = builder.augment_tender(rec)
            augmented.append(augmented_rec)

    # Write augmented tenders
    with open(context_file, "w", encoding="utf-8") as f:
        for rec in augmented:
            f.write(json.dumps(rec, default=str) + "\n")

    log.info(
        "Context complete: %d augmented, narratives + recommendations added -> %s",
        len(augmented), context_file.name,
    )

    return {
        "context_file": context_file,
        "context_count": len(augmented),
    }
