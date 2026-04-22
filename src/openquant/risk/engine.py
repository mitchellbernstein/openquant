"""Risk engine for OpenQuant.

The RiskEngine orchestrates all risk calculations:
  - Value at Risk (parametric + historical)
  - Maximum drawdown
  - Position sizing (Kelly, risk parity)
  - Correlation analysis
  - Risk warnings and recommendations

All analysis is purely quantitative — no LLM needed.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np

from openquant.data.resolver import DataResolver
from openquant.risk.models import RiskReport
from openquant.risk.var import parametric_var, historical_var
from openquant.risk.sizing import half_kelly, risk_parity

logger = logging.getLogger(__name__)


class RiskEngine:
    """Portfolio risk assessment engine.

    Usage:
        engine = RiskEngine()
        report = engine.assess(["AAPL", "MSFT", "GOOGL"], data_resolver)
        print(report.summary())
    """

    # Default lookback period for risk calculations
    LOOKBACK_DAYS = 252  # 1 year of trading days

    def assess(
        self,
        tickers: List[str],
        data: DataResolver,
        portfolio_value: float = 100_000.0,
        lookback_days: int = 252,
    ) -> RiskReport:
        """Assess portfolio risk for a list of tickers.

        Args:
            tickers: List of stock ticker symbols.
            data: DataResolver for fetching price data.
            portfolio_value: Total portfolio value in dollars.
            lookback_days: Number of calendar days to look back.

        Returns:
            RiskReport with all risk metrics.
        """
        warnings: List[str] = []
        recommendations: List[str] = []

        # ── 1. Fetch price data ────────────────────────────────────
        end = date.today()
        start = end - timedelta(days=int(lookback_days * 1.5))  # Extra buffer for weekends/holidays

        price_arrays: Dict[str, np.ndarray] = {}
        for ticker in tickers:
            try:
                prices = data.get_prices(ticker, start, end)
                if prices and len(prices) >= 20:
                    closes = np.array([p.close for p in prices], dtype=float)
                    price_arrays[ticker] = closes
                else:
                    warnings.append(f"Insufficient price data for {ticker}")
            except Exception as exc:
                warnings.append(f"Failed to fetch prices for {ticker}: {exc}")

        # ── 2. Compute returns ─────────────────────────────────────
        return_arrays: Dict[str, np.ndarray] = {}
        for ticker, closes in price_arrays.items():
            returns = np.diff(np.log(closes))
            return_arrays[ticker] = returns

        # ── 3. Portfolio returns (equal-weight for simplicity) ─────
        if return_arrays:
            # Align returns to same length
            min_len = min(len(r) for r in return_arrays.values())
            if min_len > 0:
                aligned = np.column_stack([
                    r[-min_len:] for r in return_arrays.values()
                ])
                portfolio_returns = np.mean(aligned, axis=1)
            else:
                portfolio_returns = np.array([])
        else:
            portfolio_returns = np.array([])

        # ── 4. Value at Risk ───────────────────────────────────────
        if len(portfolio_returns) >= 20:
            var_95_result = parametric_var(portfolio_returns, 0.95, portfolio_value)
            var_99_result = parametric_var(portfolio_returns, 0.99, portfolio_value)
            var_95 = var_95_result.var_pct
            var_99 = var_99_result.var_pct
        else:
            var_95 = 0.0
            var_99 = 0.0
            warnings.append("Insufficient data for VaR calculation")

        # ── 5. Maximum drawdown ────────────────────────────────────
        max_dd = 0.0
        if len(portfolio_returns) >= 20:
            cumulative = np.cumprod(1 + portfolio_returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_dd = float(-np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

        # ── 6. Kelly fraction ──────────────────────────────────────
        if len(portfolio_returns) >= 20:
            positive = portfolio_returns[portfolio_returns > 0]
            negative = portfolio_returns[portfolio_returns < 0]
            win_rate = len(positive) / len(portfolio_returns) if len(portfolio_returns) > 0 else 0
            avg_win = float(np.mean(positive)) if len(positive) > 0 else 0
            avg_loss = float(abs(np.mean(negative))) if len(negative) > 0 else 0.01
            kelly = half_kelly(win_rate, avg_win, avg_loss)
        else:
            kelly = 0.0
            warnings.append("Insufficient data for Kelly criterion")

        # ── 7. Position sizing (risk parity) ───────────────────────
        volatilities: Dict[str, float] = {}
        for ticker, returns in return_arrays.items():
            if len(returns) >= 20:
                # Annualize daily volatility
                volatilities[ticker] = float(np.std(returns, ddof=1) * np.sqrt(252))
            else:
                volatilities[ticker] = 0.30  # Default assumption

        position_sizes = risk_parity(volatilities)

        # ── 8. Correlation matrix ──────────────────────────────────
        correlations: Dict[str, Dict[str, float]] = {}
        tickers_with_data = list(return_arrays.keys())
        if len(tickers_with_data) >= 2:
            min_len = min(len(return_arrays[t]) for t in tickers_with_data)
            if min_len >= 20:
                aligned_matrix = np.column_stack([
                    return_arrays[t][-min_len:] for t in tickers_with_data
                ])
                corr_matrix = np.corrcoef(aligned_matrix, rowvar=False)
                for i, t1 in enumerate(tickers_with_data):
                    correlations[t1] = {}
                    for j, t2 in enumerate(tickers_with_data):
                        correlations[t1][t2] = float(corr_matrix[i][j])
        else:
            for t in tickers_with_data:
                correlations[t] = {t: 1.0}

        # ── 9. Generate warnings and recommendations ───────────────
        if max_dd > 0.30:
            warnings.append(f"High historical drawdown: {max_dd:.1%}")
            recommendations.append("Consider reducing position sizes or adding hedges")

        if var_95 > 0.05:
            warnings.append(f"Daily VaR(95%) is {var_95:.1%} — significant risk")
            recommendations.append("Set stop-losses at VaR level or tighter")

        # Check for high correlations (concentration risk)
        for t1 in correlations:
            for t2 in correlations:
                if t1 < t2:  # Avoid duplicates
                    corr = correlations[t1].get(t2, 0)
                    if abs(corr) > 0.8:
                        warnings.append(f"High correlation between {t1} and {t2}: {corr:.2f}")
                        recommendations.append(
                            f"Diversify by reducing overlap between {t1} and {t2}"
                        )

        # Check for individual concentration
        for ticker, size in position_sizes.items():
            if size > 0.5:
                warnings.append(f"High concentration in {ticker}: {size:.1%}")
                recommendations.append(f"Reduce {ticker} position to below 40% of portfolio")

        if kelly > 0.25:
            recommendations.append(f"Half-Kelly suggests maximum {kelly:.1%} allocation")
        elif kelly <= 0:
            recommendations.append("Kelly criterion suggests no position — consider staying flat")

        return RiskReport(
            tickers=tickers,
            var_95=var_95,
            var_99=var_99,
            max_drawdown=max_dd,
            kelly_fraction=kelly,
            position_sizes=position_sizes,
            correlations=correlations,
            warnings=warnings,
            recommendations=recommendations,
        )
