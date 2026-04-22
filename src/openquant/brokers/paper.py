"""Paper trading broker for OpenQuant.

In-memory paper trading broker that simulates fills at the requested
price (or next bar's open). Tracks positions, P&L, and trade history.
Used by Game mode.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from openquant.brokers.base import (
    BaseBroker,
    OrderResult,
    OrderStatus,
    Position,
)

logger = logging.getLogger(__name__)


class PaperBroker:
    """In-memory paper trading broker.

    Simulates fills at the requested price. Tracks positions,
    realized P&L, and full trade history.

    Usage:
        broker = PaperBroker(starting_balance=10000)
        result = broker.place_order("AAPL", "BUY", 10, price=150.00)
        positions = broker.get_positions()
    """

    def __init__(self, starting_balance: float = 10000.0, name: str = "paper") -> None:
        self._name = name
        self._balance = starting_balance
        self._starting_balance = starting_balance
        self._positions: Dict[str, Dict] = {}  # ticker -> {shares, avg_price, current_price}
        self._orders: Dict[str, Dict] = {}  # order_id -> order details
        self._trade_history: List[Dict] = []
        self._realized_pnl: float = 0.0

    @property
    def name(self) -> str:
        return self._name

    @property
    def mode(self) -> str:
        return "game"

    def get_balance(self) -> float:
        """Get current cash balance."""
        return round(self._balance, 2)

    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        positions = []
        for ticker, pos in self._positions.items():
            if pos["shares"] > 0:
                market_value = pos["shares"] * pos["current_price"]
                unrealized_pnl = (pos["current_price"] - pos["avg_price"]) * pos["shares"]
                positions.append(Position(
                    ticker=ticker,
                    shares=pos["shares"],
                    avg_price=pos["avg_price"],
                    current_price=pos["current_price"],
                    market_value=round(market_value, 2),
                    unrealized_pnl=round(unrealized_pnl, 2),
                    side="long",
                ))
        return positions

    def place_order(
        self,
        ticker: str,
        action: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> OrderResult:
        """Place a paper order.

        Market orders fill immediately at the limit_price or last known price.
        """
        action = action.upper()
        ticker = ticker.upper()
        order_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        # Determine fill price
        if order_type == "limit" and limit_price:
            fill_price = limit_price
        elif order_type == "market" and limit_price:
            fill_price = limit_price
        else:
            # Use last known price from positions, or limit_price
            if ticker in self._positions:
                fill_price = self._positions[ticker]["current_price"]
            elif limit_price:
                fill_price = limit_price
            else:
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    price=0.0,
                    order_type=order_type,
                    status=OrderStatus.REJECTED.value,
                    timestamp=now,
                    message=f"No price available for {ticker}. Provide limit_price.",
                )

        total_cost = quantity * fill_price

        # ── Execute BUY ─────────────────────────────────────────────
        if action == "BUY":
            if total_cost > self._balance:
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    price=fill_price,
                    order_type=order_type,
                    status=OrderStatus.REJECTED.value,
                    timestamp=now,
                    message=f"Insufficient balance: need ${total_cost:.2f}, have ${self._balance:.2f}",
                )

            self._balance -= total_cost

            if ticker in self._positions:
                pos = self._positions[ticker]
                new_shares = pos["shares"] + quantity
                new_avg = (pos["avg_price"] * pos["shares"] + fill_price * quantity) / new_shares
                pos["shares"] = new_shares
                pos["avg_price"] = new_avg
                pos["current_price"] = fill_price
            else:
                self._positions[ticker] = {
                    "shares": quantity,
                    "avg_price": fill_price,
                    "current_price": fill_price,
                }

            self._trade_history.append({
                "order_id": order_id,
                "action": "BUY",
                "ticker": ticker,
                "quantity": quantity,
                "price": fill_price,
                "total_cost": total_cost,
                "timestamp": now.isoformat(),
            })

            self._orders[order_id] = {
                "status": OrderStatus.FILLED.value,
                "fill_price": fill_price,
                "timestamp": now.isoformat(),
            }

            return OrderResult(
                success=True,
                order_id=order_id,
                ticker=ticker,
                action="BUY",
                quantity=quantity,
                price=fill_price,
                order_type=order_type,
                status=OrderStatus.FILLED.value,
                timestamp=now,
                message=f"BUY {quantity} {ticker} @ ${fill_price:.2f}",
            )

        # ── Execute SELL ─────────────────────────────────────────────
        elif action == "SELL":
            available = self._positions.get(ticker, {}).get("shares", 0)
            if quantity > available:
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    price=fill_price,
                    order_type=order_type,
                    status=OrderStatus.REJECTED.value,
                    timestamp=now,
                    message=f"Insufficient shares: want {quantity}, have {available}",
                )

            pos = self._positions[ticker]
            realized = (fill_price - pos["avg_price"]) * quantity
            self._realized_pnl += realized
            self._balance += total_cost

            if quantity == pos["shares"]:
                del self._positions[ticker]
            else:
                pos["shares"] -= quantity
                pos["current_price"] = fill_price

            self._trade_history.append({
                "order_id": order_id,
                "action": "SELL",
                "ticker": ticker,
                "quantity": quantity,
                "price": fill_price,
                "total_cost": total_cost,
                "realized_pnl": realized,
                "timestamp": now.isoformat(),
            })

            self._orders[order_id] = {
                "status": OrderStatus.FILLED.value,
                "fill_price": fill_price,
                "timestamp": now.isoformat(),
            }

            return OrderResult(
                success=True,
                order_id=order_id,
                ticker=ticker,
                action="SELL",
                quantity=quantity,
                price=fill_price,
                order_type=order_type,
                status=OrderStatus.FILLED.value,
                timestamp=now,
                message=f"SELL {quantity} {ticker} @ ${fill_price:.2f} (P/L: ${realized:+,.2f})",
            )

        else:
            return OrderResult(
                success=False,
                order_id=order_id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                price=fill_price,
                order_type=order_type,
                status=OrderStatus.REJECTED.value,
                timestamp=now,
                message=f"Invalid action: {action}",
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order. Paper broker fills immediately, so cancellation rarely applies."""
        if order_id in self._orders:
            status = self._orders[order_id].get("status", "")
            if status == OrderStatus.PENDING.value:
                self._orders[order_id]["status"] = OrderStatus.CANCELED.value
                return True
        return False

    def get_order_status(self, order_id: str) -> OrderStatus:
        """Get the status of an order."""
        if order_id in self._orders:
            status_str = self._orders[order_id].get("status", "unknown")
            try:
                return OrderStatus(status_str)
            except ValueError:
                return OrderStatus.PENDING
        return OrderStatus.EXPIRED

    def update_price(self, ticker: str, price: float) -> None:
        """Update the current price for a held position.

        Args:
            ticker: Stock ticker.
            price: Current market price.
        """
        ticker = ticker.upper()
        if ticker in self._positions:
            self._positions[ticker]["current_price"] = price

    def update_prices(self, prices: Dict[str, float]) -> None:
        """Update current prices for multiple positions.

        Args:
            prices: Dict of ticker -> current price.
        """
        for ticker, price in prices.items():
            self.update_price(ticker, price)

    def get_total_value(self) -> float:
        """Get total account value (cash + positions)."""
        position_value = sum(
            pos["shares"] * pos["current_price"]
            for pos in self._positions.values()
        )
        return round(self._balance + position_value, 2)

    def get_trade_history(self) -> List[Dict]:
        """Get all trade history."""
        return list(self._trade_history)

    def reset(self, balance: Optional[float] = None) -> None:
        """Reset the broker to starting state."""
        self._balance = balance or self._starting_balance
        if balance:
            self._starting_balance = balance
        self._positions.clear()
        self._orders.clear()
        self._trade_history.clear()
        self._realized_pnl = 0.0
