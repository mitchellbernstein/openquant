"""FastMCP server for OpenQuant.

Exposes OpenQuant functionality as MCP tools for AI agent integration.
Only importable when the 'mcp' package is installed.

Tools:
  - openquant_analyze: Full analysis of a ticker
  - openquant_strategy_run: Run a specific strategy on a ticker
  - openquant_strategy_list: List available strategies
  - openquant_portfolio_status: Get current portfolio state
  - openquant_risk_assessment: Run risk assessment
  - openquant_insider_scan: Scan insider trading activity
  - openquant_backtest: Backtest a strategy
  - openquant_game_status: Get game mode status
  - openquant_trade_execute: Execute a trade (paper or live)
  - openquant_trade_history: Get trade history

Usage:
    from openquant.mcp.server import create_server

    server = create_server()
    # Run with SSE transport:
    server.run(transport="sse")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Conditional import — mcp is optional
try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


def create_server() -> "FastMCP":
    """Create the OpenQuant MCP server.

    Returns:
        FastMCP server instance with all tools registered.

    Raises:
        ImportError: If the 'mcp' package is not installed.
    """
    if not _MCP_AVAILABLE:
        raise ImportError(
            "The 'mcp' package is required for the MCP server. "
            "Install with: pip install openquant[mcp]"
        )

    mcp = FastMCP(
        name="openquant",
        instructions="OpenQuant - The open-source operating system for quant trading. Analyze stocks, run strategies, manage portfolios, and execute trades.",
    )

    # ── Helper to lazily import and create data resolver ────────────
    def _get_resolver():
        from openquant.data.resolver import DataResolver
        return DataResolver.from_env()

    # ── Tool: openquant_analyze ─────────────────────────────────────
    @mcp.tool()
    def openquant_analyze(ticker: str, days: int = 90) -> Dict[str, Any]:
        """Run full analysis on a stock ticker.

        Returns price data, insider trades, analyst estimates, and risk metrics.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL").
            days: Lookback period in days (default 90).
        """
        from datetime import date, timedelta
        from openquant.insider.monitor import InsiderMonitor
        from openquant.risk.engine import RiskEngine

        resolver = _get_resolver()
        end = date.today()
        start = end - timedelta(days=days)

        result: Dict[str, Any] = {"ticker": ticker.upper()}

        # Price data
        prices = resolver.get_prices(ticker.upper(), start, end)
        if prices:
            result["current_price"] = prices[-1].close
            result["price_range_52d"] = {
                "high": max(p.high for p in prices),
                "low": min(p.low for p in prices),
            }

        # Insider data
        try:
            monitor = InsiderMonitor()
            report = monitor.scan(ticker.upper(), resolver)
            result["insider"] = {
                "score": report.score.score,
                "label": report.score.label,
                "patterns": report.score.patterns[:5],
                "alerts": report.alerts[:3],
                "trade_count": len(report.recent_trades),
            }
        except Exception as exc:
            result["insider"] = {"error": str(exc)}

        # Risk assessment
        try:
            risk_engine = RiskEngine()
            risk_report = risk_engine.assess([ticker.upper()], resolver)
            result["risk"] = {
                "level": risk_report.risk_level,
                "var_95": risk_report.var_95,
                "max_drawdown": risk_report.max_drawdown,
                "kelly_fraction": risk_report.kelly_fraction,
                "warnings": risk_report.warnings[:3],
            }
        except Exception as exc:
            result["risk"] = {"error": str(exc)}

        return result

    # ── Tool: openquant_strategy_run ────────────────────────────────
    @mcp.tool()
    def openquant_strategy_run(strategy_name: str, ticker: str) -> Dict[str, Any]:
        """Run a specific trading strategy on a ticker.

        Args:
            strategy_name: Name of the strategy (e.g. "insider-momentum").
            ticker: Stock ticker symbol.
        """
        from openquant.strategies.insider_momentum import InsiderMomentumStrategy
        from openquant.strategies.value_deep import ValueDeepStrategy
        from openquant.strategies.earnings_surge import EarningsSurgeStrategy
        from openquant.strategies.technical_breakout import TechnicalBreakoutStrategy

        strategies = {
            "insider-momentum": InsiderMomentumStrategy,
            "value-deep": ValueDeepStrategy,
            "earnings-surge": EarningsSurgeStrategy,
            "technical-breakout": TechnicalBreakoutStrategy,
        }

        strategy_cls = strategies.get(strategy_name)
        if not strategy_cls:
            return {
                "error": f"Unknown strategy: {strategy_name}",
                "available": list(strategies.keys()),
            }

        resolver = _get_resolver()
        strategy = strategy_cls()
        result = strategy.generate_signal(ticker.upper(), resolver)

        return {
            "strategy": result.strategy_name,
            "ticker": result.ticker,
            "action": result.action,
            "confidence": result.confidence,
            "entry_price": result.entry_price,
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "position_size_pct": result.position_size_pct,
            "reasoning": result.reasoning,
        }

    # ── Tool: openquant_strategy_list ──────────────────────────────
    @mcp.tool()
    def openquant_strategy_list() -> List[Dict[str, str]]:
        """List all available trading strategies."""
        return [
            {"name": "insider-momentum", "description": "Trade on insider buying momentum signals"},
            {"name": "value-deep", "description": "Deep value investing based on fundamentals"},
            {"name": "earnings-surge", "description": "Capture post-earnings announcement drift"},
            {"name": "technical-breakout", "description": "Breakout-based technical trading with insider confirmation"},
        ]

    # ── Tool: openquant_portfolio_status ───────────────────────────
    @mcp.tool()
    def openquant_portfolio_status() -> Dict[str, Any]:
        """Get current portfolio status from the game engine.

        Returns balance, positions, P/L, and achievements.
        """
        from openquant.game.engine import GameEngine
        from openquant.storage import load_state

        state = load_state()
        engine = GameEngine(starting_balance=state.get("starting_balance", 10000))
        # Restore positions from state
        for ticker, pos_data in state.get("positions", {}).items():
            from openquant.game.models import Position
            from datetime import datetime
            engine.positions[ticker] = Position(
                ticker=ticker,
                shares=pos_data.get("shares", 0),
                avg_price=pos_data.get("avg_price", 0),
                current_price=pos_data.get("current_price", 0),
                held_since=datetime.fromisoformat(pos_data["held_since"]) if pos_data.get("held_since") else None,
            )
        engine.balance = state.get("balance", 10000)

        portfolio = engine.get_portfolio()
        return {
            "balance": portfolio.balance,
            "total_value": portfolio.total_value,
            "total_pnl": portfolio.total_pnl,
            "total_pnl_pct": portfolio.total_pnl_pct,
            "trade_count": portfolio.trade_count,
            "win_count": portfolio.win_count,
            "loss_count": portfolio.loss_count,
            "positions": {
                t: {
                    "shares": p.shares,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                }
                for t, p in portfolio.positions.items()
            },
            "achievements": portfolio.achievements,
        }

    # ── Tool: openquant_risk_assessment ────────────────────────────
    @mcp.tool()
    def openquant_risk_assessment(tickers: str, days: int = 252) -> Dict[str, Any]:
        """Run risk assessment on one or more tickers.

        Args:
            tickers: Comma-separated ticker symbols (e.g. "AAPL,MSFT").
            days: Lookback period in trading days (default 252).
        """
        from openquant.risk.engine import RiskEngine

        resolver = _get_resolver()
        ticker_list = [t.strip().upper() for t in tickers.split(",")]
        engine = RiskEngine()
        report = engine.assess(ticker_list, resolver, lookback_days=days)

        return {
            "tickers": report.tickers,
            "risk_level": report.risk_level,
            "var_95": report.var_95,
            "var_99": report.var_99,
            "max_drawdown": report.max_drawdown,
            "kelly_fraction": report.kelly_fraction,
            "position_sizes": report.position_sizes,
            "warnings": report.warnings,
            "recommendations": report.recommendations,
        }

    # ── Tool: openquant_insider_scan ───────────────────────────────
    @mcp.tool()
    def openquant_insider_scan(ticker: str, days: int = 90) -> Dict[str, Any]:
        """Scan insider trading activity for a ticker.

        Returns insider sentiment score, detected patterns, and alerts.

        Args:
            ticker: Stock ticker symbol.
            days: Lookback period in days (default 90).
        """
        from openquant.insider.monitor import InsiderMonitor

        resolver = _get_resolver()
        monitor = InsiderMonitor()
        report = monitor.scan(ticker.upper(), resolver)

        return {
            "ticker": report.ticker,
            "score": report.score.score,
            "label": report.score.label,
            "patterns": report.score.patterns,
            "alerts": report.alerts,
            "trade_count": len(report.recent_trades),
            "buy_count": sum(1 for t in report.recent_trades if t.transaction_type == "BUY"),
            "sell_count": sum(1 for t in report.recent_trades if t.transaction_type == "SELL"),
        }

    # ── Tool: openquant_backtest ───────────────────────────────────
    @mcp.tool()
    def openquant_backtest(strategy_name: str, ticker: str, days: int = 252) -> Dict[str, Any]:
        """Backtest a strategy on a ticker.

        Args:
            strategy_name: Name of the strategy.
            ticker: Stock ticker symbol.
            days: Number of trading days to backtest (default 252).
        """
        from openquant.strategies.insider_momentum import InsiderMomentumStrategy
        from openquant.strategies.value_deep import ValueDeepStrategy
        from openquant.strategies.earnings_surge import EarningsSurgeStrategy
        from openquant.strategies.technical_breakout import TechnicalBreakoutStrategy

        strategies = {
            "insider-momentum": InsiderMomentumStrategy,
            "value-deep": ValueDeepStrategy,
            "earnings-surge": EarningsSurgeStrategy,
            "technical-breakout": TechnicalBreakoutStrategy,
        }

        strategy_cls = strategies.get(strategy_name)
        if not strategy_cls:
            return {"error": f"Unknown strategy: {strategy_name}"}

        resolver = _get_resolver()
        strategy = strategy_cls()
        result = strategy.backtest(ticker.upper(), resolver, days=days)

        return {
            "strategy": result.strategy_name,
            "ticker": result.ticker,
            "total_trades": result.total_trades,
            "win_rate": result.win_rate,
            "total_return": result.total_return,
            "max_drawdown": result.max_drawdown,
            "sharpe_ratio": result.sharpe_ratio,
            "avg_holding_days": result.avg_holding_days,
        }

    # ── Tool: openquant_game_status ────────────────────────────────
    @mcp.tool()
    def openquant_game_status() -> Dict[str, Any]:
        """Get game mode leaderboard stats and achievements."""
        from openquant.game.engine import GameEngine
        from openquant.storage import load_state

        state = load_state()
        engine = GameEngine(starting_balance=state.get("starting_balance", 10000))
        engine.balance = state.get("balance", 10000)

        return engine.get_leaderboard_stats()

    # ── Tool: openquant_trade_execute ───────────────────────────────
    @mcp.tool()
    def openquant_trade_execute(
        action: str,
        ticker: str,
        shares: float,
        price: float,
    ) -> Dict[str, Any]:
        """Execute a paper trade in game mode.

        Args:
            action: "BUY" or "SELL".
            ticker: Stock ticker symbol.
            shares: Number of shares.
            price: Execution price per share.
        """
        from openquant.game.engine import GameEngine
        from openquant.storage import load_state, save_state

        state = load_state()
        engine = GameEngine(starting_balance=state.get("starting_balance", 10000))
        engine.balance = state.get("balance", 10000)

        # Restore positions
        for t, pos_data in state.get("positions", {}).items():
            from openquant.game.models import Position
            from datetime import datetime
            engine.positions[t] = Position(
                ticker=t,
                shares=pos_data.get("shares", 0),
                avg_price=pos_data.get("avg_price", 0),
                current_price=pos_data.get("current_price", 0),
                held_since=datetime.fromisoformat(pos_data["held_since"]) if pos_data.get("held_since") else None,
            )

        result = engine.execute_trade(action, ticker, shares, price)

        # Save state after trade
        new_state = {
            "starting_balance": engine.starting_balance,
            "balance": engine.balance,
            "positions": {
                t: {
                    "shares": p.shares,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "held_since": p.held_since.isoformat() if p.held_since else None,
                }
                for t, p in engine.positions.items()
            },
        }
        save_state(new_state)

        return {
            "success": result.success,
            "ticker": result.ticker,
            "action": result.action,
            "shares": result.shares,
            "price": result.price,
            "total_cost": result.total_cost,
            "message": result.message,
            "new_balance": result.new_balance,
        }

    # ── Tool: openquant_trade_history ──────────────────────────────
    @mcp.tool()
    def openquant_trade_history(limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent trade history from game mode.

        Args:
            limit: Maximum number of trades to return (default 20).
        """
        from openquant.storage import load_trades

        trades = load_trades()
        return trades[-limit:] if len(trades) > limit else trades

    return mcp


def main() -> None:
    """Run the MCP server with SSE transport."""
    if not _MCP_AVAILABLE:
        print("Error: The 'mcp' package is required. Install with: pip install openquant[mcp]")
        raise SystemExit(1)

    server = create_server()
    server.run(transport="sse")


if __name__ == "__main__":
    main()
