"""Kalshi broker integration for OpenQuant.

Uses the Kalshi API to trade prediction market contracts.
Implements the same BaseBroker protocol as other brokers.
Note: Kalshi uses contracts, not shares — quantities represent contracts.

Kalshi API access requires API keys. Install: pip install kalshi-trade-api (optional)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from openquant.brokers.base import (
    OrderResult,
    OrderStatus,
    Position,
)

logger = logging.getLogger(__name__)

# Conditional import — kalshi is optional
try:
    from kalshi.trading_client import KalshiTradeClient
    _KALSHI_AVAILABLE = True
except ImportError:
    _KALSHI_AVAILABLE = False


class KalshiBroker:
    """Kalshi prediction market broker.

    Trades prediction market contracts on the Kalshi platform.
    Note: Kalshi uses contracts (not shares) — each contract settles
    at $1.00 if the event occurs, $0.00 if it doesn't.

    Modes:
        'game'  - Demo/paper mode
        'signal' - Signal-only mode (no execution)
        'live'  - Real money trading (requires explicit confirmation)

    Usage:
        broker = KalshiBroker()  # Demo mode by default
        result = broker.place_order("INXD-2412-1000", "BUY", 10)
    """

    # In Kalshi, each contract is worth up to $1.00
    CONTRACT_VALUE = 1.00

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        demo: bool = True,
        live_confirmed: bool = False,
    ) -> None:
        if not _KALSHI_AVAILABLE:
            raise ImportError(
                "kalshi-trade-api is required for KalshiBroker. "
                "Install with: pip install kalshi-trade-api"
            )

        self._demo = demo
        self._mode = "game" if demo else "live"
        self._live_confirmed = live_confirmed

        # Resolve API keys from params or environment
        self._api_key = api_key or os.environ.get("KALSHI_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("KALSHI_API_SECRET", "")

        if not self._api_key or not self._api_secret:
            raise ValueError(
                "Kalshi API keys required. Set KALSHI_API_KEY and KALSHI_API_SECRET "
                "environment variables or pass api_key/api_secret parameters."
            )

        # If user wants live but hasn't confirmed
        if not demo and not live_confirmed:
            raise ValueError(
                "Live trading requires explicit confirmation. "
                "Pass live_confirmed=True to enable real money trading."
            )

        # Initialize Kalshi client
        try:
            self._client = KalshiTradeClient(
                api_key=self._api_key,
                api_secret=self._api_secret,
                demo=demo,
            )
            logger.info("KalshiBroker initialized (mode=%s)", self._mode)
        except Exception as exc:
            raise ConnectionError(f"Failed to connect to Kalshi: {exc}") from exc

    @property
    def name(self) -> str:
        return "kalshi"

    @property
    def mode(self) -> str:
        return self._mode

    def get_balance(self) -> float:
        """Get current account balance."""
        try:
            balance = self._client.get_balance()
            return float(balance)
        except Exception as exc:
            logger.error("KalshiBroker: failed to get balance: %s", exc)
            return 0.0

    def get_positions(self) -> List[Position]:
        """Get all open contract positions from Kalshi.

        In Kalshi, positions are contracts. Each contract has a
        ticker (market series), quantity (number of contracts),
        and a purchase price.
        """
        try:
            kalshi_positions = self._client.get_positions()
            positions = []
            for kp in kalshi_positions:
                # Kalshi positions may use different field names
                ticker = getattr(kp, "market_ticker", getattr(kp, "ticker", ""))
                shares = float(getattr(kp, "quantity", getattr(kp, "contracts", 0)))
                avg_price = float(getattr(kp, "avg_price", getattr(kp, "purchase_price", 0)))
                current_price = float(getattr(kp, "current_price", 0))
                market_value = shares * current_price
                unrealized_pnl = (current_price - avg_price) * shares

                positions.append(Position(
                    ticker=ticker,
                    shares=shares,
                    avg_price=avg_price,
                    current_price=current_price,
                    market_value=round(market_value, 2),
                    unrealized_pnl=round(unrealized_pnl, 2),
                    side="long" if shares > 0 else "short",
                ))
            return positions
        except Exception as exc:
            logger.error("KalshiBroker: failed to get positions: %s", exc)
            return []

    def place_order(
        self,
        ticker: str,
        action: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> OrderResult:
        """Place a contract order on Kalshi.

        Args:
            ticker: Kalshi market ticker (e.g. "INXD-2412-1000").
            action: "BUY" or "SELL".
            quantity: Number of contracts.
            order_type: "market" or "limit".
            limit_price: Maximum price per contract (for limit orders).
        """
        if not _KALSHI_AVAILABLE:
            return OrderResult(
                success=False,
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED.value,
                timestamp=datetime.now(),
                message="kalshi-trade-api not installed",
            )

        action = action.upper()
        now = datetime.now()

        # Validate quantity (must be integer for contracts)
        int_quantity = int(quantity)
        if int_quantity <= 0:
            return OrderResult(
                success=False,
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED.value,
                timestamp=now,
                message="Contract quantity must be a positive integer",
            )

        try:
            if action == "BUY":
                # Buy contracts (yes side in Kalshi terms)
                result = self._client.buy_contracts(
                    market_ticker=ticker,
                    quantity=int_quantity,
                    price=limit_price or self.CONTRACT_VALUE,
                    order_type=order_type,
                )
            elif action == "SELL":
                # Sell contracts
                result = self._client.sell_contracts(
                    market_ticker=ticker,
                    quantity=int_quantity,
                    price=limit_price or 0.0,
                    order_type=order_type,
                )
            else:
                return OrderResult(
                    success=False,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    order_type=order_type,
                    status=OrderStatus.REJECTED.value,
                    timestamp=now,
                    message=f"Invalid action: {action}",
                )

            order_id = getattr(result, "order_id", getattr(result, "id", ""))
            fill_price = float(getattr(result, "fill_price", limit_price or 0))

            return OrderResult(
                success=True,
                order_id=str(order_id),
                ticker=ticker,
                action=action,
                quantity=int_quantity,
                price=fill_price,
                order_type=order_type,
                status=OrderStatus.SUBMITTED.value,
                timestamp=now,
                message=f"Order submitted: {action} {int_quantity} {ticker} contracts",
            )

        except Exception as exc:
            logger.error("KalshiBroker: order failed: %s", exc)
            return OrderResult(
                success=False,
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED.value,
                timestamp=now,
                message=f"Order failed: {exc}",
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        try:
            self._client.cancel_order(order_id)
            return True
        except Exception as exc:
            logger.error("KalshiBroker: cancel failed: %s", exc)
            return False

    def get_order_status(self, order_id: str) -> OrderStatus:
        """Get the status of an order."""
        try:
            order = self._client.get_order(order_id)
            status_str = getattr(order, "status", "unknown")
            status_map = {
                "pending": OrderStatus.PENDING,
                "submitted": OrderStatus.SUBMITTED,
                "partially_filled": OrderStatus.PARTIALLY_FILLED,
                "filled": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELED,
                "rejected": OrderStatus.REJECTED,
                "expired": OrderStatus.EXPIRED,
            }
            return status_map.get(status_str, OrderStatus.PENDING)
        except Exception as exc:
            logger.error("KalshiBroker: get_order_status failed: %s", exc)
            return OrderStatus.EXPIRED
