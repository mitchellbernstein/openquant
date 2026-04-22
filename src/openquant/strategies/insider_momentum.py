"""Insider Momentum strategy for OpenQuant.

Trades on insider buying momentum signals:
  - Trigger: 3+ insider buys in same week OR CEO purchase
  - Entry: When insider signal score > +40
  - Exit: Stop loss at -5%, take profit at +15%, or 30-day time stop
  - Position size: Half Kelly based on historical insider signal win rate
  - Backtestable
"""

from __future__ import annotations

import logging
from typing import List

from openquant.agents.base import SignalResult
from openquant.agents.insider_agent import InsiderAgent
from openquant.insider.models import InsiderScore
from openquant.strategies.base import BaseStrategy, StrategyResult

logger = logging.getLogger(__name__)


class InsiderMomentumStrategy(BaseStrategy):
    """Insider buying momentum strategy.

    Buys when insider sentiment is strongly positive (score > +40),
    driven by cluster buys, CEO purchases, or unusual activity.
    Uses half-Kelly position sizing based on historical win rates.
    """

    name = "insider-momentum"
    description = "Trade on insider buying momentum — cluster buys, CEO activity, unusual size"

    # Strategy parameters
    ENTRY_SCORE_THRESHOLD = 40  # Insider score must exceed this
    STOP_LOSS_PCT = 0.05  # 5% stop loss
    TAKE_PROFIT_PCT = 0.15  # 15% take profit
    TIME_STOP_DAYS = 30  # Close after 30 days regardless
    HISTORICAL_WIN_RATE = 0.58  # Historical win rate for insider signals
    HISTORICAL_AVG_WIN = 0.12  # Average winning trade return
    HISTORICAL_AVG_LOSS = 0.04  # Average losing trade loss

    def __init__(self) -> None:
        self._insider_agent = InsiderAgent()

    def generate_signal(self, ticker: str, data) -> StrategyResult:
        """Generate an insider momentum signal.

        Args:
            ticker: Stock ticker symbol.
            data: DataResolver for fetching market data.

        Returns:
            StrategyResult with the strategy's recommendation.
        """
        # Get insider signal
        insider_signal = self._insider_agent.analyze(ticker, data)

        # Get current price
        from datetime import date, timedelta
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
                signals=[insider_signal],
            )

        current_price = prices[-1].close

        # Extract insider score from signal data
        insider_score = insider_signal.data.get("insider_score", 0)

        # Check for specific patterns
        patterns = insider_signal.data.get("patterns_detected", [])
        has_cluster_buy = any("cluster buy" in p.lower() for p in patterns)
        has_ceo_purchase = any("ceo purchase" in p.lower() for p in patterns)

        # ── Entry decision ──────────────────────────────────────────
        if insider_score > self.ENTRY_SCORE_THRESHOLD:
            action = "BUY"
            # Confidence based on score magnitude and pattern strength
            confidence = min(90, insider_score + 10)
            if has_ceo_purchase:
                confidence = min(95, confidence + 10)
            if has_cluster_buy:
                confidence = min(95, confidence + 10)

            # Position sizing: half Kelly
            from openquant.risk.sizing import half_kelly
            kelly = half_kelly(
                self.HISTORICAL_WIN_RATE,
                self.HISTORICAL_AVG_WIN,
                self.HISTORICAL_AVG_LOSS,
            )
            position_size = min(kelly, 0.25)  # Cap at 25% of portfolio

            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)

            # Build reasoning
            reasons = []
            if has_ceo_purchase:
                reasons.append("CEO purchase detected")
            if has_cluster_buy:
                reasons.append("Cluster buy (3+ insiders same week)")
            reasons.append(f"Insider score: {insider_score} (threshold: {self.ENTRY_SCORE_THRESHOLD})")
            reasons.append(f"Half-Kelly position: {position_size:.1%}")
            reasoning = "; ".join(reasons)

        elif insider_score < -self.ENTRY_SCORE_THRESHOLD:
            # Strong insider selling — sell signal
            action = "SELL"
            confidence = min(80, abs(insider_score))
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * (1 + self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 - self.TAKE_PROFIT_PCT), 2)
            reasoning = f"Strong insider selling (score: {insider_score}); patterns: {', '.join(patterns[:3])}"

        else:
            action = "HOLD"
            confidence = max(10, 50 - abs(insider_score))
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)
            reasoning = f"Insider score ({insider_score}) below entry threshold ({self.ENTRY_SCORE_THRESHOLD})"

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
