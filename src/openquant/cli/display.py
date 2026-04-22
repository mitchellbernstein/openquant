"""Rich display helpers for the OpenQuant CLI.

Each function returns a Rich Panel containing a formatted Table,
ready to be printed via the Rich Console.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from openquant.data.protocol import Price, InsiderTrade


# ------------------------------------------------------------------
# Price panel
# ------------------------------------------------------------------

def format_price_panel(prices: List[Price], title: str = "Price History") -> Panel:
    """Build a Rich Panel with a table of OHLCV price data."""
    table = Table(
        title=None,
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        pad_edge=False,
    )
    table.add_column("Date", style="dim")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right", style="green")
    table.add_column("Low", justify="right", style="red")
    table.add_column("Close", justify="right", style="bold")
    table.add_column("Volume", justify="right", style="dim")

    for p in prices[-30:]:  # Show last 30 rows at most
        table.add_row(
            str(p.date),
            f"{p.open:,.2f}",
            f"{p.high:,.2f}",
            f"{p.low:,.2f}",
            f"{p.close:,.2f}",
            f"{p.volume:,}",
        )

    return Panel(table, title=f"[bold]{title}[/bold]", border_style="blue", padding=(0, 1))


# ------------------------------------------------------------------
# Insider trades panel
# ------------------------------------------------------------------

def format_insider_panel(trades: List[InsiderTrade], title: str = "Insider Trades") -> Panel:
    """Build a Rich Panel with a table of insider transactions."""
    table = Table(
        title=None,
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold magenta",
        pad_edge=False,
    )
    table.add_column("Date", style="dim")
    table.add_column("Insider", style="bold")
    table.add_column("Title", style="dim", max_width=20)
    table.add_column("Type", justify="center")
    table.add_column("Shares", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Value", justify="right", style="bold")
    table.add_column("Source", style="dim")

    for t in trades[:25]:  # Cap display
        type_style = "green" if t.transaction_type == "BUY" else "red" if t.transaction_type == "SELL" else "yellow"
        table.add_row(
            str(t.date),
            t.insider_name[:25],
            t.title[:20],
            Text(t.transaction_type, style=type_style),
            f"{t.shares:,}",
            f"{t.price:,.2f}",
            f"${t.value:,.0f}",
            t.source,
        )

    return Panel(table, title=f"[bold]{title}[/bold]", border_style="magenta", padding=(0, 1))


# ------------------------------------------------------------------
# Risk panel
# ------------------------------------------------------------------

def format_risk_panel(risk_report: Dict[str, Any], title: str = "Risk Assessment") -> Panel:
    """Build a Rich Panel displaying risk metrics.

    Expected *risk_report* keys (all optional):
        volatility, max_drawdown, sharpe_ratio, var_95, beta,
        overall_rating, warnings (list of str)
    """
    table = Table(
        title=None,
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold red",
        pad_edge=False,
    )
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    metrics = [
        ("Volatility", risk_report.get("volatility"), "%"),
        ("Max Drawdown", risk_report.get("max_drawdown"), "%"),
        ("Sharpe Ratio", risk_report.get("sharpe_ratio"), ""),
        ("VaR (95%)", risk_report.get("var_95"), "%"),
        ("Beta", risk_report.get("beta"), ""),
    ]

    for name, val, suffix in metrics:
        if val is not None:
            display = f"{val:.2f}{suffix}" if isinstance(val, (int, float)) else str(val)
            table.add_row(name, display)

    # Overall rating
    rating = risk_report.get("overall_rating", "")
    if rating:
        rating_style = _risk_rating_style(rating)
        table.add_row("Overall Rating", Text(rating, style=rating_style))

    # Warnings
    warnings = risk_report.get("warnings", [])
    if warnings:
        table.add_row("Warnings", f"{len(warnings)} issues")
        for w in warnings[:5]:
            table.add_row("", f"  - {w}", style="yellow")

    return Panel(table, title=f"[bold]{title}[/bold]", border_style="red", padding=(0, 1))


# ------------------------------------------------------------------
# Analysis panel (agent signals)
# ------------------------------------------------------------------

def format_analysis_panel(signals: List[Dict[str, Any]], title: str = "AI Analysis") -> Panel:
    """Build a Rich Panel displaying agent signals.

    Each signal dict expected keys: agent, signal, confidence, reasoning
    """
    table = Table(
        title=None,
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold yellow",
        pad_edge=False,
    )
    table.add_column("Agent", style="bold")
    table.add_column("Signal", justify="center")
    table.add_column("Confidence", justify="right")
    table.add_column("Reasoning", max_width=50)

    for sig in signals[:10]:
        signal_val = str(sig.get("signal", "")).upper()
        signal_style = "green" if "BUY" in signal_val else "red" if "SELL" in signal_val else "yellow"
        confidence = sig.get("confidence", 0)
        if isinstance(confidence, (int, float)):
            conf_str = f"{confidence:.0%}"
        else:
            conf_str = str(confidence)

        table.add_row(
            str(sig.get("agent", "")),
            Text(signal_val, style=signal_style),
            conf_str,
            str(sig.get("reasoning", ""))[:50],
        )

    return Panel(table, title=f"[bold]{title}[/bold]", border_style="yellow", padding=(0, 1))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _risk_rating_style(rating: str) -> str:
    """Map risk rating text to a Rich style string."""
    r = rating.lower()
    if r in ("low", "safe", "conservative"):
        return "bold green"
    elif r in ("medium", "moderate"):
        return "bold yellow"
    elif r in ("high", "risky", "aggressive"):
        return "bold red"
    return "bold white"
