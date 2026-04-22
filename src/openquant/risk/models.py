"""Risk report models for OpenQuant.

Defines the RiskReport dataclass used by the RiskEngine
to communicate portfolio risk metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RiskReport:
    """Portfolio risk assessment report.

    Attributes:
        tickers: List of tickers in the portfolio.
        var_95: Value at Risk at 95% confidence (as a fraction, e.g. 0.05 = 5%).
        var_99: Value at Risk at 99% confidence (as a fraction).
        max_drawdown: Maximum drawdown over the analysis period (as a fraction).
        kelly_fraction: Kelly criterion optimal fraction (0 to 1).
        position_sizes: Recommended position sizes per ticker (fraction of portfolio).
        correlations: Pairwise correlation matrix between tickers.
        warnings: Risk warnings identified during assessment.
        recommendations: Actionable risk management recommendations.
    """

    tickers: List[str]
    var_95: float  # Value at Risk at 95%
    var_99: float  # Value at Risk at 99%
    max_drawdown: float
    kelly_fraction: float
    position_sizes: Dict[str, float] = field(default_factory=dict)
    correlations: Dict[str, Dict[str, float]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    @property
    def risk_level(self) -> str:
        """Human-readable risk level based on VaR and drawdown."""
        max_risk = max(abs(self.var_95), abs(self.max_drawdown))
        if max_risk > 0.20:
            return "HIGH"
        elif max_risk > 0.10:
            return "MODERATE"
        elif max_risk > 0.05:
            return "LOW"
        else:
            return "VERY LOW"

    def summary(self) -> str:
        """Generate a human-readable summary of the risk report."""
        lines = [
            f"Risk Report: {', '.join(self.tickers)}",
            f"  Risk Level: {self.risk_level}",
            f"  VaR (95%): {self.var_95:.2%}",
            f"  VaR (99%): {self.var_99:.2%}",
            f"  Max Drawdown: {self.max_drawdown:.2%}",
            f"  Kelly Fraction: {self.kelly_fraction:.2%}",
        ]
        if self.position_sizes:
            sizes = ", ".join(f"{t}: {s:.1%}" for t, s in self.position_sizes.items())
            lines.append(f"  Position Sizes: {sizes}")
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        if self.recommendations:
            lines.append("  Recommendations:")
            for r in self.recommendations:
                lines.append(f"    - {r}")
        return "\n".join(lines)
