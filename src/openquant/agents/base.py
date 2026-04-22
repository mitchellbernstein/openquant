"""Base agent classes for the OpenQuant agent framework.

All analysis agents inherit from BaseAgent and return SignalResult.
Agents are pure-quantitative — no LLM required. Each agent specializes
in one dimension of analysis (value, growth, sentiment, technicals, insider).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from openquant.data.resolver import DataResolver


@dataclass
class SignalResult:
    """Result produced by an analysis agent.

    Attributes:
        agent_name: Identifier of the agent that produced this signal.
        ticker: Stock ticker symbol.
        signal: Signal strength from -1.0 (strong sell) to +1.0 (strong buy).
        confidence: Confidence level from 0 to 100.
        reasoning: Human-readable explanation of the signal.
        data: Optional dict of supporting metrics and raw values.
    """

    agent_name: str
    ticker: str
    signal: float  # -1.0 (strong sell) to +1.0 (strong buy)
    confidence: int  # 0-100
    reasoning: str
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Clamp signal to [-1.0, 1.0]
        self.signal = max(-1.0, min(1.0, self.signal))
        # Clamp confidence to [0, 100]
        self.confidence = max(0, min(100, self.confidence))

    @property
    def direction(self) -> str:
        """Human-readable signal direction."""
        if self.signal > 0.3:
            return "BULLISH"
        elif self.signal < -0.3:
            return "BEARISH"
        else:
            return "NEUTRAL"

    @property
    def strength(self) -> str:
        """Human-readable signal strength."""
        abs_signal = abs(self.signal)
        if abs_signal > 0.7:
            return "STRONG"
        elif abs_signal > 0.4:
            return "MODERATE"
        else:
            return "WEAK"


class BaseAgent(ABC):
    """Abstract base class for all OpenQuant analysis agents.

    Subclasses must implement `analyze()`. Each agent focuses on one
    dimension of stock analysis and returns a SignalResult with a
    quantitative signal, confidence, and reasoning.

    No LLM is used — all analysis is purely quantitative.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def analyze(self, ticker: str, data: DataResolver) -> SignalResult:
        """Analyze a ticker and return a signal.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL").
            data: DataResolver for fetching market data.

        Returns:
            SignalResult with the agent's analysis.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
