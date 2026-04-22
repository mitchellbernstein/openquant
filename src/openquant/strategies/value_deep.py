"""Value Deep strategy for OpenQuant.

Deep value investing based on fundamental criteria:
  - Criteria: P/E < 15, ROE > 15%, debt/equity < 0.5, insider buying
  - Entry: All value criteria met + insider score > 0
  - Exit: P/E > 25 or fundamental deterioration
  - Long-term hold strategy
"""

from __future__ import annotations

import logging
from typing import List

from openquant.agents.base import SignalResult
from openquant.agents.insider_agent import InsiderAgent
from openquant.strategies.base import BaseStrategy, StrategyResult

logger = logging.getLogger(__name__)


class ValueDeepStrategy(BaseStrategy):
    """Deep value investing strategy.

    Buys stocks that meet strict fundamental criteria:
    low P/E, high ROE, low leverage, with insider buying confirmation.
    Long-term hold with exit on fundamental deterioration.
    """

    name = "value-deep"
    description = "Deep value investing — low P/E, high ROE, low debt, insider confirmation"

    # Fundamental thresholds
    MAX_PE = 15.0
    MIN_ROE = 0.15  # 15%
    MAX_DEBT_EQUITY = 0.5
    EXIT_PE = 25.0
    MIN_INSIDER_SCORE = 0  # Any positive insider signal

    # Position sizing
    POSITION_SIZE = 0.10  # 10% of portfolio per position

    # Risk parameters
    STOP_LOSS_PCT = 0.15  # 15% stop loss (wider for value)
    TAKE_PROFIT_PCT = 0.50  # 50% take profit (longer term)

    def __init__(self) -> None:
        self._insider_agent = InsiderAgent()

    def generate_signal(self, ticker: str, data) -> StrategyResult:
        """Generate a value deep signal.

        Args:
            ticker: Stock ticker symbol.
            data: DataResolver for fetching market data.

        Returns:
            StrategyResult with the strategy's recommendation.
        """
        from datetime import date, timedelta

        # Get current price
        end = date.today()
        start = end - timedelta(days=30)
        prices = data.get_prices(ticker, start, end)

        if not prices:
            return StrategyResult(
                strategy_name=self.name,
                ticker=ticker,
                action="HOLD",
                confidence=0,
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                position_size_pct=0.0,
                reasoning="No price data available",
            )

        current_price = prices[-1].close

        # Get insider signal
        insider_signal = self._insider_agent.analyze(ticker, data)
        insider_score = insider_signal.data.get("insider_score", 0)

        # Fetch financial data
        income_stmts = data.get_financials(ticker, statement_type="income")
        balance_stmts = data.get_financials(ticker, statement_type="balance")

        # Evaluate fundamental criteria
        criteria_met = []
        criteria_failed = []

        # ── P/E Ratio ───────────────────────────────────────────────
        pe_ratio = self._extract_pe(income_stmts, current_price, data, ticker)
        if pe_ratio is not None and pe_ratio > 0:
            if pe_ratio < self.MAX_PE:
                criteria_met.append(f"P/E {pe_ratio:.1f} < {self.MAX_PE}")
            else:
                criteria_failed.append(f"P/E {pe_ratio:.1f} >= {self.MAX_PE}")
        else:
            # If P/E not available, we can't evaluate this criterion
            criteria_failed.append("P/E data unavailable")

        # ── ROE ────────────────────────────────────────────────────
        roe = self._extract_roe(income_stmts, balance_stmts)
        if roe is not None:
            if roe > self.MIN_ROE:
                criteria_met.append(f"ROE {roe:.1%} > {self.MIN_ROE:.0%}")
            else:
                criteria_failed.append(f"ROE {roe:.1%} <= {self.MIN_ROE:.0%}")
        else:
            criteria_failed.append("ROE data unavailable")

        # ── Debt/Equity ──────────────────────────────────────────────
        debt_equity = self._extract_debt_equity(balance_stmts)
        if debt_equity is not None:
            if debt_equity < self.MAX_DEBT_EQUITY:
                criteria_met.append(f"D/E {debt_equity:.2f} < {self.MAX_DEBT_EQUITY}")
            else:
                criteria_failed.append(f"D/E {debt_equity:.2f} >= {self.MAX_DEBT_EQUITY}")
        else:
            criteria_failed.append("Debt/Equity data unavailable")

        # ── Insider confirmation ────────────────────────────────────
        if insider_score > self.MIN_INSIDER_SCORE:
            criteria_met.append(f"Insider score {insider_score} > 0")
        else:
            criteria_failed.append(f"Insider score {insider_score} <= 0 (no insider buying confirmation)")

        # ── Decision ────────────────────────────────────────────────
        # Buy only if ALL criteria are met
        if len(criteria_met) >= 4 and len(criteria_failed) == 0:
            action = "BUY"
            confidence = min(85, 50 + len(criteria_met) * 8)
            position_size = self.POSITION_SIZE
            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)
            reasoning = f"All value criteria met: {'; '.join(criteria_met)}"

        elif pe_ratio is not None and pe_ratio > self.EXIT_PE:
            # Exit if P/E exceeds exit threshold
            action = "SELL"
            confidence = min(75, int((pe_ratio - self.EXIT_PE) * 5 + 50))
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * 1.05, 2)
            take_profit = round(entry_price * 0.85, 2)
            reasoning = f"P/E ({pe_ratio:.1f}) exceeds exit threshold ({self.EXIT_PE})"

        else:
            action = "HOLD"
            confidence = max(10, 30 + len(criteria_met) * 5)
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)
            reasoning = f"Value criteria: met [{'; '.join(criteria_met)}], failed [{'; '.join(criteria_failed)}]"

        return StrategyResult(
            strategy_name=self.name,
            ticker=ticker,
            action=action,
            confidence=confidence,
            entry_price=round(entry_price, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_pct=round(position_size, 4),
            reasoning=reasoning,
            signals=[insider_signal],
        )

    def _extract_pe(self, income_stmts, current_price: float, data, ticker) -> float | None:
        """Extract P/E ratio from financial statements or company info."""
        # Try from company info first (yfinance often provides this)
        try:
            info = data.get_company_info(ticker)
            if info and hasattr(info, 'market_cap') and info.market_cap > 0:
                # Estimate from income statement
                if income_stmts:
                    latest = income_stmts[0]
                    eps = latest.items.get("basicEPS") or latest.items.get("dilutedEPS")
                    if eps and eps > 0:
                        return current_price / eps
        except Exception:
            pass

        # Try from income statement items
        if income_stmts:
            latest = income_stmts[0]
            eps = latest.items.get("basicEPS") or latest.items.get("dilutedEPS")
            if eps and eps > 0:
                return current_price / eps

        return None

    def _extract_roe(self, income_stmts, balance_stmts) -> float | None:
        """Extract Return on Equity from financial statements."""
        try:
            if income_stmts and balance_stmts:
                latest_income = income_stmts[0]
                latest_balance = balance_stmts[0]

                net_income = latest_income.items.get("netIncome") or latest_income.items.get("netIncomeLoss")
                equity = latest_balance.items.get("totalStockholdersEquity") or latest_balance.items.get("stockholdersEquity")

                if net_income and equity and equity > 0:
                    return net_income / equity
        except Exception:
            pass

        return None

    def _extract_debt_equity(self, balance_stmts) -> float | None:
        """Extract Debt/Equity ratio from financial statements."""
        try:
            if balance_stmts:
                latest = balance_stmts[0]

                total_debt = latest.items.get("totalDebt") or latest.items.get("longTermDebt")
                equity = latest.items.get("totalStockholdersEquity") or latest.items.get("stockholdersEquity")

                if total_debt is not None and equity and equity > 0:
                    return total_debt / equity
        except Exception:
            pass

        return None
