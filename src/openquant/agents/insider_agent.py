"""Insider trading analysis agent — OpenQuant's killer feature.

Evaluates stocks based on insider trading patterns. This is the unique
differentiator — no other open-source quant framework provides built-in
insider trading pattern detection and scoring.

Uses the InsiderMonitor and InsiderScorer from openquant.insider to
detect patterns like cluster buys, CEO/CFO activity, and unusual trade sizes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from openquant.agents.base import BaseAgent, SignalResult
from openquant.data.resolver import DataResolver
from openquant.insider.monitor import InsiderMonitor
from openquant.insider.models import InsiderReport

logger = logging.getLogger(__name__)


class InsiderAgent(BaseAgent):
    """Analyzes stocks using insider trading patterns.

    Delegates to InsiderMonitor for pattern detection and scoring.
    Converts the insider sentiment score (-100 to +100) into a
    normalized signal (-1.0 to +1.0).

    This is OpenQuant's signature feature — systematic insider
    trading analysis available to every user at no cost.
    """

    name = "insider"
    description = "Insider trading agent — cluster buys, CEO activity, unusual size detection"

    def __init__(self) -> None:
        self._monitor = InsiderMonitor()

    def analyze(self, ticker: str, data: DataResolver) -> SignalResult:
        metrics: Dict[str, Any] = {}
        reasons: list[str] = []

        try:
            report = self._monitor.scan(ticker, data)
        except Exception as exc:
            logger.warning("InsiderAgent: scan failed for %s: %s", ticker, exc)
            return SignalResult(
                agent_name=self.name,
                ticker=ticker,
                signal=0.0,
                confidence=0,
                reasoning=f"Insider data unavailable: {exc}",
                data=metrics,
            )

        # ── Extract score and convert to signal ────────────────────
        score = report.score.score  # -100 to +100
        # Normalize to [-1.0, +1.0]
        signal = round(score / 100.0, 3)

        metrics["insider_score"] = score
        metrics["insider_label"] = report.score.label
        metrics["patterns_detected"] = report.score.patterns
        metrics["recent_trades_count"] = len(report.recent_trades)
        metrics["alerts"] = report.alerts

        # ── Build reasoning ────────────────────────────────────────
        if report.score.patterns:
            reasons.append(f"Patterns: {', '.join(report.score.patterns)}")
        if report.alerts:
            reasons.append(f"Alerts: {', '.join(report.alerts)}")
        reasons.append(f"Insider sentiment: {report.score.label} (score {score})")

        # Confidence based on number of recent trades and pattern clarity
        trade_count = len(report.recent_trades)
        if trade_count == 0:
            confidence = 5  # Very low — no data
        elif trade_count < 3:
            confidence = 25
        elif trade_count < 10:
            confidence = 50
        else:
            confidence = 70

        # Boost confidence when patterns are detected
        if report.score.patterns:
            confidence = min(90, confidence + 15)

        return SignalResult(
            agent_name=self.name,
            ticker=ticker,
            signal=signal,
            confidence=confidence,
            reasoning="; ".join(reasons),
            data=metrics,
        )
