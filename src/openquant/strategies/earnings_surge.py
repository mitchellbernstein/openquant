"""Earnings Surge strategy for OpenQuant.

Short-term strategy around earnings events:
  - Pre-earnings: Buy if estimate revisions trending up + insider buying
  - Post-earnings: Sell 2 days after if beat, sell immediately if miss
  - Short-term strategy with tight risk management
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List, Optional

from openquant.agents.base import SignalResult
from openquant.agents.insider_agent import InsiderAgent
from openquant.strategies.base import BaseStrategy, StrategyResult

logger = logging.getLogger(__name__)


class EarningsSurgeStrategy(BaseStrategy):
    """Earnings surge strategy.

    Captures post-earnings announcement drift (PEAD) by buying ahead
    of earnings when estimates are being revised upward and insiders
    are buying. Exits based on earnings results.
    """

    name = "earnings-surge"
    description = "Capture post-earnings announcement drift — estimate revisions + insider confirmation"

    # Strategy parameters
    MIN_REVISION_TREND = 2  # At least 2 upward revisions in recent estimates
    MIN_INSIDER_SCORE = 10  # Insiders should be net buyers
    STOP_LOSS_PCT = 0.04  # 4% stop loss (tight for short-term)
    TAKE_PROFIT_PCT = 0.10  # 10% take profit
    TIME_STOP_DAYS = 10  # Short time horizon
    POSITION_SIZE = 0.08  # 8% of portfolio

    # Historical stats for Kelly sizing
    HISTORICAL_WIN_RATE = 0.55
    HISTORICAL_AVG_WIN = 0.08
    HISTORICAL_AVG_LOSS = 0.03

    def __init__(self) -> None:
        self._insider_agent = InsiderAgent()

    def generate_signal(self, ticker: str, data) -> StrategyResult:
        """Generate an earnings surge signal.

        Args:
            ticker: Stock ticker symbol.
            data: DataResolver for fetching market data.

        Returns:
            StrategyResult with the strategy's recommendation.
        """
        # Get current price
        end = date.today()
        start = end - timedelta(days=60)
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

        # Get analyst estimates
        estimates = data.get_analyst_estimates(ticker)

        # Evaluate earnings-related criteria
        criteria_met = []
        criteria_failed = []

        # ── Estimate revision trend ─────────────────────────────────
        revision_signal = self._evaluate_estimates(estimates)
        if revision_signal >= self.MIN_REVISION_TREND:
            criteria_met.append(f"Estimate revisions trending up ({revision_signal} positive)")
        elif revision_signal < 0:
            criteria_failed.append(f"Estimate revisions trending down ({revision_signal})")
        else:
            criteria_failed.append(f"Neutral estimate revision trend ({revision_signal})")

        # ── Insider confirmation ────────────────────────────────────
        if insider_score > self.MIN_INSIDER_SCORE:
            criteria_met.append(f"Insider buying (score: {insider_score})")
        else:
            criteria_failed.append(f"No insider buying confirmation (score: {insider_score})")

        # ── Price momentum (recent uptrend) ─────────────────────────
        if len(prices) >= 20:
            recent = [p.close for p in prices[-5:]]
            earlier = [p.close for p in prices[-20:-15]]
            recent_avg = sum(recent) / len(recent)
            earlier_avg = sum(earlier) / len(earlier)
            if recent_avg > earlier_avg * 1.02:
                criteria_met.append("Short-term price momentum positive")
            elif recent_avg < earlier_avg * 0.98:
                criteria_failed.append("Short-term price momentum negative")

        # ── Decision ────────────────────────────────────────────────
        if len(criteria_met) >= 2 and revision_signal >= self.MIN_REVISION_TREND and insider_score > self.MIN_INSIDER_SCORE:
            action = "BUY"
            confidence = min(80, 40 + len(criteria_met) * 12 + revision_signal * 5)

            # Half-Kelly position sizing
            from openquant.risk.sizing import half_kelly
            kelly = half_kelly(
                self.HISTORICAL_WIN_RATE,
                self.HISTORICAL_AVG_WIN,
                self.HISTORICAL_AVG_LOSS,
            )
            position_size = min(kelly, self.POSITION_SIZE)

            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)
            reasoning = f"Pre-earnings surge: {'; '.join(criteria_met)}"

        elif revision_signal < 0:
            # Negative estimate revisions — potential sell
            action = "SELL"
            confidence = min(70, 40 + abs(revision_signal) * 5)
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * 1.04, 2)
            take_profit = round(entry_price * 0.90, 2)
            reasoning = f"Post-earnings miss risk: {'; '.join(criteria_failed)}"

        else:
            action = "HOLD"
            confidence = max(10, 30 + len(criteria_met) * 5)
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)
            reasoning = f"Earnings criteria: met [{'; '.join(criteria_met)}], failed [{'; '.join(criteria_failed)}]"

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

    def _evaluate_estimates(self, estimates) -> int:
        """Evaluate analyst estimate revision trend.

        Returns:
            Positive number = upward revision trend
            Negative number = downward revision trend
            0 = neutral
        """
        if not estimates:
            return 0

        # Focus on EPS estimates
        eps_estimates = [e for e in estimates if e.estimate_type == "eps"]
        if not eps_estimates:
            return 0

        # If consensus is above the midpoint of the range, it suggests
        # upward revisions have been happening
        upward_count = 0
        for est in eps_estimates:
            mid = (est.consensus_low + est.consensus_high) / 2
            if est.consensus_avg > mid * 1.01:  # Above midpoint = upward revision
                upward_count += 1
            elif est.consensus_avg < mid * 0.99:  # Below midpoint = downward revision
                upward_count -= 1

        return upward_count
