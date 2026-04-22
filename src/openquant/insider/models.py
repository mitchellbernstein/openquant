"""Insider trading data models for OpenQuant.

Defines InsiderScore and InsiderReport — the core data structures
for the insider trading monitor. These are used by both the
InsiderMonitor and the InsiderAgent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from openquant.data.protocol import InsiderTrade


@dataclass
class InsiderScore:
    """Insider sentiment score for a single ticker.

    Attributes:
        ticker: Stock ticker symbol.
        score: Sentiment score from -100 (strong sell) to +100 (strong buy).
        label: Human-readable sentiment label.
        patterns: List of detected trading patterns.
        trades: Insider trades that were analyzed.
    """

    ticker: str
    score: int  # -100 to +100
    label: str  # "STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"
    patterns: List[str] = field(default_factory=list)
    trades: List[InsiderTrade] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Clamp score to [-100, 100]
        self.score = max(-100, min(100, self.score))

    @staticmethod
    def score_to_label(score: int) -> str:
        """Convert a numeric score to a human-readable label."""
        if score >= 60:
            return "STRONG BUY"
        elif score >= 25:
            return "BUY"
        elif score > -25:
            return "NEUTRAL"
        elif score > -60:
            return "SELL"
        else:
            return "STRONG SELL"


@dataclass
class InsiderReport:
    """Full insider trading analysis report for a ticker.

    Attributes:
        ticker: Stock ticker symbol.
        score: Computed insider sentiment score.
        recent_trades: List of recent insider trades.
        alerts: Actionable alerts from pattern detection.
    """

    ticker: str
    score: InsiderScore
    recent_trades: List[InsiderTrade] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
