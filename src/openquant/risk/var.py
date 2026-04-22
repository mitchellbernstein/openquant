"""Value at Risk (VaR) calculations for OpenQuant.

Implements two VaR methodologies:
  - Parametric (variance-covariance): assumes normal distribution
  - Historical simulation: non-parametric, uses actual return distribution

Both return VaR as a positive fraction representing potential loss
(e.g. 0.05 means 5% of portfolio value at risk).

Uses pure numpy — no scipy dependency.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VaRResult:
    """Value at Risk calculation result.

    Attributes:
        var_pct: VaR as a percentage (e.g. 0.05 means 5%).
        var_dollar: VaR in dollar terms (based on portfolio_value).
        confidence: Confidence level used (e.g. 0.95).
        method: Method used for calculation.
        mean_return: Mean of the return distribution.
        std_return: Standard deviation of the return distribution.
    """

    var_pct: float
    var_dollar: float
    confidence: float
    method: str
    mean_return: float = 0.0
    std_return: float = 0.0

    def __repr__(self) -> str:
        return (
            f"VaRResult(method={self.method!r}, confidence={self.confidence:.0%}, "
            f"var={self.var_pct:.2%}, var_dollar=${self.var_dollar:,.2f})"
        )


# ── Standard normal quantile (inverse CDF) ──────────────────────────
# Rational approximation for the normal inverse CDF (Abramowitz & Stegun)
# Avoids scipy dependency.

_NORM_PPF_COEFFS = [
    -3.969683028665376e+01,
     2.209460984245205e+02,
    -2.759285104469687e+02,
     1.383577518672690e+02,
    -3.066479806614716e+01,
     2.506628277459239e+00,
]

_NORM_PPF_COEFFS2 = [
    -5.447609779154151e+01,
     1.615858368580409e+02,
    -1.556989798598866e+02,
     6.680131188771972e+01,
    -1.328068155288572e+01,
]

_NORM_PPF_COEFFS3 = [
    7.784695709041462e-03,
    -3.223964580411365e-01,
    -2.400758277058598e+00,
    -2.549732539343734e+00,
     4.374664141464968e+00,
     2.938163982698783e+00,
]

_NORM_PPF_COEFFS4 = [
     7.784695709041462e-03,
     3.224671290700398e-01,
     2.445134137142996e+00,
     3.754408661907416e+00,
]


def _norm_ppf(p: float) -> float:
    """Inverse of the standard normal CDF (percent-point function).

    Rational approximation from Abramowitz & Stegun, implemented in
    many libraries. Accuracy ~1e-9.

    Args:
        p: Probability value (0 < p < 1).

    Returns:
        Z-score corresponding to the given probability.
    """
    if p <= 0:
        return float("-inf")
    if p >= 1:
        return float("inf")

    a = _NORM_PPF_COEFFS
    b = _NORM_PPF_COEFFS2
    c = _NORM_PPF_COEFFS3
    d = _NORM_PPF_COEFFS4

    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        numer = ((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]
        denom = (((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1
        x = numer / denom
    elif p > 0.97575:
        q = math.sqrt(-2 * math.log(1 - p))
        numer = ((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]
        denom = (((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1
        x = -numer / denom
    else:
        q = p - 0.5
        r = q * q
        numer = ((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]
        numer *= q
        denom = (((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4]
        denom = denom * r + 1
        x = numer / denom

    return x


def parametric_var(
    returns: np.ndarray,
    confidence: float = 0.95,
    portfolio_value: float = 100_000.0,
) -> VaRResult:
    """Calculate VaR using the variance-covariance (parametric) method.

    Assumes returns are normally distributed. This is the simplest VaR
    model — fast to compute but can underestimate tail risk.

    Args:
        returns: Array of periodic returns (e.g. daily log returns).
        confidence: Confidence level (0.95 or 0.99).
        portfolio_value: Total portfolio value in dollars.

    Returns:
        VaRResult with the calculated VaR.
    """
    if len(returns) < 2:
        return VaRResult(
            var_pct=0.0,
            var_dollar=0.0,
            confidence=confidence,
            method="parametric",
        )

    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1))

    if std == 0:
        return VaRResult(
            var_pct=0.0,
            var_dollar=0.0,
            confidence=confidence,
            method="parametric",
            mean_return=mean,
            std_return=std,
        )

    # Z-score for the confidence level (one-tailed)
    z = _norm_ppf(1 - confidence)

    # VaR = -(mean + z * std)
    # This gives the maximum loss at the given confidence level
    var_pct = -(mean + z * std)
    var_pct = max(var_pct, 0.0)  # VaR is expressed as a positive loss

    var_dollar = var_pct * portfolio_value

    return VaRResult(
        var_pct=var_pct,
        var_dollar=var_dollar,
        confidence=confidence,
        method="parametric",
        mean_return=mean,
        std_return=std,
    )


def historical_var(
    returns: np.ndarray,
    confidence: float = 0.95,
    portfolio_value: float = 100_000.0,
) -> VaRResult:
    """Calculate VaR using historical simulation.

    Non-parametric method — uses the actual return distribution.
    More robust to non-normal distributions but requires sufficient
    history (at least 252 observations recommended).

    Args:
        returns: Array of periodic returns (e.g. daily log returns).
        confidence: Confidence level (0.95 or 0.99).
        portfolio_value: Total portfolio value in dollars.

    Returns:
        VaRResult with the calculated VaR.
    """
    if len(returns) < 10:
        return VaRResult(
            var_pct=0.0,
            var_dollar=0.0,
            confidence=confidence,
            method="historical",
        )

    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1))

    # Sort returns ascending (worst first)
    sorted_returns = np.sort(returns)

    # Find the return at the (1 - confidence) quantile
    # e.g. at 95% confidence, look at the 5th percentile
    index = int((1 - confidence) * len(sorted_returns))
    index = max(0, min(index, len(sorted_returns) - 1))

    # VaR is the loss at that percentile (positive number)
    var_pct = -sorted_returns[index]
    var_pct = max(var_pct, 0.0)

    var_dollar = var_pct * portfolio_value

    return VaRResult(
        var_pct=var_pct,
        var_dollar=var_dollar,
        confidence=confidence,
        method="historical",
        mean_return=mean,
        std_return=std,
    )


def conditional_var(
    returns: np.ndarray,
    confidence: float = 0.95,
    portfolio_value: float = 100_000.0,
) -> VaRResult:
    """Calculate Conditional VaR (Expected Shortfall / CVaR).

    The average loss when the loss exceeds VaR. This captures tail risk
    better than standard VaR.

    Args:
        returns: Array of periodic returns.
        confidence: Confidence level.
        portfolio_value: Total portfolio value in dollars.

    Returns:
        VaRResult with the Conditional VaR.
    """
    if len(returns) < 10:
        return VaRResult(
            var_pct=0.0,
            var_dollar=0.0,
            confidence=confidence,
            method="conditional",
        )

    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1))

    # Sort returns ascending
    sorted_returns = np.sort(returns)

    # Find all returns below the VaR threshold
    index = int((1 - confidence) * len(sorted_returns))
    index = max(0, min(index, len(sorted_returns) - 1))

    tail_returns = sorted_returns[: index + 1]

    if len(tail_returns) == 0:
        cvar_pct = 0.0
    else:
        cvar_pct = -float(np.mean(tail_returns))

    cvar_pct = max(cvar_pct, 0.0)
    cvar_dollar = cvar_pct * portfolio_value

    return VaRResult(
        var_pct=cvar_pct,
        var_dollar=cvar_dollar,
        confidence=confidence,
        method="conditional",
        mean_return=mean,
        std_return=std,
    )
