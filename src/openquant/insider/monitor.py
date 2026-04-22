"""Insider trading monitor for OpenQuant.

The InsiderMonitor scans recent insider trades for a ticker,
detects notable patterns, and produces an InsiderReport.

This is OpenQuant's killer feature — systematic, free insider
trading analysis with pattern detection and scoring.
"""

from __future__ import annotations

import logging
from typing import List

from openquant.data.protocol import InsiderTrade
from openquant.data.resolver import DataResolver
from openquant.insider.models import InsiderReport, InsiderScore
from openquant.insider.scorer import InsiderScorer

logger = logging.getLogger(__name__)


class InsiderMonitor:
    """Monitors insider trading activity and detects patterns.

    Usage:
        monitor = InsiderMonitor()
        report = monitor.scan("AAPL", data_resolver)
        print(report.score.label)   # "BUY"
        print(report.score.score)   # 45
        print(report.patterns)      # ["CEO purchase: ...", "Cluster buy: ..."]
        print(report.alerts)         # ["Unusual CEO buying activity detected"]
    """

    def __init__(self) -> None:
        self._scorer = InsiderScorer()

    def scan(self, ticker: str, data: DataResolver) -> InsiderReport:
        """Scan a ticker for insider trading patterns.

        Args:
            ticker: Stock ticker symbol.
            data: DataResolver for fetching insider trade data.

        Returns:
            InsiderReport with score, patterns, trades, and alerts.
        """
        # Fetch recent insider trades (last 90 days by default)
        try:
            trades = data.get_insider_trades(ticker, days=90)
        except Exception as exc:
            logger.warning("InsiderMonitor: failed to fetch trades for %s: %s", ticker, exc)
            trades = []

        if not trades:
            return InsiderReport(
                ticker=ticker,
                score=InsiderScore(
                    ticker=ticker,
                    score=0,
                    label="NEUTRAL",
                    patterns=["no_recent_trades"],
                    trades=[],
                ),
                recent_trades=[],
                alerts=["No insider trades in the last 90 days"],
            )

        # Score the trades
        score = self._scorer.score(ticker, trades)

        # Generate alerts based on score and patterns
        alerts = self._generate_alerts(score, trades)

        return InsiderReport(
            ticker=ticker,
            score=score,
            recent_trades=trades,
            alerts=alerts,
        )

    def _generate_alerts(self, score: InsiderScore, trades: List[InsiderTrade]) -> List[str]:
        """Generate actionable alerts from the insider score and patterns."""
        alerts: List[str] = []

        # High-conviction alerts
        if score.score >= 60:
            alerts.append("STRONG insider buying signal — multiple high-conviction purchases detected")
        elif score.score >= 25:
            alerts.append("Moderate insider buying signal — insiders are accumulating")

        if score.score <= -60:
            alerts.append("STRONG insider selling signal — multiple high-conviction sales detected")
        elif score.score <= -25:
            alerts.append("Moderate insider selling signal — insiders are reducing positions")

        # Pattern-specific alerts
        for pattern in score.patterns:
            p = pattern.lower()
            if "ceo purchase" in p:
                alerts.append("CEO is buying — highest-conviction insider signal")
            if "ceo sale" in p:
                alerts.append("CEO is selling — potential red flag")
            if "cluster buy" in p:
                alerts.append("Multiple insiders buying simultaneously — strong coordinated signal")
            if "cluster sell" in p:
                alerts.append("Multiple insiders selling simultaneously — potential coordinated exit")
            if "large purchase" in p:
                alerts.append("Unusually large insider purchase detected")

        # Remove duplicates while preserving order
        seen = set()
        unique_alerts = []
        for a in alerts:
            if a not in seen:
                seen.add(a)
                unique_alerts.append(a)

        return unique_alerts
