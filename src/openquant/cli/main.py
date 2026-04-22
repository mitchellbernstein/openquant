"""OpenQuant CLI - command-line interface powered by Click and Rich."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import date, timedelta
from typing import Optional

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
# Root group
# ==================================================================

@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose/debug logging.")
@click.version_option(version="0.1.0", prog_name="openquant")
@click.pass_context
def cli(ctx, verbose):
    """OpenQuant - The open-source operating system for quant trading."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    if verbose:
        logging.basicConfig(level=logging.DEBUG)


# ==================================================================
# openquant run TICKER
# ==================================================================

@cli.command()
@click.argument("ticker")
@click.option("--days", "-d", default=90, help="Lookback period in days.")
@click.option("--provider", "-p", default=None, help="Force a specific data provider.")
def run(ticker: str, days: int, provider: Optional[str]):
    """Run full analysis on a ticker.

    Shows prices, insider trades, analyst estimates, and risk assessment.
    """
    console.print(Panel(
        f"[bold cyan]OpenQuant[/bold cyan] — Running full analysis for [bold]{ticker.upper()}[/bold]",
        border_style="cyan",
    ))

    resolver = DataResolver.from_env()
    end = date.today()
    start = end - timedelta(days=days)

    # Fetch data
    with console.status("[bold green]Fetching price data..."):
        prices = resolver.get_prices(ticker.upper(), start, end)

    with console.status("[bold magenta]Fetching insider trades..."):
        trades = resolver.get_insider_trades(ticker.upper(), days=days)

    with console.status("[bold yellow]Fetching analyst estimates..."):
        estimates = resolver.get_analyst_estimates(ticker.upper())

    with console.status("[bold blue]Fetching company info..."):
        info = resolver.get_company_info(ticker.upper())

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
        console.print(format_price_panel(prices, title=f"{ticker.upper()} Prices"))
    else:
        console.print("[dim]No price data available.[/dim]")

    # Display insider trades
    if trades:
        console.print(format_insider_panel(trades, title=f"{ticker.upper()} Insider Trades"))
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
        console.print(Panel(est_table, title=f"[bold]{ticker.upper()} Analyst Estimates[/bold]", border_style="yellow", padding=(0, 1)))
    else:
        console.print("[dim]No analyst estimate data available.[/dim]")

    # Risk assessment (placeholder — full risk engine not yet implemented)
    risk_report = _compute_basic_risk(prices)
    if risk_report:
        console.print(format_risk_panel(risk_report, title=f"{ticker.upper()} Risk"))
    else:
        console.print("[dim]Insufficient data for risk assessment.[/dim]")


# ==================================================================
# openquant strategy list / strategy run
# ==================================================================

@cli.group()
def strategy():
    """Manage and run trading strategies."""
    pass


@strategy.command("list")
def strategy_list():
    """List available strategies."""
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold green")
    table.add_column("Strategy", style="bold")
    table.add_column("Description")

    # These come from the entry_points in pyproject.toml
    known_strategies = [
        ("insider-momentum", "Trade on insider buying momentum signals"),
        ("value-deep", "Deep value investing based on fundamentals"),
        ("earnings-surge", "Capture post-earnings announcement drift"),
        ("technical-breakout", "Breakout-based technical trading"),
    ]
    for name, desc in known_strategies:
        table.add_row(name, desc)

    console.print(Panel(table, title="[bold]Available Strategies[/bold]", border_style="green", padding=(0, 1)))


@strategy.command("run")
@click.argument("name")
@click.option("--ticker", "-t", required=True, help="Ticker symbol to trade.")
@click.option("--mode", "-m", default="paper", type=click.Choice(["paper", "game", "live"]), help="Execution mode.")
def strategy_run(name: str, ticker: str, mode: str):
    """Run a named strategy on a ticker."""
    console.print(Panel(
        f"Running [bold]{name}[/bold] on [bold]{ticker.upper()}[/bold] in [bold]{mode}[/bold] mode",
        border_style="green",
    ))

    resolver = DataResolver.from_env()
    end = date.today()
    start = end - timedelta(days=90)

    with console.status("[bold green]Loading data..."):
        prices = resolver.get_prices(ticker.upper(), start, end)
        trades = resolver.get_insider_trades(ticker.upper())

    if not prices:
        console.print("[red]No price data available — cannot run strategy.[/red]")
        return

    console.print(format_price_panel(prices, title=f"{ticker.upper()} Data"))
    if trades:
        console.print(format_insider_panel(trades, title=f"{ticker.upper()} Insider"))

    console.print(f"\n[bold green]Strategy '{name}' initialized.[/bold green] Execution mode: {mode}")
    # TODO: wire up actual strategy execution once strategy classes are implemented


# ==================================================================
# openquant game start
# ==================================================================

@cli.group()
def game():
    """Game mode - practice trading with virtual capital."""
    pass


@game.command("start")
@click.option("--strategy", "-s", default="insider-momentum", help="Strategy to use.")
@click.option("--balance", "-b", default=10000.0, type=float, help="Starting balance.")
def game_start(strategy: str, balance: float):
    """Start a game-mode trading session."""
    console.print(Panel(
        Text.assemble(
            ("Game Mode\n", "bold cyan"),
            (f"Strategy: {strategy}\n", "bold"),
            (f"Starting Balance: ${balance:,.2f}\n", "bold green"),
            ("Paper trading — no real money at risk.", "dim"),
        ),
        border_style="cyan",
        padding=(1, 2),
    ))
    # TODO: wire up game loop once game engine is implemented
    console.print("[dim]Game engine not yet implemented. Coming soon![/dim]")


# ==================================================================
# openquant risk TICKER
# ==================================================================

@cli.command()
@click.argument("ticker")
@click.option("--days", "-d", default=252, help="Lookback in trading days.")
def risk(ticker: str, days: int):
    """Run risk assessment on a ticker."""
    console.print(Panel(
        f"[bold red]Risk Assessment[/bold red] — {ticker.upper()}",
        border_style="red",
    ))

    resolver = DataResolver.from_env()
    end = date.today()
    start = end - timedelta(days=days)

    with console.status("[bold red]Computing risk metrics..."):
        prices = resolver.get_prices(ticker.upper(), start, end)

    report = _compute_basic_risk(prices)
    if report:
        console.print(format_risk_panel(report, title=f"{ticker.upper()} Risk"))
    else:
        console.print("[red]Insufficient data for risk assessment.[/red]")


# ==================================================================
# openquant insider TICKER
# ==================================================================

@cli.command()
@click.argument("ticker")
@click.option("--days", "-d", default=90, help="Lookback in days.")
def insider(ticker: str, days: int):
    """Show insider trading analysis for a ticker."""
    console.print(Panel(
        f"[bold magenta]Insider Trading[/bold magenta] — {ticker.upper()}",
        border_style="magenta",
    ))

    resolver = DataResolver.from_env()

    with console.status("[bold magenta]Fetching insider trades..."):
        trades = resolver.get_insider_trades(ticker.upper(), days=days)

    if trades:
        console.print(format_insider_panel(trades, title=f"{ticker.upper()} Insider Trades"))

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
def analyze(ticker: str, days: int):
    """Full AI analysis of a ticker."""
    console.print(Panel(
        f"[bold yellow]AI Analysis[/bold yellow] — {ticker.upper()}",
        border_style="yellow",
    ))

    resolver = DataResolver.from_env()
    end = date.today()
    start = end - timedelta(days=days)

    with console.status("[bold green]Gathering data..."):
        prices = resolver.get_prices(ticker.upper(), start, end)
        trades = resolver.get_insider_trades(ticker.upper(), days=days)
        estimates = resolver.get_analyst_estimates(ticker.upper())
        info = resolver.get_company_info(ticker.upper())

    # Show data panels
    if info:
        console.print(Panel(
            f"[bold]{info.name}[/bold] | Sector: {info.sector or 'N/A'} | Industry: {info.industry or 'N/A'}",
            border_style="cyan",
        ))

    if prices:
        console.print(format_price_panel(prices, title=f"{ticker.upper()} Prices"))

    if trades:
        console.print(format_insider_panel(trades, title=f"{ticker.upper()} Insider"))

    # Generate placeholder agent signals
    signals = _generate_signals(prices, trades, estimates)
    if signals:
        console.print(format_analysis_panel(signals, title=f"{ticker.upper()} AI Signals"))
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
