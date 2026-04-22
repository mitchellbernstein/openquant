"""Base strategy classes for OpenQuant.

All trading strategies inherit from BaseStrategy and return StrategyResult.
Strategies combine agent signals, risk assessment, and position sizing
into actionable trade decisions.

No LLM required -- all logic is purely quantitative.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from openquant.agents.base import SignalResult
from openquant.risk.models import RiskReport


@dataclass
class BacktestResult:
    """Result of a strategy backtest.

    Attributes:
        strategy_name: Name of the strategy that was backtested.
        ticker: Ticker symbol.
        total_trades: Number of trades executed during backtest.
        win_rate: Fraction of profitable trades (0 to 1).
        total_return: Cumulative return as a fraction (e.g. 0.15 = 15%).
        max_drawdown: Maximum drawdown as a fraction.
        sharpe_ratio: Annualized Sharpe ratio.
        avg_holding_days: Average holding period in trading days.
        trades: List of individual trade records from the backtest.
    """
    strategy_name: str
    ticker: str
    total_trades: int
    win_rate: float
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    avg_holding_days: float
    trades: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        """Generate a human-readable backtest summary."""
        lines = [
            f"Backtest: {self.strategy_name} on {self.ticker}",
            f"  Total Trades: {self.total_trades}",
            f"  Win Rate: {self.win_rate:.1%}",
            f"  Total Return: {self.total_return:.1%}",
            f"  Max Drawdown: {self.max_drawdown:.1%}",
            f"  Sharpe Ratio: {self.sharpe_ratio:.2f}",
            f"  Avg Holding: {self.avg_holding_days:.1f} days",
        ]
        return "\n".join(lines)


@dataclass
class StrategyResult:
    """Result produced by a trading strategy.

    Attributes:
        strategy_name: Identifier of the strategy that produced this result.
        ticker: Stock ticker symbol.
        action: Recommended action: "BUY", "SELL", or "HOLD".
        confidence: Confidence level from 0 to 100.
        entry_price: Suggested entry price.
        stop_loss: Stop loss price.
        take_profit: Take profit price.
        position_size_pct: Recommended position size as fraction of portfolio (0 to 1).
        reasoning: Human-readable explanation of the strategy decision.
        signals: Agent signals that contributed to this decision.
        risk_report: Optional risk assessment for this position.
    """
    strategy_name: str
    ticker: str
    action: str  # "BUY", "SELL", "HOLD"
    confidence: int  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_pct: float  # fraction of portfolio
    reasoning: str
    signals: List[SignalResult] = field(default_factory=list)
    risk_report: Optional[RiskReport] = None

    def __post_init__(self) -> None:
        # Clamp confidence to [0, 100]
        self.confidence = max(0, min(100, self.confidence))
        # Validate action
        valid_actions = {"BUY", "SELL", "HOLD"}
        if self.action not in valid_actions:
            raise ValueError(f"Invalid action: {self.action!r}. Must be one of {valid_actions}")
        # Clamp position size
        self.position_size_pct = max(0.0, min(1.0, self.position_size_pct))

    def summary(self) -> str:
        """Generate a human-readable strategy result summary."""
        lines = [
            f"Strategy: {self.strategy_name} | {self.ticker}",
            f"  Action: {self.action} (confidence: {self.confidence}/100)",
            f"  Entry: ${self.entry_price:.2f} | Stop: ${self.stop_loss:.2f} | Target: ${self.take_profit:.2f}",
            f"  Position Size: {self.position_size_pct:.1%} of portfolio",
            f"  Reasoning: {self.reasoning}",
        ]
        if self.signals:
            lines.append(f"  Signals: {', '.join(f'{s.agent_name}={s.direction}' for s in self.signals)}")
        if self.risk_report:
            lines.append(f"  Risk Level: {self.risk_report.risk_level}")
        return "\n".join(lines)


class BaseStrategy(ABC):
    """Abstract base class for all OpenQuant trading strategies.

    Subclasses must implement `generate_signal()`. Each strategy combines
    multiple agent signals, applies its own entry/exit rules, and produces
    a StrategyResult with a clear action, position size, and risk parameters.

    No LLM is used -- all analysis is purely quantitative.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def generate_signal(self, ticker: str, data) -> StrategyResult:
        """Generate a trading signal for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL").
            data: DataResolver for fetching market data.

        Returns:
            StrategyResult with the strategy's recommendation.
        """
        ...

    def backtest(self, ticker: str, data, days: int = 252) -> BacktestResult:
        """Default backtest using the signal over historical data.

        Steps through the last `days` of price data, generating signals
        at each point and tracking the resulting trades.

        Args:
            ticker: Stock ticker symbol.
            data: DataResolver for fetching market data.
            days: Number of calendar days to backtest.

        Returns:
            BacktestResult with performance metrics.
        """
        from datetime import date, timedelta

        end = date.today()
        start = end - timedelta(days=int(days * 1.5))
        prices = data.get_prices(ticker, start, end)

        if not prices or len(prices) < 20:
            return BacktestResult(
                strategy_name=self.name,
                ticker=ticker,
                total_trades=0,
                win_rate=0.0,
                total_return=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                avg_holding_days=0.0,
            )

        # Simple backtest: simulate signals at each price point
        # and track results based on stop/target
        trades: List[Dict[str, Any]] = []
        position = None  # {entry_price, stop_loss, take_profit, entry_idx}

        for i, price in enumerate(prices):
            current_price = price.close

            if position is not None:
                # Check exit conditions
                if current_price <= position["stop_loss"]:
                    pnl = (current_price - position["entry_price"]) / position["entry_price"]
                    trades.append({
                        "entry_price": position["entry_price"],
                        "exit_price": current_price,
                        "pnl": pnl,
                        "exit_reason": "stop_loss",
                        "holding_days": i - position["entry_idx"],
                    })
                    position = None
                elif current_price >= position["take_profit"]:
                    pnl = (current_price - position["entry_price"]) / position["entry_price"]
                    trades.append({
                        "entry_price": position["entry_price"],
                        "exit_price": current_price,
                        "pnl": pnl,
                        "exit_reason": "take_profit",
                        "holding_days": i - position["entry_idx"],
                    })
                    position = None
                elif i - position["entry_idx"] >= 30:
                    # Time stop
                    pnl = (current_price - position["entry_price"]) / position["entry_price"]
                    trades.append({
                        "entry_price": position["entry_price"],
                        "exit_price": current_price,
                        "pnl": pnl,
                        "exit_reason": "time_stop",
                        "holding_days": i - position["entry_idx"],
                    })
                    position = None
            else:
                # Only generate signal every 5 bars to reduce noise
                if i % 5 == 0 and i >= 20:
                    try:
                        signal = self.generate_signal(ticker, data)
                        if signal.action == "BUY" and signal.confidence >= 40:
                            position = {
                                "entry_price": current_price,
                                "stop_loss": signal.stop_loss,
                                "take_profit": signal.take_profit,
                                "entry_idx": i,
                            }
                    except Exception:
                        pass  # Skip failed signal generations in backtest

        # Close any open position at end
        if position is not None and prices:
            current_price = prices[-1].close
            pnl = (current_price - position["entry_price"]) / position["entry_price"]
            trades.append({
                "entry_price": position["entry_price"],
                "exit_price": current_price,
                "pnl": pnl,
                "exit_reason": "end_of_data",
                "holding_days": len(prices) - 1 - position["entry_idx"],
            })

        # Compute metrics
        total_trades = len(trades)
        if total_trades == 0:
            return BacktestResult(
                strategy_name=self.name,
                ticker=ticker,
                total_trades=0,
                win_rate=0.0,
                total_return=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                avg_holding_days=0.0,
            )

        wins = [t for t in trades if t["pnl"] > 0]
        win_rate = len(wins) / total_trades

        # Total return (compounded)
        cumulative = 1.0
        peak = 1.0
        max_dd = 0.0
        for t in trades:
            cumulative *= (1 + t["pnl"])
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak
            if dd > max_dd:
                max_dd = dd

        total_return = cumulative - 1.0

        # Sharpe ratio (simplified)
        import numpy as np
        pnls = np.array([t["pnl"] for t in trades])
        if len(pnls) > 1 and np.std(pnls) > 0:
            sharpe = float(np.mean(pnls) / np.std(pnls) * np.sqrt(252))
        else:
            sharpe = 0.0

        avg_holding = float(np.mean([t["holding_days"] for t in trades]))

        return BacktestResult(
            strategy_name=self.name,
            ticker=ticker,
            total_trades=total_trades,
            win_rate=win_rate,
            total_return=total_return,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            avg_holding_days=avg_holding,
            trades=trades,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
