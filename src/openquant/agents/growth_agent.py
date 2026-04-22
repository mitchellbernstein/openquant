"""Growth investing agent — pure quantitative growth analysis.

Evaluates stocks based on growth trajectory metrics:
  - Revenue growth (YoY)
  - Earnings growth (YoY)
  - Margin expansion (gross + operating)
  - Analyst forward estimates

No LLM needed. Rule-based scoring from growth rates.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from openquant.agents.base import BaseAgent, SignalResult
from openquant.data.protocol import AnalystEstimate, FinancialStatement
from openquant.data.resolver import DataResolver

logger = logging.getLogger(__name__)

# ── Growth thresholds ────────────────────────────────────────────────

REVENUE_GROWTH_GOOD = 0.15    # 15% YoY revenue growth
REVENUE_GROWTH_GREAT = 0.30   # 30%+ is exceptional
EARNINGS_GROWTH_GOOD = 0.20   # 20% YoY earnings growth
EARNINGS_GROWTH_GREAT = 0.40  # 40%+ is exceptional
MARGIN_EXPANSION_GOOD = 0.02  # 2pp margin expansion YoY


class GrowthAgent(BaseAgent):
    """Analyzes stocks using growth investing principles.

    Scores based on revenue growth, earnings growth, margin expansion,
    and analyst forward estimates. Each dimension contributes to the
    final signal.
    """

    name = "growth"
    description = "Growth agent — revenue growth, earnings growth, margins, analyst estimates"

    def analyze(self, ticker: str, data: DataResolver) -> SignalResult:
        scores: List[float] = []
        metrics: Dict[str, Any] = {}
        reasons: List[str] = []
        data_points = 0

        # ── 1. Revenue growth ──────────────────────────────────────
        rev_growth = self._get_revenue_growth(ticker, data)
        if rev_growth is not None:
            data_points += 1
            metrics["revenue_growth"] = rev_growth
            if rev_growth > REVENUE_GROWTH_GREAT:
                scores.append(0.6)
                reasons.append(f"Revenue growth {rev_growth:.1%} is exceptional (>{REVENUE_GROWTH_GREAT:.0%})")
            elif rev_growth > REVENUE_GROWTH_GOOD:
                scores.append(0.4)
                reasons.append(f"Revenue growth {rev_growth:.1%} is strong (>{REVENUE_GROWTH_GOOD:.0%})")
            elif rev_growth > 0:
                scores.append(0.1)
                reasons.append(f"Revenue growth {rev_growth:.1%} is positive but modest")
            elif rev_growth < -0.1:
                scores.append(-0.5)
                reasons.append(f"Revenue declining {rev_growth:.1%} — serious concern")
            else:
                scores.append(-0.2)
                reasons.append(f"Revenue growth {rev_growth:.1%} is stagnant/declining")
        else:
            reasons.append("Revenue growth data unavailable")

        # ── 2. Earnings growth ─────────────────────────────────────
        earn_growth = self._get_earnings_growth(ticker, data)
        if earn_growth is not None:
            data_points += 1
            metrics["earnings_growth"] = earn_growth
            if earn_growth > EARNINGS_GROWTH_GREAT:
                scores.append(0.6)
                reasons.append(f"Earnings growth {earn_growth:.1%} is exceptional")
            elif earn_growth > EARNINGS_GROWTH_GOOD:
                scores.append(0.4)
                reasons.append(f"Earnings growth {earn_growth:.1%} is strong")
            elif earn_growth > 0:
                scores.append(0.1)
                reasons.append(f"Earnings growth {earn_growth:.1%} is positive but modest")
            elif earn_growth < -0.2:
                scores.append(-0.6)
                reasons.append(f"Earnings declining {earn_growth:.1%} — major red flag")
            else:
                scores.append(-0.2)
                reasons.append(f"Earnings growth {earn_growth:.1%} is stagnant/declining")
        else:
            reasons.append("Earnings growth data unavailable")

        # ── 3. Margin expansion ─────────────────────────────────────
        margin_exp = self._get_margin_expansion(ticker, data)
        if margin_exp is not None:
            data_points += 1
            metrics["margin_expansion"] = margin_exp
            if margin_exp > MARGIN_EXPANSION_GOOD:
                scores.append(0.4)
                reasons.append(f"Margin expanding by {margin_exp:.1%} — operating leverage")
            elif margin_exp < -0.03:
                scores.append(-0.4)
                reasons.append(f"Margin compressing by {margin_exp:.1%} — concerning")
            else:
                scores.append(0.0)
                reasons.append(f"Margin change {margin_exp:.1%} is roughly flat")
        else:
            reasons.append("Margin expansion data unavailable")

        # ── 4. Analyst forward estimates ───────────────────────────
        fwd_signal = self._get_analyst_signal(ticker, data)
        if fwd_signal is not None:
            data_points += 1
            metrics["analyst_consensus"] = fwd_signal
            if fwd_signal > 0.2:
                scores.append(0.3)
                reasons.append("Analyst consensus is bullish on growth")
            elif fwd_signal < -0.2:
                scores.append(-0.3)
                reasons.append("Analyst consensus is bearish on growth")
            else:
                scores.append(0.0)
                reasons.append("Analyst consensus is neutral on growth")
        else:
            reasons.append("Analyst estimate data unavailable")

        # ── Aggregate ──────────────────────────────────────────────
        if not scores:
            return SignalResult(
                agent_name=self.name,
                ticker=ticker,
                signal=0.0,
                confidence=0,
                reasoning="No growth metrics available for analysis.",
                data=metrics,
            )

        avg_score = sum(scores) / len(scores)
        # Growth analysis needs at least 2 data points for decent confidence
        confidence = min(80, int(data_points / 4 * 80))

        return SignalResult(
            agent_name=self.name,
            ticker=ticker,
            signal=round(avg_score, 3),
            confidence=confidence,
            reasoning="; ".join(reasons),
            data=metrics,
        )

    # ── Private helpers ────────────────────────────────────────────

    def _get_revenue_growth(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Calculate YoY revenue growth from income statements."""
        try:
            stmts = data.get_financials(ticker, "income")
            if len(stmts) < 2:
                return None
            # Sort by period end date (newest first)
            sorted_stmts = sorted(stmts, key=lambda s: s.period_end_date, reverse=True)
            current = sorted_stmts[0].items.get("totalRevenue") or sorted_stmts[0].items.get("revenue")
            prior = sorted_stmts[1].items.get("totalRevenue") or sorted_stmts[1].items.get("revenue")
            if not current or not prior or prior == 0:
                return None
            return (current - prior) / abs(prior)
        except Exception as exc:
            logger.debug("GrowthAgent: revenue growth failed for %s: %s", ticker, exc)
            return None

    def _get_earnings_growth(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Calculate YoY earnings growth from income statements."""
        try:
            stmts = data.get_financials(ticker, "income")
            if len(stmts) < 2:
                return None
            sorted_stmts = sorted(stmts, key=lambda s: s.period_end_date, reverse=True)
            current = (
                sorted_stmts[0].items.get("netIncome")
                or sorted_stmts[0].items.get("netIncomeCommonStockholders")
            )
            prior = (
                sorted_stmts[1].items.get("netIncome")
                or sorted_stmts[1].items.get("netIncomeCommonStockholders")
            )
            if current is None or prior is None:
                return None
            if prior == 0:
                # Avoid division by zero — check if current is positive growth
                return 1.0 if current > 0 else -1.0
            return (current - prior) / abs(prior)
        except Exception as exc:
            logger.debug("GrowthAgent: earnings growth failed for %s: %s", ticker, exc)
            return None

    def _get_margin_expansion(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Calculate operating margin expansion YoY."""
        try:
            stmts = data.get_financials(ticker, "income")
            if len(stmts) < 2:
                return None
            sorted_stmts = sorted(stmts, key=lambda s: s.period_end_date, reverse=True)

            current_revenue = sorted_stmts[0].items.get("totalRevenue") or sorted_stmts[0].items.get("revenue")
            prior_revenue = sorted_stmts[1].items.get("totalRevenue") or sorted_stmts[1].items.get("revenue")

            current_op_income = (
                sorted_stmts[0].items.get("operatingIncome")
                or sorted_stmts[0].items.get("incomeFromOperations")
            )
            prior_op_income = (
                sorted_stmts[1].items.get("operatingIncome")
                or sorted_stmts[1].items.get("incomeFromOperations")
            )

            if not current_revenue or not prior_revenue:
                return None
            if current_revenue == 0 or prior_revenue == 0:
                return None
            if current_op_income is None or prior_op_income is None:
                return None

            current_margin = current_op_income / current_revenue
            prior_margin = prior_op_income / prior_revenue
            return current_margin - prior_margin
        except Exception as exc:
            logger.debug("GrowthAgent: margin expansion failed for %s: %s", ticker, exc)
            return None

    def _get_analyst_signal(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Convert analyst estimates to a growth signal."""
        try:
            estimates = data.get_analyst_estimates(ticker)
            if not estimates:
                return None
            # Look for EPS and revenue estimates
            eps_est = [e for e in estimates if e.estimate_type == "eps"]
            rev_est = [e for e in estimates if e.estimate_type == "revenue"]
            signals = []

            if eps_est:
                # If consensus > 0 and there's a range, use breadth as signal
                e = eps_est[0]
                if e.consensus_avg > 0:
                    spread = (e.consensus_high - e.consensus_low) / max(abs(e.consensus_avg), 0.01)
                    # Narrow spread + positive avg = more confidence in growth
                    signals.append(0.2 if spread < 0.5 else 0.0)
                else:
                    signals.append(-0.2)

            if rev_est:
                e = rev_est[0]
                if e.consensus_avg > 0:
                    signals.append(0.2)
                else:
                    signals.append(-0.2)

            if not signals:
                return None
            return sum(signals) / len(signals)
        except Exception as exc:
            logger.debug("GrowthAgent: analyst signal failed for %s: %s", ticker, exc)
            return None
