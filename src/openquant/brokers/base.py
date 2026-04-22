"""Base broker protocol for OpenQuant.

Defines the BaseBroker protocol that all broker integrations must implement.
This enables pluggable execution backends: paper, Alpaca, Kalshi, or custom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Protocol, runtime_checkable


class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """Order execution status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Position:
    """A position held at a broker.

    Attributes:
        ticker: Stock ticker or contract symbol.
        shares: Number of shares or contracts.
        avg_price: Average entry price.
        current_price: Current market price.
        market_value: Current market value.
        unrealized_pnl: Unrealized profit/loss.
        side: "long" or "short".
    """
    ticker: str
    shares: float
    avg_price: float
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    side: str = "long"

    def __post_init__(self) -> None:
        if not self.market_value:
            self.market_value = self.shares * self.current_price
        if not self.unrealized_pnl:
            self.unrealized_pnl = (self.current_price - self.avg_price) * self.shares


@dataclass
class OrderResult:
    """Result of an order placement.

    Attributes:
        success: Whether the order was accepted.
        order_id: Unique order identifier from the broker.
        ticker: Stock ticker or contract symbol.
        action: "BUY" or "SELL".
        quantity: Number of shares or contracts.
        price: Execution price (filled price for market orders).
        order_type: Type of order placed.
        status: Current status of the order.
        timestamp: When the order was placed.
        message: Human-readable result or error message.
    """
    success: bool
    order_id: str = ""
    ticker: str = ""
    action: str = ""
    quantity: float = 0.0
    price: float = 0.0
    order_type: str = "market"
    status: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""


@runtime_checkable
class BaseBroker(Protocol):
    """Protocol for broker integrations.

    All brokers must implement these methods. This enables swapping
    execution backends without changing the strategy layer.
    """

    @property
    def name(self) -> str:
        """Human-readable name of this broker."""
        ...

    @property
    def mode(self) -> str:
        """Execution mode: 'game', 'signal', or 'live'."""
        ...

    def get_balance(self) -> float:
        """Get current account balance (cash available)."""
        ...

    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        ...

    def place_order(
        self,
        ticker: str,
        action: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> OrderResult:
        """Place an order.

        Args:
            ticker: Stock ticker or contract symbol.
            action: "BUY" or "SELL".
            quantity: Number of shares or contracts.
            order_type: "market", "limit", "stop", or "stop_limit".
            limit_price: Limit price (for limit/stop_limit orders).
            stop_price: Stop price (for stop/stop_limit orders).

        Returns:
            OrderResult with order details.
        """
        ...

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order.

        Args:
            order_id: The order to cancel.

        Returns:
            True if cancellation succeeded.
        """
        ...

    def get_order_status(self, order_id: str) -> OrderStatus:
        """Get the current status of an order.

        Args:
            order_id: The order to check.

        Returns:
            OrderStatus enum value.
        """
        ...
