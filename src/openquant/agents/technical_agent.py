"""Technical analysis agent — pure quantitative technical indicators.

Evaluates stocks using classic technical analysis:
  - SMA crossover (50/200 day — golden/death cross)
  - RSI (relative strength index — overbought/oversold)
  - Volume pattern detection (spikes, trends)
  - Price momentum

All calculations use numpy. No LLM needed.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

from openquant.agents.base import BaseAgent, SignalResult
from openquant.data.protocol import Price
from openquant.data.resolver import DataResolver

logger = logging.getLogger(__name__)

# ── Technical thresholds ──────────────────────────────────────────────

RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
SMA_SHORT = 50
SMA_LONG = 200
VOLUME_SPIKE_THRESHOLD = 2.0  # 2x average volume


class TechnicalAgent(BaseAgent):
    """Analyzes stocks using technical indicators.

    Pure quantitative — SMA crossover, RSI, volume patterns, and price
    momentum. No LLM required.
    """

    name = "technical"
    description = "Technical agent — SMA crossover, RSI, volume patterns, momentum"

    def analyze(self, ticker: str, data: DataResolver) -> SignalResult:
        scores: List[float] = []
        metrics: Dict[str, Any] = {}
        reasons: List[str] = []
        data_points = 0

        # Fetch price data — need at least 200 trading days for SMA200
        end = date.today()
        start = end - timedelta(days=400)  # ~280 trading days
        try:
            prices = data.get_prices(ticker, start, end)
        except Exception as exc:
            logger.debug("TechnicalAgent: price fetch failed for %s: %s", ticker, exc)
            prices = []

        if not prices or len(prices) < 20:
            return SignalResult(
                agent_name=self.name,
                ticker=ticker,
                signal=0.0,
                confidence=0,
                reasoning="Insufficient price data for technical analysis.",
                data=metrics,
            )

        # Convert to numpy arrays
        closes = np.array([p.close for p in prices], dtype=float)
        volumes = np.array([p.volume for p in prices], dtype=float)

        # ── 1. SMA crossover ───────────────────────────────────────
        sma_signal = self._sma_crossover(closes)
        if sma_signal is not None:
            data_points += 1
            metrics["sma50"] = float(np.mean(closes[-SMA_SHORT:])) if len(closes) >= SMA_SHORT else None
            metrics["sma200"] = float(np.mean(closes[-SMA_LONG:])) if len(closes) >= SMA_LONG else None
            metrics["sma_signal"] = sma_signal
            if sma_signal > 0.3:
                scores.append(0.5)
                reasons.append("Golden cross — SMA50 above SMA200")
            elif sma_signal < -0.3:
                scores.append(-0.5)
                reasons.append("Death cross — SMA50 below SMA200")
            elif sma_signal > 0:
                scores.append(0.2)
                reasons.append("Price above SMA50 (short-term uptrend)")
            else:
                scores.append(-0.2)
                reasons.append("Price below SMA50 (short-term downtrend)")
        else:
            reasons.append("Insufficient data for SMA crossover")

        # ── 2. RSI ─────────────────────────────────────────────────
        rsi = self._compute_rsi(closes)
        if rsi is not None:
            data_points += 1
            metrics["rsi"] = round(rsi, 1)
            if rsi > RSI_OVERBOUGHT:
                scores.append(-0.4)
                reasons.append(f"RSI {rsi:.1f} — overbought (>{RSI_OVERBOUGHT})")
            elif rsi < RSI_OVERSOLD:
                scores.append(0.4)
                reasons.append(f"RSI {rsi:.1f} — oversold (<{RSI_OVERSOLD})")
            elif rsi > 55:
                scores.append(0.1)
                reasons.append(f"RSI {rsi:.1f} — mildly bullish")
            elif rsi < 45:
                scores.append(-0.1)
                reasons.append(f"RSI {rsi:.1f} — mildly bearish")
            else:
                scores.append(0.0)
                reasons.append(f"RSI {rsi:.1f} — neutral")
        else:
            reasons.append("Insufficient data for RSI")

        # ── 3. Volume patterns ─────────────────────────────────────
        vol_signal = self._volume_analysis(volumes, closes)
        if vol_signal is not None:
            data_points += 1
            metrics["volume_signal"] = vol_signal
            if vol_signal > 0.3:
                scores.append(0.3)
                reasons.append("High volume on up days — accumulation")
            elif vol_signal < -0.3:
                scores.append(-0.3)
                reasons.append("High volume on down days — distribution")
            else:
                scores.append(0.0)
                reasons.append("Volume patterns neutral")
        else:
            reasons.append("Insufficient data for volume analysis")

        # ── 4. Price momentum ──────────────────────────────────────
        momentum = self._momentum(closes)
        if momentum is not None:
            data_points += 1
            metrics["momentum_20d"] = round(momentum, 3)
            if momentum > 0.05:
                scores.append(0.3)
                reasons.append(f"Strong 20-day momentum ({momentum:.1%})")
            elif momentum < -0.05:
                scores.append(-0.3)
                reasons.append(f"Negative 20-day momentum ({momentum:.1%})")
            else:
                scores.append(0.0)
                reasons.append(f"Flat 20-day momentum ({momentum:.1%})")
        else:
            reasons.append("Insufficient data for momentum")

        # ── Aggregate ──────────────────────────────────────────────
        if not scores:
            return SignalResult(
                agent_name=self.name,
                ticker=ticker,
                signal=0.0,
                confidence=0,
                reasoning="No technical indicators could be computed.",
                data=metrics,
            )

        avg_score = sum(scores) / len(scores)
        confidence = min(75, int(data_points / 4 * 75))

        return SignalResult(
            agent_name=self.name,
            ticker=ticker,
            signal=round(avg_score, 3),
            confidence=confidence,
            reasoning="; ".join(reasons),
            data=metrics,
        )

    # ── Private helpers ────────────────────────────────────────────

    def _sma_crossover(self, closes: np.ndarray) -> Optional[float]:
        """Compute SMA crossover signal.

        Returns a value indicating the relationship between price, SMA50,
        and SMA200. Positive = bullish alignment, negative = bearish.
        """
        n = len(closes)
        if n < SMA_SHORT:
            return None

        sma_short = np.mean(closes[-SMA_SHORT:])
        current_price = closes[-1]

        if n >= SMA_LONG:
            sma_long = np.mean(closes[-SMA_LONG:])
            # Full golden/death cross
            if sma_short > sma_long and current_price > sma_short:
                return 0.5 + min(0.5, (sma_short - sma_long) / sma_long * 10)
            elif sma_short < sma_long and current_price < sma_short:
                return -0.5 - min(0.5, (sma_long - sma_short) / sma_long * 10)
            elif current_price > sma_short:
                return 0.2
            else:
                return -0.2
        else:
            # Only SMA50 available
            if current_price > sma_short:
                return 0.2
            else:
                return -0.2

    def _compute_rsi(self, closes: np.ndarray, period: int = 14) -> Optional[float]:
        """Compute RSI using Wilder's smoothing method."""
        if len(closes) < period + 1:
            return None

        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        # Wilder's smoothing (exponential moving average)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return float(rsi)

    def _volume_analysis(self, volumes: np.ndarray, closes: np.ndarray) -> Optional[float]:
        """Analyze volume patterns — accumulation vs distribution.

        Compares volume on up-days vs down-days over the last 20 sessions.
        """
        n = len(volumes)
        if n < 20:
            return None

        recent_vol = volumes[-20:]
        recent_closes = closes[-20:]
        price_changes = np.diff(recent_closes[-20:])

        # Pad to same length
        if len(price_changes) < 20:
            vol_slice = recent_vol[1:21]
        else:
            vol_slice = recent_vol[-20:]

        min_len = min(len(price_changes), len(vol_slice))
        price_changes = price_changes[-min_len:]
        vol_slice = vol_slice[-min_len:]

        up_mask = price_changes > 0
        down_mask = price_changes < 0

        up_volume = np.sum(vol_slice[up_mask]) if np.any(up_mask) else 0
        down_volume = np.sum(vol_slice[down_mask]) if np.any(down_mask) else 0
        total_volume = up_volume + down_volume

        if total_volume == 0:
            return 0.0

        # Net volume direction: positive = accumulation, negative = distribution
        net_ratio = (up_volume - down_volume) / total_volume

        # Also check for volume spikes
        avg_vol = np.mean(volumes[-50:]) if len(volumes) >= 50 else np.mean(volumes)
        latest_vol = volumes[-1]
        spike = latest_vol / avg_vol if avg_vol > 0 else 1.0

        metrics_extra = {"volume_spike": round(float(spike), 2)}
        # Spike weighting — if latest day has unusual volume, boost signal
        boost = 0.0
        if spike > VOLUME_SPIKE_THRESHOLD:
            boost = 0.1 if price_changes[-1] > 0 else -0.1

        return float(net_ratio + boost)

    def _momentum(self, closes: np.ndarray) -> Optional[float]:
        """Compute 20-day price momentum (rate of change)."""
        if len(closes) < 21:
            return None
        return float((closes[-1] - closes[-21]) / closes[-21])
