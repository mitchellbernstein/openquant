"""Position sizing methods for OpenQuant.

Implements:
  - Kelly Criterion (full and half)
  - Risk parity (equal risk contribution)

All methods are pure math — no LLM needed.
"""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)


def kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
) -> float:
    """Calculate the full Kelly criterion fraction.

    Kelly fraction = win_rate - (1 - win_rate) / (avg_win / avg_loss)

    This maximizes long-term geometric growth but can be very aggressive.
    In practice, half-Kelly is preferred.

    Args:
        win_rate: Fraction of winning trades (0 to 1).
        avg_win: Average gain on winning trades (as a fraction, e.g. 0.10 = 10%).
        avg_loss: Average loss on losing trades (as a fraction, e.g. 0.05 = 5%).

    Returns:
        Kelly fraction (0 to 1). Returns 0 if inputs are invalid.
    """
    if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0

    win_loss_ratio = avg_win / avg_loss
    kelly = win_rate - (1 - win_rate) / win_loss_ratio

    # Clamp to [0, 1] — negative Kelly means don't trade
    return max(0.0, min(1.0, kelly))


def half_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
) -> float:
    """Calculate the half-Kelly fraction.

    Half-Kelly is the full Kelly divided by 2. It provides ~75% of the
    growth rate with significantly less volatility and drawdown.

    Args:
        win_rate: Fraction of winning trades (0 to 1).
        avg_win: Average gain on winning trades (fraction).
        avg_loss: Average loss on losing trades (fraction).

    Returns:
        Half-Kelly fraction (0 to 0.5).
    """
    return kelly_criterion(win_rate, avg_win, avg_loss) / 2.0


def risk_parity(
    volatilities: Dict[str, float],
) -> Dict[str, float]:
    """Calculate risk-parity position sizes.

    Each asset gets an allocation inversely proportional to its volatility,
    so that each contributes equally to portfolio risk.

    Args:
        volatilities: Dict mapping ticker to annualized volatility (e.g. 0.30 = 30%).

    Returns:
        Dict mapping ticker to portfolio fraction (sums to 1.0).
    """
    if not volatilities:
        return {}

    # Inverse volatility weighting
    inv_vols: Dict[str, float] = {}
    for ticker, vol in volatilities.items():
        if vol > 0:
            inv_vols[ticker] = 1.0 / vol
        else:
            # Zero volatility — assign very small weight
            inv_vols[ticker] = 0.0

    total = sum(inv_vols.values())
    if total == 0:
        # Equal weight if all volatilities are zero
        n = len(volatilities)
        return {ticker: 1.0 / n for ticker in volatilities}

    return {ticker: inv / total for ticker, inv in inv_vols.items()}


def equal_weight(tickers: List[str]) -> Dict[str, float]:
    """Simple equal-weight position sizing.

    Args:
        tickers: List of tickers.

    Returns:
        Dict mapping ticker to equal portfolio fraction.
    """
    if not tickers:
        return {}
    weight = 1.0 / len(tickers)
    return {ticker: weight for ticker in tickers}


def volatility_target(
    volatilities: Dict[str, float],
    target_vol: float = 0.15,
) -> Dict[str, float]:
    """Size positions to target a specific portfolio volatility.

    Scales each position so the portfolio's expected volatility is
    close to target_vol. Uses equal-risk contribution as a starting
    point, then scales the total.

    Args:
        volatilities: Dict mapping ticker to annualized volatility.
        target_vol: Target annualized portfolio volatility (e.g. 0.15 = 15%).

    Returns:
        Dict mapping ticker to portfolio fraction.
    """
    parity = risk_parity(volatilities)

    if not parity:
        return {}

    # Estimate portfolio vol under risk-parity allocation
    # (simplified: assumes zero correlation)
    tickers = list(parity.keys())
    portfolio_var = 0.0
    for t in tickers:
        w = parity[t]
        vol = volatilities.get(t, 0)
        portfolio_var += (w * vol) ** 2
    portfolio_vol = np.sqrt(portfolio_var)

    if portfolio_vol == 0:
        return parity

    # Scale to target volatility
    scale = target_vol / portfolio_vol

    # Don't allow more than 100% total allocation
    total_parity = sum(parity.values())
    max_scale = 1.0 / total_parity if total_parity > 0 else 1.0
    scale = min(scale, max_scale)

    return {t: w * scale for t, w in parity.items()}
