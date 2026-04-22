"""Insider trading sentiment scorer for OpenQuant.

Scores insider trades using a rule-based system derived from
academic research on insider trading signals:

  - CEO purchase: +40 points (highest conviction signal)
  - CFO purchase: +20 points
  - Cluster buy (3+ insiders in same week): +30 points
  - Large purchase (>3x average trade size): +15 points
  - Director sale (routine, <25% of holdings): -5 points
  - CEO sale: -30 points (highest conviction negative signal)
  - CFO sale: -15 points
  - Cluster sell (3+ insiders in same week): -25 points

The final score is clamped to [-100, +100] and mapped to a label.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import List, Optional, Tuple

from openquant.data.protocol import InsiderTrade
from openquant.insider.models import InsiderScore

logger = logging.getLogger(__name__)

# ── Scoring weights ──────────────────────────────────────────────────

SCORES = {
    "ceo_purchase": 40,
    "cfo_purchase": 20,
    "cluster_buy": 30,
    "large_purchase": 15,
    "director_routine_sale": -5,
    "ceo_sale": -30,
    "cfo_sale": -15,
    "cluster_sell": -25,
    "officer_purchase": 15,
    "officer_sale": -10,
    "director_purchase": 10,
}


def _normalize_title(title: str) -> str:
    """Normalize insider title for pattern matching."""
    t = title.upper().strip()
    return t


def _is_ceo(title: str) -> bool:
    t = _normalize_title(title)
    return "CEO" in t or "CHIEF EXECUTIVE" in t


def _is_cfo(title: str) -> bool:
    t = _normalize_title(title)
    return "CFO" in t or "CHIEF FINANCIAL" in t or "FINANCE OFFICER" in t


def _is_officer(title: str) -> bool:
    t = _normalize_title(title)
    return (
        _is_ceo(title)
        or _is_cfo(title)
        or "COO" in t
        or "CHIEF OPERATING" in t
        or "CTO" in t
        or "CHIEF TECHNOLOGY" in t
        or "PRESIDENT" in t
        or "VP" in t
        or "OFFICER" in t
    )


def _is_director(title: str) -> bool:
    t = _normalize_title(title)
    return "DIRECTOR" in t or "BOARD" in t


def _get_week_key(trade_date: date) -> Tuple[int, int]:
    """Get ISO (year, week) for clustering."""
    iso = trade_date.isocalendar()
    return (iso[0], iso[1])


class InsiderScorer:
    """Scores a list of insider trades to produce an InsiderScore.

    Detects patterns: cluster buys/sells, CEO/CFO activity, unusual size.
    Returns a score from -100 to +100 with detected patterns.
    """

    def score(self, ticker: str, trades: List[InsiderTrade]) -> InsiderScore:
        """Score a list of insider trades.

        Args:
            ticker: Stock ticker.
            trades: List of insider trades to analyze.

        Returns:
            InsiderScore with score, label, patterns, and trades.
        """
        if not trades:
            return InsiderScore(
                ticker=ticker,
                score=0,
                label="NEUTRAL",
                patterns=["no_recent_trades"],
                trades=[],
            )

        raw_score = 0
        patterns: List[str] = []

        # ── 1. Individual trade scoring ───────────────────────────
        total_value = sum(t.value for t in trades)
        avg_value = total_value / len(trades) if trades else 0

        for trade in trades:
            title = trade.title
            is_buy = trade.transaction_type.upper() == "BUY"
            is_sell = trade.transaction_type.upper() == "SELL"

            if is_buy:
                if _is_ceo(title):
                    raw_score += SCORES["ceo_purchase"]
                    patterns.append(f"CEO purchase: {trade.insider_name} ({trade.value:,.0f})")
                elif _is_cfo(title):
                    raw_score += SCORES["cfo_purchase"]
                    patterns.append(f"CFO purchase: {trade.insider_name} ({trade.value:,.0f})")
                elif _is_officer(title):
                    raw_score += SCORES["officer_purchase"]
                elif _is_director(title):
                    raw_score += SCORES["director_purchase"]

                # Large purchase detection (>3x average)
                if avg_value > 0 and trade.value > 3 * avg_value:
                    raw_score += SCORES["large_purchase"]
                    patterns.append(
                        f"Large purchase: {trade.insider_name} "
                        f"({trade.value:,.0f}, {trade.value / avg_value:.1f}x avg)"
                    )

            elif is_sell:
                if _is_ceo(title):
                    raw_score += SCORES["ceo_sale"]
                    patterns.append(f"CEO sale: {trade.insider_name} ({trade.value:,.0f})")
                elif _is_cfo(title):
                    raw_score += SCORES["cfo_sale"]
                    patterns.append(f"CFO sale: {trade.insider_name} ({trade.value:,.0f})")
                elif _is_officer(title):
                    raw_score += SCORES["officer_sale"]
                elif _is_director(title):
                    # Director sales are often routine — small penalty
                    raw_score += SCORES["director_routine_sale"]

        # ── 2. Cluster detection ──────────────────────────────────
        # Group trades by week
        week_buys: defaultdict = defaultdict(list)
        week_sells: defaultdict = defaultdict(list)
        for trade in trades:
            week = _get_week_key(trade.date)
            if trade.transaction_type.upper() == "BUY":
                week_buys[week].append(trade)
            else:
                week_sells[week].append(trade)

        # Cluster buy: 3+ different insiders buying in same week
        for week, week_trades in week_buys.items():
            unique_insiders = set(t.insider_name for t in week_trades)
            if len(unique_insiders) >= 3:
                raw_score += SCORES["cluster_buy"]
                patterns.append(
                    f"Cluster buy: {len(unique_insiders)} insiders bought in week {week[1]}/{week[0]}"
                )

        # Cluster sell: 3+ different insiders selling in same week
        for week, week_trades in week_sells.items():
            unique_insiders = set(t.insider_name for t in week_trades)
            if len(unique_insiders) >= 3:
                raw_score += SCORES["cluster_sell"]
                patterns.append(
                    f"Cluster sell: {len(unique_insiders)} insiders sold in week {week[1]}/{week[0]}"
                )

        # ── 3. Buy/sell ratio ─────────────────────────────────────
        buys = [t for t in trades if t.transaction_type.upper() == "BUY"]
        sells = [t for t in trades if t.transaction_type.upper() == "SELL"]

        buy_value = sum(t.value for t in buys)
        sell_value = sum(t.value for t in sells)
        total = buy_value + sell_value

        if total > 0:
            net_ratio = (buy_value - sell_value) / total
            # Add a small bonus/penalty based on net direction
            raw_score += int(net_ratio * 20)

        # ── 4. Clamp and create score ─────────────────────────────
        clamped = max(-100, min(100, raw_score))
        label = InsiderScore.score_to_label(clamped)

        # Deduplicate patterns (keep unique)
        seen = set()
        unique_patterns = []
        for p in patterns:
            if p not in seen:
                seen.add(p)
                unique_patterns.append(p)

        return InsiderScore(
            ticker=ticker,
            score=clamped,
            label=label,
            patterns=unique_patterns,
            trades=trades,
        )
