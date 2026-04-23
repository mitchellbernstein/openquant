"""OpenQuant CLI - command-line interface powered by Click and Rich."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from dataclasses import asdict

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box

from openquant.data.resolver import DataResolver
from openquant.cli.display import (
    format_price_panel,
    format_insider_panel,
    format_risk_panel,
    format_analysis_panel,
)

logger = logging.getLogger(__name__)
console = Console()


# ==================================================================
# JSON output helpers
# ==================================================================

def _json_output_enabled(ctx: click.Context) -> bool:
    """Check whether --json mode is active."""
    return bool(ctx.obj.get("json_output"))


def _emit_json(ctx: click.Context, payload: dict) -> None:
    """Write a structured JSON blob to stdout.

    Automatically adds a ``timestamp`` field in ISO-8601 UTC.
    """
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    click.echo(json.dumps(payload, default=str, indent=2))


def _serialize_price(p) -> dict:
    return {
        "date": str(p.date),
        "open": p.open,
        "high": p.high,
        "low": p.low,
        "close": p.close,
        "volume": p.volume,
        "source": p.source,
    }


def _serialize_insider_trade(t) -> dict:
    return {
        "insider_name": t.insider_name,
        "title": t.title,
        "transaction_type": t.transaction_type,
        "shares": t.shares,
        "price": t.price,
        "value": t.value,
        "date": str(t.date),
        "source": t.source,
    }


def _serialize_estimate(e) -> dict:
    return {
        "estimate_type": e.estimate_type,
        "period": e.period,
        "consensus_avg": e.consensus_avg,
        "consensus_low": e.consensus_low,
        "consensus_high": e.consensus_high,
        "number_of_analysts": e.number_of_analysts,
        "source": e.source,
    }


def _serialize_company_info(info) -> dict:
    return {
        "name": info.name,
        "sector": info.sector,
        "industry": info.industry,
        "market_cap": info.market_cap,
        "cik": info.cik,
    }


# ==================================================================
# Root group
# ==================================================================

@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose/debug logging.")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON instead of Rich formatting.")
@click.version_option(version="0.1.0", prog_name="openquant")
@click.pass_context
def cli(ctx, verbose, json_output):
    """OpenQuant - The open-source operating system for quant trading."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["json_output"] = json_output
    if verbose:
        logging.basicConfig(level=logging.DEBUG)


# ==================================================================
# openquant run TICKER
# ==================================================================

@cli.command()
@click.argument("ticker")
@click.option("--days", "-d", default=90, help="Lookback period in days.")
@click.option("--provider", "-p", default=None, help="Force a specific data provider.")
@click.pass_context
def run(ctx, ticker: str, days: int, provider: Optional[str]):
    """Run full analysis on a ticker.

    Shows prices, insider trades, analyst estimates, and risk assessment.
    """
    ticker = ticker.upper()

    if _json_output_enabled(ctx):
        resolver = DataResolver.from_env()
        end = date.today()
        start = end - timedelta(days=days)

        prices = resolver.get_prices(ticker, start, end)
        trades = resolver.get_insider_trades(ticker, days=days)
        estimates = resolver.get_analyst_estimates(ticker)
        info = resolver.get_company_info(ticker)

        data = {}
        if info:
            data["company_info"] = _serialize_company_info(info)
        if prices:
            data["prices"] = [_serialize_price(p) for p in prices]
        else:
            data["prices"] = []
        if trades:
            data["insider_trades"] = [_serialize_insider_trade(t) for t in trades]
        else:
            data["insider_trades"] = []
        if estimates:
            data["analyst_estimates"] = [_serialize_estimate(e) for e in estimates]
        else:
            data["analyst_estimates"] = []

        risk_report = _compute_basic_risk(prices)
        data["risk"] = risk_report if risk_report else {}

        _emit_json(ctx, {
            "command": "run",
            "ticker": ticker,
            "data": data,
        })
        return

    # --- Rich output (default) ---
    console.print(Panel(
        f"[bold cyan]OpenQuant[/bold cyan] — Running full analysis for [bold]{ticker}[/bold]",
        border_style="cyan",
    ))

    resolver = DataResolver.from_env()
    end = date.today()
    start = end - timedelta(days=days)

    # Fetch data
    with console.status("[bold green]Fetching price data..."):
        prices = resolver.get_prices(ticker, start, end)

    with console.status("[bold magenta]Fetching insider trades..."):
        trades = resolver.get_insider_trades(ticker, days=days)

    with console.status("[bold yellow]Fetching analyst estimates..."):
        estimates = resolver.get_analyst_estimates(ticker)

    with console.status("[bold blue]Fetching company info..."):
        info = resolver.get_company_info(ticker)

    # Display company info
    if info:
        info_table = Table(box=box.SIMPLE, show_header=False)
        info_table.add_column("Key", style="bold")
        info_table.add_column("Value")
        info_table.add_row("Name", info.name)
        info_table.add_row("Sector", info.sector or "N/A")
        info_table.add_row("Industry", info.industry or "N/A")
        info_table.add_row("Market Cap", f"${info.market_cap:,.0f}" if info.market_cap else "N/A")
        info_table.add_row("CIK", info.cik or "N/A")
        console.print(Panel(info_table, title="[bold]Company Info[/bold]", border_style="cyan", padding=(0, 1)))

    # Display prices
    if prices:
        console.print(format_price_panel(prices, title=f"{ticker} Prices"))
    else:
        console.print("[dim]No price data available.[/dim]")

    # Display insider trades
    if trades:
        console.print(format_insider_panel(trades, title=f"{ticker} Insider Trades"))
    else:
        console.print("[dim]No insider trade data available.[/dim]")

    # Display analyst estimates
    if estimates:
        est_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold yellow")
        est_table.add_column("Type")
        est_table.add_column("Period")
        est_table.add_column("Avg", justify="right")
        est_table.add_column("Low", justify="right")
        est_table.add_column("High", justify="right")
        est_table.add_column("Analysts", justify="right")
        est_table.add_column("Source", style="dim")
        for e in estimates:
            est_table.add_row(
                e.estimate_type,
                e.period,
                f"{e.consensus_avg:,.2f}",
                f"{e.consensus_low:,.2f}",
                f"{e.consensus_high:,.2f}",
                str(e.number_of_analysts),
                e.source,
            )
        console.print(Panel(est_table, title=f"[bold]{ticker} Analyst Estimates[/bold]", border_style="yellow", padding=(0, 1)))
    else:
        console.print("[dim]No analyst estimate data available.[/dim]")

    # Risk assessment (placeholder — full risk engine not yet implemented)
    risk_report = _compute_basic_risk(prices)
    if risk_report:
        console.print(format_risk_panel(risk_report, title=f"{ticker} Risk"))
    else:
        console.print("[dim]Insufficient data for risk assessment.[/dim]")


# ==================================================================
# openquant strategy list / strategy run
# ==================================================================

@cli.group()
@click.pass_context
def strategy(ctx):
    """Manage and run trading strategies."""
    pass


@strategy.command("list")
@click.pass_context
def strategy_list(ctx):
    """List available strategies."""
    known_strategies = [
        {"name": "insider-momentum", "description": "Trade on insider buying momentum signals"},
        {"name": "value-deep", "description": "Deep value investing based on fundamentals"},
        {"name": "earnings-surge", "description": "Capture post-earnings announcement drift"},
        {"name": "technical-breakout", "description": "Breakout-based technical trading"},
    ]

    if _json_output_enabled(ctx):
        _emit_json(ctx, {
            "command": "strategy_list",
            "data": known_strategies,
        })
        return

    # --- Rich output (default) ---
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold green")
    table.add_column("Strategy", style="bold")
    table.add_column("Description")

    for s in known_strategies:
        table.add_row(s["name"], s["description"])

    console.print(Panel(table, title="[bold]Available Strategies[/bold]", border_style="green", padding=(0, 1)))


def _get_strategy(name: str):
    """Instantiate a strategy by name. Returns (strategy_instance, error_message)."""
    from openquant.strategies import (
        InsiderMomentumStrategy,
        ValueDeepStrategy,
        EarningsSurgeStrategy,
        TechnicalBreakoutStrategy,
    )

    strategy_map = {
        "insider-momentum": InsiderMomentumStrategy,
        "value-deep": ValueDeepStrategy,
        "earnings-surge": EarningsSurgeStrategy,
        "technical-breakout": TechnicalBreakoutStrategy,
    }

    cls = strategy_map.get(name)
    if cls is None:
        return None, f"Unknown strategy '{name}'. Available: {', '.join(strategy_map.keys())}"
    return cls(), None


def _serialize_signal(s) -> dict:
    """Serialize a SignalResult to a JSON-friendly dict."""
    return {
        "agent_name": s.agent_name,
        "signal": s.signal,
        "direction": s.direction,
        "confidence": s.confidence,
        "reasoning": s.reasoning,
    }


@strategy.command("run")
@click.argument("name")
@click.option("--ticker", "-t", required=True, help="Ticker symbol to trade.")
@click.option("--mode", "-m", default="paper", type=click.Choice(["paper", "game", "live"]), help="Execution mode.")
@click.pass_context
def strategy_run(ctx, name: str, ticker: str, mode: str):
    """Run a named strategy on a ticker."""
    ticker = ticker.upper()

    # Instantiate the strategy
    strategy, err = _get_strategy(name)
    if err:
        if _json_output_enabled(ctx):
            _emit_json(ctx, {"command": "strategy_run", "data": {"error": err}})
        else:
            console.print(f"[red]{err}[/red]")
        return

    resolver = DataResolver.from_env()

    # Generate the signal
    result = strategy.generate_signal(ticker, resolver)

    if _json_output_enabled(ctx):
        data = {
            "strategy": name,
            "ticker": ticker,
            "mode": mode,
            "action": result.action,
            "confidence": result.confidence,
            "entry_price": result.entry_price,
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "position_size_pct": result.position_size_pct,
            "reasoning": result.reasoning,
            "signals": [_serialize_signal(s) for s in result.signals],
            "status": "completed",
        }
        if result.risk_report:
            data["risk"] = {
                "risk_level": result.risk_report.risk_level,
                "var_95": result.risk_report.var_95,
                "max_drawdown": result.risk_report.max_drawdown,
            }
        _emit_json(ctx, {
            "command": "strategy_run",
            "data": data,
        })
        return

    # --- Rich output (default) ---
    console.print(Panel(
        f"Strategy: [bold]{name}[/bold] | Ticker: [bold]{ticker}[/bold] | Mode: [bold]{mode}[/bold]",
        border_style="green",
    ))

    # Signal result panel
    action_color = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}.get(result.action, "white")
    conf_color = "green" if result.confidence >= 60 else "yellow" if result.confidence >= 40 else "red"

    signal_table = Table(box=box.SIMPLE, show_header=False)
    signal_table.add_column("Key", style="bold")
    signal_table.add_column("Value")
    signal_table.add_row("Action", f"[{action_color}]{result.action}[/{action_color}]")
    signal_table.add_row("Confidence", f"[{conf_color}]{result.confidence}/100[/{conf_color}]")
    if result.entry_price > 0:
        signal_table.add_row("Entry Price", f"${result.entry_price:.2f}")
        signal_table.add_row("Stop Loss", f"${result.stop_loss:.2f}")
        signal_table.add_row("Take Profit", f"${result.take_profit:.2f}")
    signal_table.add_row("Position Size", f"{result.position_size_pct:.1%} of portfolio")
    signal_table.add_row("Reasoning", result.reasoning)

    console.print(Panel(signal_table, title="[bold]Strategy Signal[/bold]", border_style="cyan", padding=(0, 1)))

    # Show contributing agent signals
    if result.signals:
        sig_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta")
        sig_table.add_column("Agent")
        sig_table.add_column("Direction")
        sig_table.add_column("Confidence", justify="right")
        sig_table.add_column("Reasoning")
        for s in result.signals:
            dir_color = "green" if s.direction == "BULLISH" else "red" if s.direction == "BEARISH" else "yellow"
            sig_table.add_row(
                s.agent_name,
                f"[{dir_color}]{s.direction}[/{dir_color}]",
                f"{s.confidence}/100",
                s.reasoning[:80],
            )
        console.print(Panel(sig_table, title="[bold]Agent Signals[/bold]", border_style="magenta", padding=(0, 1)))

    # Risk level
    if result.risk_report:
        risk_color = {"HIGH": "red", "MODERATE": "yellow", "LOW": "green", "VERY LOW": "cyan"}.get(result.risk_report.risk_level, "white")
        console.print(f"Risk Level: [{risk_color}]{result.risk_report.risk_level}[/{risk_color}]")

    # Show price data if available
    end = date.today()
    start = end - timedelta(days=90)
    prices = resolver.get_prices(ticker, start, end)
    if prices:
        console.print(format_price_panel(prices[-10:], title=f"{ticker} Recent Prices"))


# ==================================================================
# openquant game start / status / trade
# ==================================================================

@cli.group()
@click.pass_context
def game(ctx):
    """Game mode - practice trading with virtual capital."""
    pass


@game.command("start")
@click.option("--strategy", "-s", default="insider-momentum", help="Strategy to use.")
@click.option("--balance", "-b", default=10000.0, type=float, help="Starting balance.")
@click.pass_context
def game_start(ctx, strategy: str, balance: float):
    """Start a game-mode trading session."""
    from openquant.game import GameEngine, save_session, new_session_id

    session_id = new_session_id()
    engine = GameEngine(starting_balance=balance)
    save_session(engine, session_id, strategy)

    if _json_output_enabled(ctx):
        portfolio = engine.get_portfolio()
        _emit_json(ctx, {
            "command": "game_start",
            "data": {
                "session_id": session_id,
                "strategy": strategy,
                "starting_balance": balance,
                "balance": portfolio.balance,
                "total_value": portfolio.total_value,
                "status": "started",
            },
        })
        return

    # --- Rich output (default) ---
    console.print(Panel(
        Text.assemble(
            ("Game Mode Started!\n", "bold cyan"),
            (f"Session:  {session_id}\n", ""),
            (f"Strategy: {strategy}\n", "bold"),
            (f"Starting Balance: ${balance:,.2f}\n", "bold green"),
            ("Paper trading — no real money at risk.", "dim"),
        ),
        border_style="cyan",
        padding=(1, 2),
    ))


@game.command("status")
@click.pass_context
def game_status(ctx):
    """Show current game state (balance, positions, P&L)."""
    from openquant.game import load_session, get_active_session_id

    session_id = get_active_session_id()
    if not session_id:
        if _json_output_enabled(ctx):
            _emit_json(ctx, {"command": "game_status", "data": {"error": "No active game session. Run 'openquant game start' first."}})
        else:
            console.print("[red]No active game session.[/red] Run [bold]openquant game start[/bold] first.")
        return

    result = load_session(session_id)
    if not result:
        if _json_output_enabled(ctx):
            _emit_json(ctx, {"command": "game_status", "data": {"error": f"Could not load session {session_id}"}})
        else:
            console.print(f"[red]Could not load session {session_id}[/red]")
        return

    engine, strategy = result
    portfolio = engine.get_portfolio()

    if _json_output_enabled(ctx):
        positions_data = {}
        for ticker, pos in portfolio.positions.items():
            positions_data[ticker] = {
                "ticker": pos.ticker,
                "shares": pos.shares,
                "avg_price": pos.avg_price,
                "current_price": pos.current_price,
                "cost_basis": pos.cost_basis,
                "market_value": pos.market_value,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_pct": pos.unrealized_pnl_pct,
            }
        _emit_json(ctx, {
            "command": "game_status",
            "data": {
                "session_id": session_id,
                "strategy": strategy,
                "balance": portfolio.balance,
                "positions": positions_data,
                "total_value": portfolio.total_value,
                "total_pnl": portfolio.total_pnl,
                "total_pnl_pct": portfolio.total_pnl_pct,
                "trade_count": portfolio.trade_count,
                "win_count": portfolio.win_count,
                "loss_count": portfolio.loss_count,
                "achievements": portfolio.achievements,
            },
        })
        return

    # --- Rich output (default) ---
    console.print(Panel(
        Text.assemble(
            ("Game Status\n", "bold cyan"),
            (f"Session:  {session_id}\n", ""),
            (f"Strategy: {strategy}", ""),
        ),
        border_style="cyan",
        padding=(1, 2),
    ))

    # Portfolio summary
    pnl_color = "green" if portfolio.total_pnl >= 0 else "red"
    pnl_sign = "+" if portfolio.total_pnl >= 0 else ""
    summary_table = Table(box=box.SIMPLE, show_header=False)
    summary_table.add_column("Key", style="bold")
    summary_table.add_column("Value")
    summary_table.add_row("Portfolio Value", f"${portfolio.total_value:,.2f}")
    summary_table.add_row("Cash Balance", f"${portfolio.balance:,.2f}")
    summary_table.add_row("Total P/L", f"[{pnl_color}]{pnl_sign}${portfolio.total_pnl:,.2f} ({pnl_sign}{portfolio.total_pnl_pct:.1f}%)[/{pnl_color}]")
    summary_table.add_row("Trades", f"{portfolio.trade_count} (W: {portfolio.win_count} / L: {portfolio.loss_count})")
    if portfolio.achievements:
        summary_table.add_row("Achievements", ", ".join(portfolio.achievements))
    console.print(Panel(summary_table, title="[bold]Portfolio[/bold]", border_style="green", padding=(0, 1)))

    # Positions table
    if portfolio.positions:
        pos_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold yellow")
        pos_table.add_column("Ticker")
        pos_table.add_column("Shares", justify="right")
        pos_table.add_column("Avg Price", justify="right")
        pos_table.add_column("Current", justify="right")
        pos_table.add_column("Value", justify="right")
        pos_table.add_column("P/L", justify="right")
        for pos in portfolio.positions.values():
            pos_pnl_color = "green" if pos.unrealized_pnl >= 0 else "red"
            pos_pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            pos_table.add_row(
                pos.ticker,
                f"{pos.shares:.2f}",
                f"${pos.avg_price:.2f}",
                f"${pos.current_price:.2f}",
                f"${pos.market_value:,.2f}",
                f"[{pos_pnl_color}]{pos_pnl_sign}${pos.unrealized_pnl:,.2f} ({pos_pnl_sign}{pos.unrealized_pnl_pct:.1f}%)[/{pos_pnl_color}]",
            )
        console.print(Panel(pos_table, title="[bold]Positions[/bold]", border_style="yellow", padding=(0, 1)))
    else:
        console.print("[dim]No open positions.[/dim]")


@game.group("trade")
@click.pass_context
def game_trade(ctx):
    """Execute trades in the current game session."""
    pass


def _resolve_price(ticker: str) -> Optional[float]:
    """Try to fetch the latest price for a ticker."""
    try:
        resolver = DataResolver.from_env()
        end = date.today()
        start = end - timedelta(days=5)
        prices = resolver.get_prices(ticker.upper(), start, end)
        if prices:
            return float(prices[-1].close)
    except Exception:
        pass
    return None


def _get_engine_for_trade(ctx):
    """Load the active session's engine, or print an error and return None."""
    from openquant.game import load_session, get_active_session_id

    session_id = get_active_session_id()
    if not session_id:
        if _json_output_enabled(ctx):
            _emit_json(ctx, {"command": "game_trade", "data": {"error": "No active game session. Run 'openquant game start' first."}})
        else:
            console.print("[red]No active game session.[/red] Run [bold]openquant game start[/bold] first.")
        return None, None, None

    result = load_session(session_id)
    if not result:
        if _json_output_enabled(ctx):
            _emit_json(ctx, {"command": "game_trade", "data": {"error": f"Could not load session {session_id}"}})
        else:
            console.print(f"[red]Could not load session {session_id}[/red]")
        return None, None, None

    engine, strategy = result
    return engine, session_id, strategy


@game_trade.command("buy")
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--price", "-p", type=float, default=None, help="Execution price (defaults to latest market price).")
@click.pass_context
def game_trade_buy(ctx, ticker: str, qty: float, price: Optional[float]):
    """Buy shares of a ticker."""
    from openquant.game import save_session

    engine, session_id, strategy = _get_engine_for_trade(ctx)
    if engine is None:
        return

    ticker = ticker.upper()

    if price is None:
        price = _resolve_price(ticker)
        if price is None:
            if _json_output_enabled(ctx):
                _emit_json(ctx, {"command": "game_trade", "data": {"error": f"Cannot resolve price for {ticker}. Use --price to specify."}})
            else:
                console.print(f"[red]Cannot resolve price for {ticker}.[/red] Use [bold]--price[/bold] to specify.")
            return

    result = engine.execute_trade("BUY", ticker, qty, price)
    new_achievements = engine.check_achievements()
    save_session(engine, session_id, strategy)

    if _json_output_enabled(ctx):
        _emit_json(ctx, {
            "command": "game_trade",
            "data": {
                "success": result.success,
                "action": result.action,
                "ticker": result.ticker,
                "shares": result.shares,
                "price": result.price,
                "total_cost": result.total_cost,
                "new_balance": result.new_balance,
                "position_shares": result.position_shares,
                "message": result.message,
                "new_achievements": new_achievements,
            },
        })
        return

    # --- Rich output (default) ---
    if result.success:
        console.print(Panel(
            Text.assemble(
                ("TRADE FILLED\n", "bold green"),
                (result.message, ""),
            ),
            border_style="green",
            padding=(0, 1),
        ))
    else:
        console.print(Panel(
            Text.assemble(
                ("TRADE REJECTED\n", "bold red"),
                (result.message, ""),
            ),
            border_style="red",
            padding=(0, 1),
        ))

    if new_achievements:
        for ach_name in new_achievements:
            ach = engine.achievements[ach_name]
            console.print(f"[bold yellow]Achievement Unlocked: [{ach.icon}] {ach.title} — {ach.description}[/bold yellow]")


@game_trade.command("sell")
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--price", "-p", type=float, default=None, help="Execution price (defaults to latest market price).")
@click.pass_context
def game_trade_sell(ctx, ticker: str, qty: float, price: Optional[float]):
    """Sell shares of a ticker (close a position)."""
    from openquant.game import save_session

    engine, session_id, strategy = _get_engine_for_trade(ctx)
    if engine is None:
        return

    ticker = ticker.upper()

    if price is None:
        price = _resolve_price(ticker)
        if price is None:
            if _json_output_enabled(ctx):
                _emit_json(ctx, {"command": "game_trade", "data": {"error": f"Cannot resolve price for {ticker}. Use --price to specify."}})
            else:
                console.print(f"[red]Cannot resolve price for {ticker}.[/red] Use [bold]--price[/bold] to specify.")
            return

    result = engine.execute_trade("SELL", ticker, qty, price)
    new_achievements = engine.check_achievements()
    save_session(engine, session_id, strategy)

    if _json_output_enabled(ctx):
        _emit_json(ctx, {
            "command": "game_trade",
            "data": {
                "success": result.success,
                "action": result.action,
                "ticker": result.ticker,
                "shares": result.shares,
                "price": result.price,
                "total_cost": result.total_cost,
                "new_balance": result.new_balance,
                "position_shares": result.position_shares,
                "message": result.message,
                "new_achievements": new_achievements,
            },
        })
        return

    # --- Rich output (default) ---
    if result.success:
        console.print(Panel(
            Text.assemble(
                ("TRADE FILLED\n", "bold green"),
                (result.message, ""),
            ),
            border_style="green",
            padding=(0, 1),
        ))
    else:
        console.print(Panel(
            Text.assemble(
                ("TRADE REJECTED\n", "bold red"),
                (result.message, ""),
            ),
            border_style="red",
            padding=(0, 1),
        ))

    if new_achievements:
        for ach_name in new_achievements:
            ach = engine.achievements[ach_name]
            console.print(f"[bold yellow]Achievement Unlocked: [{ach.icon}] {ach.title} — {ach.description}[/bold yellow]")


# ==================================================================
# openquant risk TICKER
# ==================================================================

@cli.command()
@click.argument("ticker")
@click.option("--days", "-d", default=252, help="Lookback in trading days.")
@click.pass_context
def risk(ctx, ticker: str, days: int):
    """Run risk assessment on a ticker."""
    ticker = ticker.upper()

    resolver = DataResolver.from_env()
    end = date.today()
    start = end - timedelta(days=days)

    prices = resolver.get_prices(ticker, start, end)
    report = _compute_basic_risk(prices)

    if _json_output_enabled(ctx):
        _emit_json(ctx, {
            "command": "risk",
            "ticker": ticker,
            "data": report if report else {},
        })
        return

    # --- Rich output (default) ---
    console.print(Panel(
        f"[bold red]Risk Assessment[/bold red] — {ticker}",
        border_style="red",
    ))

    if report:
        console.print(format_risk_panel(report, title=f"{ticker} Risk"))
    else:
        console.print("[red]Insufficient data for risk assessment.[/red]")


# ==================================================================
# openquant insider TICKER
# ==================================================================

@cli.command()
@click.argument("ticker")
@click.option("--days", "-d", default=90, help="Lookback in days.")
@click.pass_context
def insider(ctx, ticker: str, days: int):
    """Show insider trading analysis for a ticker."""
    ticker = ticker.upper()

    resolver = DataResolver.from_env()
    trades = resolver.get_insider_trades(ticker, days=days)

    if _json_output_enabled(ctx):
        data = {
            "trades": [_serialize_insider_trade(t) for t in trades] if trades else [],
        }
        if trades:
            buys = [t for t in trades if t.transaction_type == "BUY"]
            sells = [t for t in trades if t.transaction_type == "SELL"]
            buy_value = sum(t.value for t in buys)
            sell_value = sum(t.value for t in sells)
            sentiment = "BULLISH" if buy_value > sell_value else "BEARISH" if sell_value > buy_value else "NEUTRAL"
            data["summary"] = {
                "buy_transactions": len(buys),
                "sell_transactions": len(sells),
                "total_buy_value": buy_value,
                "total_sell_value": sell_value,
                "net_sentiment": sentiment,
            }
        _emit_json(ctx, {
            "command": "insider",
            "ticker": ticker,
            "data": data,
        })
        return

    # --- Rich output (default) ---
    console.print(Panel(
        f"[bold magenta]Insider Trading[/bold magenta] — {ticker}",
        border_style="magenta",
    ))

    if trades:
        console.print(format_insider_panel(trades, title=f"{ticker} Insider Trades"))

        # Summary stats
        buys = [t for t in trades if t.transaction_type == "BUY"]
        sells = [t for t in trades if t.transaction_type == "SELL"]
        buy_value = sum(t.value for t in buys)
        sell_value = sum(t.value for t in sells)

        summary = Table(box=box.SIMPLE, show_header=False)
        summary.add_column("Key", style="bold")
        summary.add_column("Value")
        summary.add_row("Buy Transactions", str(len(buys)))
        summary.add_row("Sell Transactions", str(len(sells)))
        summary.add_row("Total Buy Value", f"${buy_value:,.0f}")
        summary.add_row("Total Sell Value", f"${sell_value:,.0f}")
        summary.add_row("Net Sentiment", Text(
            "BULLISH" if buy_value > sell_value else "BEARISH" if sell_value > buy_value else "NEUTRAL",
            style="green" if buy_value > sell_value else "red" if sell_value > buy_value else "yellow",
        ))
        console.print(Panel(summary, title="[bold]Summary[/bold]", border_style="magenta", padding=(0, 1)))
    else:
        console.print("[dim]No insider trade data available.[/dim]")


# ==================================================================
# openquant analyze TICKER
# ==================================================================

@cli.command()
@click.argument("ticker")
@click.option("--days", "-d", default=90, help="Lookback period in days.")
@click.pass_context
def analyze(ctx, ticker: str, days: int):
    """Full AI analysis of a ticker."""
    ticker = ticker.upper()

    resolver = DataResolver.from_env()
    end = date.today()
    start = end - timedelta(days=days)

    prices = resolver.get_prices(ticker, start, end)
    trades = resolver.get_insider_trades(ticker, days=days)
    estimates = resolver.get_analyst_estimates(ticker)
    info = resolver.get_company_info(ticker)
    signals = _generate_signals(prices, trades, estimates)

    if _json_output_enabled(ctx):
        data = {}
        if info:
            data["company_info"] = _serialize_company_info(info)
        data["prices"] = [_serialize_price(p) for p in prices] if prices else []
        data["insider_trades"] = [_serialize_insider_trade(t) for t in trades] if trades else []
        data["analyst_estimates"] = [_serialize_estimate(e) for e in estimates] if estimates else []
        data["signals"] = signals if signals else []
        _emit_json(ctx, {
            "command": "analyze",
            "ticker": ticker,
            "data": data,
        })
        return

    # --- Rich output (default) ---
    console.print(Panel(
        f"[bold yellow]AI Analysis[/bold yellow] — {ticker}",
        border_style="yellow",
    ))

    # Show data panels
    if info:
        console.print(Panel(
            f"[bold]{info.name}[/bold] | Sector: {info.sector or 'N/A'} | Industry: {info.industry or 'N/A'}",
            border_style="cyan",
        ))

    if prices:
        console.print(format_price_panel(prices, title=f"{ticker} Prices"))

    if trades:
        console.print(format_insider_panel(trades, title=f"{ticker} Insider"))

    if signals:
        console.print(format_analysis_panel(signals, title=f"{ticker} AI Signals"))
    else:
        console.print("[dim]Insufficient data for AI analysis.[/dim]")


# ==================================================================
# Internal helpers
# ==================================================================

def _compute_basic_risk(prices) -> dict:
    """Compute basic risk metrics from price data.

    Returns a dict with volatility, max_drawdown, sharpe_ratio, etc.
    """
    if not prices or len(prices) < 5:
        return {}

    try:
        import numpy as np

        closes = [p.close for p in prices]
        returns = np.diff(closes) / closes[:-1]
        returns = returns[~np.isnan(returns)]

        if len(returns) < 2:
            return {}

        volatility = float(np.std(returns) * np.sqrt(252)) * 100  # annualized %
        max_dd = _max_drawdown(closes)
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0.0
        var_95 = float(np.percentile(returns, 5) * 100) if len(returns) > 10 else 0.0
        beta = 1.0  # Would need market data to compute properly

        # Overall rating
        if volatility < 20 and max_dd < 15:
            rating = "Low"
        elif volatility < 35 and max_dd < 30:
            rating = "Medium"
        else:
            rating = "High"

        warnings = []
        if max_dd > 30:
            warnings.append("Max drawdown exceeds 30%")
        if volatility > 40:
            warnings.append("High volatility (>40%)")

        return {
            "volatility": round(volatility, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "var_95": round(var_95, 2),
            "beta": round(beta, 2),
            "overall_rating": rating,
            "warnings": warnings,
        }
    except ImportError:
        return {}
    except Exception as exc:
        logger.error("Risk computation error: %s", exc)
        return {}


def _max_drawdown(closes: list) -> float:
    """Compute max drawdown percentage from a list of closing prices."""
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _generate_signals(prices, trades, estimates) -> list:
    """Generate simple heuristic trading signals based on data.

    This is a placeholder until the full AI agent system is implemented.
    """
    if not prices or len(prices) < 5:
        return []

    signals = []

    # Insider sentiment signal
    if trades:
        buys = sum(1 for t in trades if t.transaction_type == "BUY")
        sells = sum(1 for t in trades if t.transaction_type == "SELL")
        if buys + sells > 0:
            ratio = buys / (buys + sells)
            sig = "BUY" if ratio > 0.6 else "SELL" if ratio < 0.4 else "HOLD"
            signals.append({
                "agent": "InsiderSentiment",
                "signal": sig,
                "confidence": ratio if sig == "BUY" else 1 - ratio if sig == "SELL" else 0.5,
                "reasoning": f"{buys} buys vs {sells} sells in last 90d",
            })

    # Momentum signal
    try:
        import numpy as np
        closes = [p.close for p in prices]
        if len(closes) >= 20:
            ma20 = np.mean(closes[-20:])
            current = closes[-1]
            if current > ma20 * 1.02:
                sig = "BUY"
                conf = min((current / ma20 - 1) * 10, 0.9)
            elif current < ma20 * 0.98:
                sig = "SELL"
                conf = min((1 - current / ma20) * 10, 0.9)
            else:
                sig = "HOLD"
                conf = 0.5
            signals.append({
                "agent": "Momentum",
                "signal": sig,
                "confidence": round(conf, 2),
                "reasoning": f"Price {'above' if current > ma20 else 'below'} 20d MA",
            })
    except ImportError:
        pass

    # Analyst consensus signal
    if estimates:
        eps_est = [e for e in estimates if e.estimate_type == "eps"]
        if eps_est:
            avg = eps_est[0].consensus_avg
            low = eps_est[0].consensus_low
            high = eps_est[0].consensus_high
            spread = high - low
            if avg > 0 and spread > 0:
                conf = min(eps_est[0].number_of_analysts / 20, 0.9)
                signals.append({
                    "agent": "AnalystConsensus",
                    "signal": "BUY" if avg > (low + high) / 2 else "HOLD",
                    "confidence": round(conf, 2),
                    "reasoning": f"EPS est {avg:.2f} ({eps_est[0].number_of_analysts} analysts)",
                })

    return signals


# ==================================================================
# openquant tui
# ==================================================================

@cli.command()
@click.option("--mode", "-m", default="paper", type=click.Choice(["paper", "game", "live"]), help="Trading mode.")
def tui(mode: str):
    """Launch the OpenQuant Textual TUI (sentient Bloomberg terminal)."""
    resolver = DataResolver.from_env()
    broker = None

    if mode in ("paper", "game"):
        from openquant.brokers.paper import PaperBroker
        broker = PaperBroker(starting_balance=10000.0)

    try:
        from openquant.tui.app import run_tui
        run_tui(broker=broker, resolver=resolver, mode=mode)
    except ImportError as exc:
        console.print(f"[red]TUI dependencies not installed: {exc}[/red]")
        console.print("[dim]Install with: pip3 install textual asciichartpy[/dim]")
        sys.exit(1)


# ==================================================================
# openquant chat
# ==================================================================

@cli.command()
@click.option("--model", default=None, help="LLM model to use (e.g. openai/gpt-4o-mini).")
@click.option("--mode", "-m", "trading_mode", default="paper", type=click.Choice(["paper", "game", "live"]), help="Trading mode.")
def chat(model: Optional[str], trading_mode: str):
    """Launch the AI agent chat in terminal (non-TUI)."""
    from openquant.agent.loop import run_agent_terminal, AgentLoop, EventType
    from openquant.agent.providers import get_default_model

    resolver = DataResolver.from_env()
    broker = None

    if trading_mode in ("paper", "game"):
        from openquant.brokers.paper import PaperBroker
        broker = PaperBroker(starting_balance=10000.0)

    model_str = model or get_default_model()

    console.print(Panel(
        f"[bold cyan]OpenQuant Chat[/bold cyan]\n"
        f"Model: {model_str}\n"
        f"Mode: {trading_mode}\n"
        f"Type 'quit' to exit, 'help' for commands",
        border_style="cyan",
    ))

    agent = AgentLoop(
        model=model_str,
        broker=broker,
        resolver=resolver,
        mode=trading_mode,
    )

    while True:
        try:
            user_input = console.input("[bold green]> [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() == "help":
            console.print(Panel(
                "Commands:\n"
                "  Analyze TICKER — Full stock analysis\n"
                "  Buy/SELL TICKER SHARES — Place order\n"
                "  Portfolio — Show portfolio summary\n"
                "  Risk TICKER — Risk assessment\n"
                "  Quit — Exit chat",
                title="Help",
                border_style="yellow",
            ))
            continue

        # Run the agent
        console.print()
        try:
            asyncio.run(_run_chat_turn(agent, user_input))
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
        console.print()


async def _run_chat_turn(agent, user_message: str) -> None:
    """Run a single chat turn and print events."""
    from openquant.agent.loop import EventType

    streaming_text = ""
    async for event in agent.run(user_message):
        if event.type == EventType.TEXT:
            console.print(event.data, end="")
            streaming_text += event.data
        elif event.type == EventType.TEXT_DONE:
            if streaming_text:
                console.print()  # Newline
            streaming_text = ""
        elif event.type == EventType.TOOL_CALL_START:
            console.print(f"\n  [bold yellow]Calling {event.tool_name}...[/bold yellow]")
        elif event.type == EventType.TOOL_RESULT:
            result = event.data
            if isinstance(result, (dict, list)):
                result_str = json.dumps(result, indent=2, default=str)[:500]
            else:
                result_str = str(result)[:500]
            console.print(f"  [dim]Result: {result_str}[/dim]")
        elif event.type == EventType.BLOCKED:
            console.print(f"\n  [bold red]BLOCKED: {event.data}[/bold red]")
        elif event.type == EventType.ERROR:
            console.print(f"\n  [red]ERROR: {event.data}[/red]")
        elif event.type == EventType.TURN_COMPLETE:
            if event.data and not streaming_text:
                console.print(event.data)
