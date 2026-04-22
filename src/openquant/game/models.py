"""Game mode data models for OpenQuant.

Defines TradeResult, PortfolioStatus, and Achievement dataclasses
used by the GameEngine for paper trading with gamification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class TradeResult:
    """Result of a trade execution in game mode.

    Attributes:
        success: Whether the trade was executed successfully.
        ticker: Stock ticker symbol.
        action: "BUY" or "SELL".
        shares: Number of shares traded.
        price: Execution price per share.
        total_cost: Total cost of the trade (shares * price).
        timestamp: When the trade was executed.
        message: Human-readable result message.
        new_balance: Account balance after the trade.
        position_shares: Number of shares held after the trade.
    """
    success: bool
    ticker: str
    action: str
    shares: float
    price: float
    total_cost: float
    timestamp: datetime
    message: str
    new_balance: float = 0.0
    position_shares: float = 0.0

    def summary(self) -> str:
        """Generate a human-readable trade summary."""
        status = "FILLED" if self.success else "REJECTED"
        return (
            f"[{status}] {self.action} {self.shares:.2f} {self.ticker} "
            f"@ ${self.price:.2f} = ${self.total_cost:.2f} | "
            f"Balance: ${self.new_balance:.2f}"
        )


@dataclass
class Position:
    """A single position in the portfolio.

    Attributes:
        ticker: Stock ticker symbol.
        shares: Number of shares held.
        avg_price: Average purchase price.
        current_price: Latest market price.
        cost_basis: Total cost of the position (shares * avg_price).
        market_value: Current market value (shares * current_price).
        unrealized_pnl: Unrealized profit/loss in dollars.
        unrealized_pnl_pct: Unrealized profit/loss as a percentage.
        held_since: When the position was first opened.
    """
    ticker: str
    shares: float
    avg_price: float
    current_price: float = 0.0
    held_since: Optional[datetime] = None

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_price

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100

    def summary(self) -> str:
        """Generate a human-readable position summary."""
        pnl_sign = "+" if self.unrealized_pnl >= 0 else ""
        return (
            f"{self.ticker}: {self.shares:.2f} shares @ ${self.avg_price:.2f} "
            f"| Value: ${self.market_value:.2f} "
            f"| P/L: {pnl_sign}${self.unrealized_pnl:.2f} ({pnl_sign}{self.unrealized_pnl_pct:.1f}%)"
        )


@dataclass
class PortfolioStatus:
    """Current state of the game portfolio.

    Attributes:
        balance: Cash balance.
        positions: Dict of ticker -> Position.
        total_value: Total portfolio value (cash + positions).
        total_pnl: Total profit/loss from starting balance.
        total_pnl_pct: Total P/L as a percentage.
        trade_count: Number of trades executed.
        win_count: Number of winning trades.
        loss_count: Number of losing trades.
        achievements: List of unlocked achievement names.
    """
    balance: float
    positions: Dict[str, Position] = field(default_factory=dict)
    total_value: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    achievements: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Calculate derived values
        position_value = sum(p.market_value for p in self.positions.values())
        self.total_value = self.balance + position_value

    def summary(self) -> str:
        """Generate a human-readable portfolio summary."""
        lines = [
            f"Portfolio Value: ${self.total_value:,.2f} | Cash: ${self.balance:,.2f}",
            f"P/L: {'+' if self.total_pnl >= 0 else ''}${self.total_pnl:,.2f} ({'+' if self.total_pnl_pct >= 0 else ''}{self.total_pnl_pct:.1f}%)",
            f"Trades: {self.trade_count} | Wins: {self.win_count} | Losses: {self.loss_count}",
        ]
        if self.positions:
            lines.append("Positions:")
            for pos in self.positions.values():
                lines.append(f"  {pos.summary()}")
        if self.achievements:
            lines.append(f"Achievements: {', '.join(self.achievements)}")
        return "\n".join(lines)


@dataclass
class Achievement:
    """A game achievement.

    Attributes:
        name: Unique identifier for the achievement.
        title: Human-readable title.
        description: What the achievement represents.
        icon: ASCII icon for terminal display.
        unlocked_at: When the achievement was unlocked (None if locked).
    """
    name: str
    title: str
    description: str
    icon: str = "*"
    unlocked_at: Optional[datetime] = None

    @property
    def is_unlocked(self) -> bool:
        return self.unlocked_at is not None

    def summary(self) -> str:
        """Generate a human-readable achievement summary."""
        status = f"UNLOCKED {self.unlocked_at.strftime('%Y-%m-%d %H:%M')}" if self.unlocked_at else "LOCKED"
        return f"[{self.icon}] {self.title} - {self.description} ({status})"


# ── Predefined achievements ────────────────────────────────────────────

ACHIEVEMENTS = [
    Achievement(
        name="first_trade",
        title="First Trade",
        description="Execute your first trade",
        icon=">",
    ),
    Achievement(
        name="three_day_streak",
        title="3-Day Streak",
        description="Make a trade 3 days in a row",
        icon="~",
    ),
    Achievement(
        name="five_wins",
        title="5 Wins",
        description="Close 5 profitable trades",
        icon="+",
    ),
    Achievement(
        name="ten_percent_return",
        title="10% Return",
        description="Achieve a 10% portfolio return",
        icon="^",
    ),
    Achievement(
        name="diamond_hands",
        title="Diamond Hands",
        description="Hold a position for 30+ days",
        icon="<>",
    ),
    Achievement(
        name="quick_draw",
        title="Quick Draw",
        description="Trade within 5 minutes of receiving a signal",
        icon="!",
    ),
]
