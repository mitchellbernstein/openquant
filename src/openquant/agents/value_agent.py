"""Value investing agent — pure quantitative value analysis.

Evaluates stocks based on classic value investing metrics:
  - P/E ratio (price-to-earnings)
  - P/B ratio (price-to-book)
  - ROE (return on equity)
  - Debt-to-equity ratio
  - Free cash flow yield

No LLM needed. Uses simple rule-based thresholds derived from
academic value investing literature (Graham, Greenblatt).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from openquant.agents.base import BaseAgent, SignalResult
from openquant.data.protocol import FinancialStatement, Price
from openquant.data.resolver import DataResolver

logger = logging.getLogger(__name__)

# ── Value thresholds ──────────────────────────────────────────────────
# These are deliberately simple; they can be tuned per sector later.

PE_CHEAP = 15.0        # P/E below this is considered cheap
PE_EXPENSIVE = 30.0    # P/E above this is expensive
PB_CHEAP = 1.5         # P/B below this is cheap
PB_EXPENSIVE = 4.0     # P/B above this is expensive
ROE_GOOD = 0.15        # ROE above 15% is strong
DEBT_EQUITY_HIGH = 2.0 # Debt/equity above 2x is risky
FCF_YIELD_GOOD = 0.08  # FCF yield above 8% is attractive


class ValueInvestingAgent(BaseAgent):
    """Analyzes stocks using value investing principles.

    Scores a ticker on five value dimensions, each contributing to the
    final signal. Confidence reflects how many metrics had data available.
    """

    name = "value"
    description = "Value investing agent — P/E, P/B, ROE, debt, FCF yield"

    def analyze(self, ticker: str, data: DataResolver) -> SignalResult:
        scores: List[float] = []
        metrics: Dict[str, Any] = {}
        reasons: List[str] = []
        data_points = 0

        # ── 1. P/E ratio ───────────────────────────────────────────
        pe = self._get_pe(ticker, data)
        if pe is not None:
            data_points += 1
            metrics["pe_ratio"] = pe
            if pe <= 0:
                scores.append(-0.3)
                reasons.append(f"P/E is negative ({pe:.1f}) — likely losses")
            elif pe < PE_CHEAP:
                s = 0.5 * (1.0 - pe / PE_CHEAP)  # 0..0.5
                scores.append(min(0.5, s + 0.2))
                reasons.append(f"P/E {pe:.1f} is cheap (<{PE_CHEAP})")
            elif pe > PE_EXPENSIVE:
                scores.append(-0.4)
                reasons.append(f"P/E {pe:.1f} is expensive (>{PE_EXPENSIVE})")
            else:
                scores.append(0.0)
                reasons.append(f"P/E {pe:.1f} is moderate")
        else:
            reasons.append("P/E data unavailable")

        # ── 2. P/B ratio ───────────────────────────────────────────
        pb = self._get_pb(ticker, data)
        if pb is not None:
            data_points += 1
            metrics["pb_ratio"] = pb
            if pb < PB_CHEAP:
                scores.append(0.4)
                reasons.append(f"P/B {pb:.1f} is cheap (<{PB_CHEAP})")
            elif pb > PB_EXPENSIVE:
                scores.append(-0.3)
                reasons.append(f"P/B {pb:.1f} is expensive (>{PB_EXPENSIVE})")
            else:
                scores.append(0.0)
                reasons.append(f"P/B {pb:.1f} is moderate")
        else:
            reasons.append("P/B data unavailable")

        # ── 3. ROE ─────────────────────────────────────────────────
        roe = self._get_roe(ticker, data)
        if roe is not None:
            data_points += 1
            metrics["roe"] = roe
            if roe > ROE_GOOD:
                scores.append(0.4)
                reasons.append(f"ROE {roe:.1%} is strong (>{ROE_GOOD:.0%})")
            elif roe < 0:
                scores.append(-0.5)
                reasons.append(f"ROE {roe:.1%} is negative")
            else:
                scores.append(0.0)
                reasons.append(f"ROE {roe:.1%} is moderate")
        else:
            reasons.append("ROE data unavailable")

        # ── 4. Debt-to-equity ──────────────────────────────────────
        de = self._get_debt_equity(ticker, data)
        if de is not None:
            data_points += 1
            metrics["debt_equity"] = de
            if de > DEBT_EQUITY_HIGH:
                scores.append(-0.4)
                reasons.append(f"D/E {de:.1f} is high (>{DEBT_EQUITY_HIGH})")
            elif de < 0.5:
                scores.append(0.2)
                reasons.append(f"D/E {de:.1f} is low — strong balance sheet")
            else:
                scores.append(0.0)
                reasons.append(f"D/E {de:.1f} is moderate")
        else:
            reasons.append("Debt/equity data unavailable")

        # ── 5. Free cash flow yield ────────────────────────────────
        fcf_yield = self._get_fcf_yield(ticker, data)
        if fcf_yield is not None:
            data_points += 1
            metrics["fcf_yield"] = fcf_yield
            if fcf_yield > FCF_YIELD_GOOD:
                scores.append(0.5)
                reasons.append(f"FCF yield {fcf_yield:.1%} is attractive (>{FCF_YIELD_GOOD:.0%})")
            elif fcf_yield < 0:
                scores.append(-0.3)
                reasons.append(f"FCF yield {fcf_yield:.1%} is negative — burning cash")
            else:
                scores.append(0.0)
                reasons.append(f"FCF yield {fcf_yield:.1%} is moderate")
        else:
            reasons.append("FCF yield data unavailable")

        # ── Aggregate ─────────────────────────────────────────────
        if not scores:
            return SignalResult(
                agent_name=self.name,
                ticker=ticker,
                signal=0.0,
                confidence=0,
                reasoning="No value metrics available for analysis.",
                data=metrics,
            )

        avg_score = sum(scores) / len(scores)
        # Confidence scales with how many data points we had
        confidence = min(80, int(data_points / 5 * 80))

        return SignalResult(
            agent_name=self.name,
            ticker=ticker,
            signal=round(avg_score, 3),
            confidence=confidence,
            reasoning="; ".join(reasons),
            data=metrics,
        )

    # ── Private helpers ────────────────────────────────────────────

    def _get_pe(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Extract trailing P/E from income statement + price."""
        try:
            financials = data.get_financials(ticker, "income")
            if not financials:
                return None
            income = financials[0].items
            eps = income.get("basicEPS") or income.get("dilutedEPS") or income.get("eps")
            if not eps or eps <= 0:
                return None
            end = date.today()
            start = end - timedelta(days=7)
            prices = data.get_prices(ticker, start, end)
            if not prices:
                return None
            price = prices[-1].close
            return price / eps
        except Exception as exc:
            logger.debug("ValueAgent: P/E lookup failed for %s: %s", ticker, exc)
            return None

    def _get_pb(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Extract P/B from balance sheet + price."""
        try:
            financials = data.get_financials(ticker, "balance")
            if not financials:
                return None
            balance = financials[0].items
            book_value = (
                balance.get("totalStockholderEquity")
                or balance.get("stockholdersEquity")
                or balance.get("totalEquity")
            )
            shares = balance.get("commonStockSharesOutstanding") or balance.get("sharesOutstanding")
            if not book_value or not shares or book_value <= 0:
                return None
            book_per_share = book_value / shares
            end = date.today()
            start = end - timedelta(days=7)
            prices = data.get_prices(ticker, start, end)
            if not prices:
                return None
            price = prices[-1].close
            return price / book_per_share
        except Exception as exc:
            logger.debug("ValueAgent: P/B lookup failed for %s: %s", ticker, exc)
            return None

    def _get_roe(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Extract ROE from income statement + balance sheet."""
        try:
            income_stmts = data.get_financials(ticker, "income")
            balance_stmts = data.get_financials(ticker, "balance")
            if not income_stmts or not balance_stmts:
                return None
            net_income = (
                income_stmts[0].items.get("netIncome")
                or income_stmts[0].items.get("netIncomeCommonStockholders")
            )
            equity = (
                balance_stmts[0].items.get("totalStockholderEquity")
                or balance_stmts[0].items.get("stockholdersEquity")
            )
            if not net_income or not equity or equity == 0:
                return None
            return net_income / equity
        except Exception as exc:
            logger.debug("ValueAgent: ROE lookup failed for %s: %s", ticker, exc)
            return None

    def _get_debt_equity(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Extract debt-to-equity ratio from balance sheet."""
        try:
            financials = data.get_financials(ticker, "balance")
            if not financials:
                return None
            items = financials[0].items
            total_debt = items.get("totalDebt") or (
                (items.get("longTermDebt") or 0) + (items.get("shortTermDebt") or 0)
            )
            equity = items.get("totalStockholderEquity") or items.get("stockholdersEquity")
            if not equity or equity == 0:
                return None
            return total_debt / equity if total_debt else 0.0
        except Exception as exc:
            logger.debug("ValueAgent: D/E lookup failed for %s: %s", ticker, exc)
            return None

    def _get_fcf_yield(self, ticker: str, data: DataResolver) -> Optional[float]:
        """Estimate free cash flow yield from cashflow statement + market cap."""
        try:
            cashflow_stmts = data.get_financials(ticker, "cashflow")
            if not cashflow_stmts:
                return None
            items = cashflow_stmts[0].items
            fcf = (
                items.get("freeCashFlow")
                or (
                    (items.get("operatingCashFlow") or items.get("totalCashFromOperatingActivities") or 0)
                    - (items.get("capitalExpenditures") or items.get("capitalExpenditure") or 0)
                )
            )
            if fcf is None:
                return None
            company = data.get_company_info(ticker)
            if company and company.market_cap and company.market_cap > 0:
                return fcf / company.market_cap
            # Fallback: use price * shares
            end = date.today()
            start = end - timedelta(days=7)
            prices = data.get_prices(ticker, start, end)
            if not prices:
                return None
            price = prices[-1].close
            balance_stmts = data.get_financials(ticker, "balance")
            if not balance_stmts:
                return None
            shares = (
                balance_stmts[0].items.get("commonStockSharesOutstanding")
                or balance_stmts[0].items.get("sharesOutstanding")
            )
            if not shares:
                return None
            market_cap = price * shares
            if market_cap <= 0:
                return None
            return fcf / market_cap
        except Exception as exc:
            logger.debug("ValueAgent: FCF yield lookup failed for %s: %s", ticker, exc)
            return None
