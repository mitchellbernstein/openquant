"""Alpaca broker integration for OpenQuant.

Uses the alpaca-trade-api (optional dependency) to execute trades
on Alpaca's commission-free platform. Paper trading key is used by
default. Live trading requires explicit confirmation.

Install: pip install alpaca-trade-api
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from openquant.brokers.base import (
    OrderResult,
    OrderStatus,
    Position,
)

logger = logging.getLogger(__name__)

# Conditional import — alpaca-py is optional
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False


class AlpacaBroker:
    """Alpaca broker integration.

    Supports paper and live trading via Alpaca's API.
    Paper trading is the default. Live mode requires explicit
    confirmation and uses separate API keys.

    Modes:
        'game'  - Paper trading (default)
        'signal' - Paper trading (signal-only, no auto-execute)
        'live'  - Real money trading (requires explicit confirmation)

    Usage:
        broker = AlpacaBroker()  # Paper mode by default
        result = broker.place_order("AAPL", "BUY", 10)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
        live_confirmed: bool = False,
    ) -> None:
        if not _ALPACA_AVAILABLE:
            raise ImportError(
                "alpaca-trade-api is required for AlpacaBroker. "
                "Install with: pip install alpaca-trade-api"
            )

        self._paper = paper
        self._mode = "game" if paper else "live"
        self._live_confirmed = live_confirmed

        # Resolve API keys from params or environment
        self._api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self._secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")

        if not self._api_key or not self._secret_key:
            raise ValueError(
                "Alpaca API keys required. Set ALPACA_API_KEY and ALPACA_SECRET_KEY "
                "environment variables or pass api_key/secret_key parameters."
            )

        # If user wants live but hasn't confirmed
        if not paper and not live_confirmed:
            raise ValueError(
                "Live trading requires explicit confirmation. "
                "Pass live_confirmed=True to enable real money trading."
            )

        # Initialize Alpaca client
        try:
            self._client = TradingClient(
                api_key=self._api_key,
                secret_key=self._secret_key,
                paper=paper,
            )
            logger.info("AlpacaBroker initialized (mode=%s)", self._mode)
        except Exception as exc:
            raise ConnectionError(f"Failed to connect to Alpaca: {exc}") from exc

    @property
    def name(self) -> str:
        return "alpaca"

    @property
    def mode(self) -> str:
        return self._mode

    def get_balance(self) -> float:
        """Get current account cash balance."""
        try:
            account = self._client.get_account()
            return float(account.cash)
        except Exception as exc:
            logger.error("AlpacaBroker: failed to get balance: %s", exc)
            return 0.0

    def get_positions(self) -> List[Position]:
        """Get all open positions from Alpaca."""
        try:
            alpaca_positions = self._client.get_all_positions()
            positions = []
            for ap in alpaca_positions:
                positions.append(Position(
                    ticker=ap.symbol,
                    shares=float(ap.qty),
                    avg_price=float(ap.avg_entry_price),
                    current_price=float(ap.current_price),
                    market_value=float(ap.market_value),
                    unrealized_pnl=float(ap.unrealized_pl),
                    side="long" if float(ap.qty) > 0 else "short",
                ))
            return positions
        except Exception as exc:
            logger.error("AlpacaBroker: failed to get positions: %s", exc)
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
        """Place an order on Alpaca."""
        if not _ALPACA_AVAILABLE:
            return OrderResult(
                success=False,
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED.value,
                timestamp=datetime.now(),
                message="alpaca-trade-api not installed",
            )

        action = action.upper()
        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

        try:
            if order_type == "market":
                request = MarketOrderRequest(
                    symbol=ticker.upper(),
                    qty=quantity,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )
            elif order_type == "limit" and limit_price:
                request = LimitOrderRequest(
                    symbol=ticker.upper(),
                    qty=quantity,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price,
                )
            else:
                return OrderResult(
                    success=False,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    order_type=order_type,
                    status=OrderStatus.REJECTED.value,
                    timestamp=datetime.now(),
                    message=f"Unsupported order type: {order_type}",
                )

            order = self._client.submit_order(request)

            return OrderResult(
                success=True,
                order_id=order.id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                price=float(order.submitted_at or 0),
                order_type=order_type,
                status=OrderStatus.SUBMITTED.value,
                timestamp=datetime.now(),
                message=f"Order submitted: {action} {quantity} {ticker}",
            )

        except Exception as exc:
            logger.error("AlpacaBroker: order failed: %s", exc)
            return OrderResult(
                success=False,
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED.value,
                timestamp=datetime.now(),
                message=f"Order failed: {exc}",
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception as exc:
            logger.error("AlpacaBroker: cancel failed: %s", exc)
            return False

    def get_order_status(self, order_id: str) -> OrderStatus:
        """Get the status of an order."""
        try:
            order = self._client.get_order_by_id(order_id)
            status_map = {
                "new": OrderStatus.SUBMITTED,
                "partially_filled": OrderStatus.PARTIALLY_FILLED,
                "filled": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELED,
                "rejected": OrderStatus.REJECTED,
                "expired": OrderStatus.EXPIRED,
            }
            return status_map.get(order.status, OrderStatus.PENDING)
        except Exception as exc:
            logger.error("AlpacaBroker: get_order_status failed: %s", exc)
            return OrderStatus.EXPIRED
