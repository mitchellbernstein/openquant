"""Game engine for OpenQuant - paper trading with gamification.

The GameEngine manages a virtual portfolio with starting capital,
executes paper trades, tracks P&L, and awards achievements.
No real money is at risk.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from openquant.game.models import (
    Achievement,
    ACHIEVEMENTS,
    Position,
    PortfolioStatus,
    TradeResult,
)

logger = logging.getLogger(__name__)


class GameEngine:
    """Paper trading engine with gamification.

    Manages a virtual portfolio, executes trades at market prices,
    tracks performance, and awards achievements.

    Usage:
        engine = GameEngine(starting_balance=10000)
        result = engine.execute_trade("BUY", "AAPL", 10, 150.00)
        portfolio = engine.get_portfolio()
        new_achievements = engine.check_achievements()
    """

    def __init__(self, starting_balance: float = 10000.0) -> None:
        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Dict] = []
        self.achievements: Dict[str, Achievement] = {
            a.name: Achievement(
                name=a.name,
                title=a.title,
                description=a.description,
                icon=a.icon,
            )
            for a in ACHIEVEMENTS
        }
        self.stats: Dict[str, int | float] = {
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "trading_days": set(),
        }
        self._signal_timestamps: Dict[str, datetime] = {}

    def execute_trade(
        self,
        action: str,
        ticker: str,
        shares: float,
        price: float,
        signal_time: Optional[datetime] = None,
    ) -> TradeResult:
        """Execute a trade in game mode.

        Args:
            action: "BUY" or "SELL".
            ticker: Stock ticker symbol.
            shares: Number of shares to trade.
            price: Execution price per share.
            signal_time: When the signal was generated (for Quick Draw achievement).

        Returns:
            TradeResult with execution details.
        """
        action = action.upper()
        ticker = ticker.upper()
        timestamp = datetime.now()
        total_cost = shares * price

        if action not in ("BUY", "SELL"):
            return TradeResult(
                success=False,
                ticker=ticker,
                action=action,
                shares=shares,
                price=price,
                total_cost=total_cost,
                timestamp=timestamp,
                message=f"Invalid action: {action}. Must be BUY or SELL.",
            )

        if shares <= 0:
            return TradeResult(
                success=False,
                ticker=ticker,
                action=action,
                shares=shares,
                price=price,
                total_cost=total_cost,
                timestamp=timestamp,
                message="Shares must be positive.",
            )

        if price <= 0:
            return TradeResult(
                success=False,
                ticker=ticker,
                action=action,
                shares=shares,
                price=price,
                total_cost=total_cost,
                timestamp=timestamp,
                message="Price must be positive.",
            )

        if action == "BUY":
            # Check sufficient balance
            if total_cost > self.balance:
                return TradeResult(
                    success=False,
                    ticker=ticker,
                    action=action,
                    shares=shares,
                    price=price,
                    total_cost=total_cost,
                    timestamp=timestamp,
                    message=f"Insufficient balance. Need ${total_cost:.2f}, have ${self.balance:.2f}.",
                )

            # Execute buy
            self.balance -= total_cost

            if ticker in self.positions:
                pos = self.positions[ticker]
                # Update average price
                total_shares = pos.shares + shares
                new_avg = (pos.cost_basis + total_cost) / total_shares
                pos.shares = total_shares
                pos.avg_price = new_avg
                pos.current_price = price
            else:
                self.positions[ticker] = Position(
                    ticker=ticker,
                    shares=shares,
                    avg_price=price,
                    current_price=price,
                    held_since=timestamp,
                )

            # Record trade
            self.trade_history.append({
                "action": "BUY",
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "total_cost": total_cost,
                "timestamp": timestamp.isoformat(),
            })

            # Track trading day
            if isinstance(self.stats["trading_days"], set):
                self.stats["trading_days"].add(timestamp.date())

            # Track signal time for Quick Draw
            if signal_time:
                self._signal_timestamps[ticker] = signal_time

            position_shares = self.positions[ticker].shares if ticker in self.positions else 0

            return TradeResult(
                success=True,
                ticker=ticker,
                action="BUY",
                shares=shares,
                price=price,
                total_cost=total_cost,
                timestamp=timestamp,
                message=f"BOUGHT {shares:.2f} {ticker} @ ${price:.2f}",
                new_balance=self.balance,
                position_shares=position_shares,
            )

        elif action == "SELL":
            # Check sufficient shares
            if ticker not in self.positions or self.positions[ticker].shares < shares:
                available = self.positions[ticker].shares if ticker in self.positions else 0
                return TradeResult(
                    success=False,
                    ticker=ticker,
                    action=action,
                    shares=shares,
                    price=price,
                    total_cost=total_cost,
                    timestamp=timestamp,
                    message=f"Insufficient shares. Want {shares:.2f}, have {available:.2f}.",
                )

            pos = self.positions[ticker]
            # Calculate realized P/L
            realized_pnl = (price - pos.avg_price) * shares
            self.balance += total_cost

            # Update or close position
            if pos.shares == shares:
                # Close entire position
                del self.positions[ticker]
                position_shares = 0.0
            else:
                # Partial sell
                pos.shares -= shares
                pos.current_price = price
                position_shares = pos.shares

            # Update stats
            if realized_pnl > 0:
                self.stats["wins"] = self.stats.get("wins", 0) + 1
            elif realized_pnl < 0:
                self.stats["losses"] = self.stats.get("losses", 0) + 1
            self.stats["total_pnl"] = self.stats.get("total_pnl", 0.0) + realized_pnl

            # Record trade
            self.trade_history.append({
                "action": "SELL",
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "total_cost": total_cost,
                "realized_pnl": realized_pnl,
                "timestamp": timestamp.isoformat(),
            })

            # Track trading day
            if isinstance(self.stats["trading_days"], set):
                self.stats["trading_days"].add(timestamp.date())

            return TradeResult(
                success=True,
                ticker=ticker,
                action="SELL",
                shares=shares,
                price=price,
                total_cost=total_cost,
                timestamp=timestamp,
                message=f"SOLD {shares:.2f} {ticker} @ ${price:.2f} (P/L: ${realized_pnl:+,.2f})",
                new_balance=self.balance,
                position_shares=position_shares,
            )

        # Should not reach here
        return TradeResult(
            success=False,
            ticker=ticker,
            action=action,
            shares=shares,
            price=price,
            total_cost=total_cost,
            timestamp=timestamp,
            message="Unexpected error.",
        )

    def update_prices(self, prices: Dict[str, float]) -> None:
        """Update current prices for all held positions.

        Args:
            prices: Dict of ticker -> current price.
        """
        for ticker, price in prices.items():
            ticker = ticker.upper()
            if ticker in self.positions:
                self.positions[ticker].current_price = price

    def get_portfolio(self) -> PortfolioStatus:
        """Get current portfolio state.

        Returns:
            PortfolioStatus with all portfolio metrics.
        """
        # Calculate total portfolio value
        position_value = sum(p.market_value for p in self.positions.values())
        total_value = self.balance + position_value
        total_pnl = total_value - self.starting_balance
        total_pnl_pct = (total_pnl / self.starting_balance * 100) if self.starting_balance > 0 else 0.0

        unlocked = [a.name for a in self.achievements.values() if a.is_unlocked]

        return PortfolioStatus(
            balance=round(self.balance, 2),
            positions=dict(self.positions),
            total_value=round(total_value, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl_pct, 2),
            trade_count=len(self.trade_history),
            win_count=self.stats.get("wins", 0),
            loss_count=self.stats.get("losses", 0),
            achievements=unlocked,
        )

    def check_achievements(self) -> List[str]:
        """Check for newly unlocked achievements.

        Returns:
            List of newly unlocked achievement names.
        """
        newly_unlocked = []
        now = datetime.now()
        portfolio = self.get_portfolio()

        # ── First Trade ─────────────────────────────────────────────
        if not self.achievements["first_trade"].is_unlocked and len(self.trade_history) >= 1:
            self.achievements["first_trade"].unlocked_at = now
            newly_unlocked.append("first_trade")

        # ── 3-Day Streak ────────────────────────────────────────────
        trading_days = self.stats.get("trading_days", set())
        if isinstance(trading_days, set) and not self.achievements["three_day_streak"].is_unlocked:
            # Check for 3 consecutive trading days
            sorted_days = sorted(trading_days)
            if len(sorted_days) >= 3:
                for i in range(len(sorted_days) - 2):
                    d1, d2, d3 = sorted_days[i], sorted_days[i + 1], sorted_days[i + 2]
                    if (d2 - d1).days <= 1 and (d3 - d2).days <= 1:
                        self.achievements["three_day_streak"].unlocked_at = now
                        newly_unlocked.append("three_day_streak")
                        break

        # ── 5 Wins ──────────────────────────────────────────────────
        if not self.achievements["five_wins"].is_unlocked and self.stats.get("wins", 0) >= 5:
            self.achievements["five_wins"].unlocked_at = now
            newly_unlocked.append("five_wins")

        # ── 10% Return ──────────────────────────────────────────────
        if not self.achievements["ten_percent_return"].is_unlocked and portfolio.total_pnl_pct >= 10.0:
            self.achievements["ten_percent_return"].unlocked_at = now
            newly_unlocked.append("ten_percent_return")

        # ── Diamond Hands ───────────────────────────────────────────
        if not self.achievements["diamond_hands"].is_unlocked:
            for pos in self.positions.values():
                if pos.held_since and (now - pos.held_since).days >= 30:
                    self.achievements["diamond_hands"].unlocked_at = now
                    newly_unlocked.append("diamond_hands")
                    break

        # ── Quick Draw ──────────────────────────────────────────────
        if not self.achievements["quick_draw"].is_unlocked and self._signal_timestamps:
            for trade in self.trade_history:
                ticker = trade["ticker"]
                if ticker in self._signal_timestamps:
                    signal_time = self._signal_timestamps[ticker]
                    trade_time = datetime.fromisoformat(trade["timestamp"])
                    delta = (trade_time - signal_time).total_seconds()
                    if delta <= 300:  # 5 minutes
                        self.achievements["quick_draw"].unlocked_at = now
                        newly_unlocked.append("quick_draw")
                        break

        return newly_unlocked

    def get_leaderboard_stats(self) -> Dict:
        """Get stats formatted for leaderboard display.

        Returns:
            Dict with portfolio metrics suitable for sharing.
        """
        portfolio = self.get_portfolio()
        return {
            "total_value": portfolio.total_value,
            "total_return_pct": portfolio.total_pnl_pct,
            "trades": portfolio.trade_count,
            "win_rate": (
                portfolio.win_count / portfolio.trade_count * 100
                if portfolio.trade_count > 0
                else 0.0
            ),
            "achievements": len([a for a in self.achievements.values() if a.is_unlocked]),
            "positions_held": len(self.positions),
        }

    def reset(self, balance: Optional[float] = None) -> None:
        """Reset the game engine to starting state.

        Args:
            balance: New starting balance (defaults to original).
        """
        self.balance = balance or self.starting_balance
        if balance:
            self.starting_balance = balance
        self.positions.clear()
        self.trade_history.clear()
        self.stats = {"wins": 0, "losses": 0, "total_pnl": 0.0, "trading_days": set()}
        self._signal_timestamps.clear()
        # Reset achievements
        for a in self.achievements.values():
            a.unlocked_at = None
