"""Technical Breakout strategy for OpenQuant.

Trend-following with insider confirmation:
  - Entry: Price breaks above 50-day SMA with 2x volume + insider buying
  - Exit: Price falls below 20-day SMA or stop at -3%
  - Combines technical analysis with insider signal confirmation
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List

import numpy as np

from openquant.agents.base import SignalResult
from openquant.agents.insider_agent import InsiderAgent
from openquant.strategies.base import BaseStrategy, StrategyResult

logger = logging.getLogger(__name__)


class TechnicalBreakoutStrategy(BaseStrategy):
    """Technical breakout strategy with insider confirmation.

    Buys when price breaks above the 50-day SMA on high volume (2x average)
    and insider buying is present. Exits when price falls below the
    20-day SMA or hits a tight 3% stop loss.
    """

    name = "technical-breakout"
    description = "Breakout trading with volume confirmation and insider signal overlay"

    # Technical parameters
    SMA_PERIOD = 50  # 50-day SMA for breakout
    SHORT_SMA_PERIOD = 20  # 20-day SMA for exit
    VOLUME_MULTIPLIER = 2.0  # Volume must be 2x average
    MIN_INSIDER_SCORE = 0  # Any positive insider signal adds confidence

    # Risk parameters
    STOP_LOSS_PCT = 0.03  # 3% stop loss (tight for breakout)
    TAKE_PROFIT_PCT = 0.12  # 12% take profit
    POSITION_SIZE = 0.06  # 6% of portfolio per breakout

    # Historical stats for Kelly sizing
    HISTORICAL_WIN_RATE = 0.45  # Breakouts have lower win rate but higher payoff
    HISTORICAL_AVG_WIN = 0.10
    HISTORICAL_AVG_LOSS = 0.025

    def __init__(self) -> None:
        self._insider_agent = InsiderAgent()

    def generate_signal(self, ticker: str, data) -> StrategyResult:
        """Generate a technical breakout signal.

        Args:
            ticker: Stock ticker symbol.
            data: DataResolver for fetching market data.

        Returns:
            StrategyResult with the strategy's recommendation.
        """
        # Fetch enough price data for SMA calculation
        end = date.today()
        start = end - timedelta(days=120)  # Extra buffer for 50-day SMA
        prices = data.get_prices(ticker, start, end)

        if not prices or len(prices) < self.SMA_PERIOD + 5:
            return StrategyResult(
                strategy_name=self.name,
                ticker=ticker,
                action="HOLD",
                confidence=0,
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                position_size_pct=0.0,
                reasoning="Insufficient price data for technical analysis",
            )

        # Get insider signal
        insider_signal = self._insider_agent.analyze(ticker, data)
        insider_score = insider_signal.data.get("insider_score", 0)

        # ── Technical calculations ──────────────────────────────────
        closes = np.array([p.close for p in prices], dtype=float)
        volumes = np.array([p.volume for p in prices], dtype=float)

        current_price = float(closes[-1])

        # 50-day SMA
        sma_50 = float(np.mean(closes[-self.SMA_PERIOD:]))
        # 20-day SMA
        sma_20 = float(np.mean(closes[-self.SHORT_SMA_PERIOD:]))
        # Average volume (last 20 days)
        avg_volume = float(np.mean(volumes[-20:]))
        # Current volume
        current_volume = float(volumes[-1])

        # ── Breakout detection ─────────────────────────────────────
        price_above_sma50 = current_price > sma_50
        price_above_sma20 = current_price > sma_20
        volume_surge = current_volume > avg_volume * self.VOLUME_MULTIPLIER if avg_volume > 0 else False

        # Check if this is a fresh breakout (price just crossed above SMA50)
        prev_close = float(closes[-2])
        prev_sma50 = float(np.mean(closes[-(self.SMA_PERIOD + 1):-1]))
        fresh_breakout = prev_close <= prev_sma50 and current_price > sma_50

        # ── Build criteria ──────────────────────────────────────────
        criteria_met = []
        criteria_failed = []

        if price_above_sma50:
            criteria_met.append(f"Price ({current_price:.2f}) above 50d SMA ({sma_50:.2f})")
        else:
            criteria_failed.append(f"Price ({current_price:.2f}) below 50d SMA ({sma_50:.2f})")

        if volume_surge:
            vol_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            criteria_met.append(f"Volume surge: {vol_ratio:.1f}x average")
        else:
            vol_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            criteria_failed.append(f"Low volume: {vol_ratio:.1f}x (need {self.VOLUME_MULTIPLIER:.0f}x)")

        if insider_score > self.MIN_INSIDER_SCORE:
            criteria_met.append(f"Insider buying (score: {insider_score})")
        else:
            criteria_failed.append(f"No insider buying (score: {insider_score})")

        if fresh_breakout:
            criteria_met.append("Fresh breakout above 50d SMA")

        # ── Decision ────────────────────────────────────────────────
        # Buy on breakout with volume + insider confirmation
        if price_above_sma50 and volume_surge and insider_score > self.MIN_INSIDER_SCORE:
            action = "BUY"
            confidence = min(85, 40 + len(criteria_met) * 10)
            if fresh_breakout:
                confidence = min(90, confidence + 10)

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
            reasoning = f"Breakout confirmed: {'; '.join(criteria_met)}"

        elif not price_above_sma20:
            # Below 20-day SMA — exit/sell signal
            action = "SELL"
            confidence = min(70, 50 + (1 if not price_above_sma50 else 0) * 20)
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * 1.03, 2)
            take_profit = round(entry_price * 0.88, 2)
            reasoning = f"Price below 20d SMA ({sma_20:.2f}) — trend broken"

        elif price_above_sma50 and not volume_surge:
            # Above SMA but no volume — watch/hold
            action = "HOLD"
            confidence = min(50, 30 + (10 if insider_score > 0 else 0))
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)
            reasoning = f"Above SMA but no volume confirmation: {'; '.join(criteria_failed)}"

        else:
            action = "HOLD"
            confidence = max(10, 25 + len(criteria_met) * 5)
            position_size = 0.0
            entry_price = current_price
            stop_loss = round(entry_price * (1 - self.STOP_LOSS_PCT), 2)
            take_profit = round(entry_price * (1 + self.TAKE_PROFIT_PCT), 2)
            reasoning = f"No breakout signal: met [{'; '.join(criteria_met)}], failed [{'; '.join(criteria_failed)}]"

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
