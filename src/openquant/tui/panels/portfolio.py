"""Portfolio panel for OpenQuant TUI.

Shows:
  - Position table with P&L
  - Total portfolio value
  - Game mode stats

Data comes from the connected broker (paper by default).
"""

from __future__ import annotations

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Label, Static

logger = logging.getLogger(__name__)


class PortfolioPanel(Vertical):
    """Portfolio panel showing positions, P&L, and account summary."""

    CSS = """
    PortfolioPanel {
        height: 100%;
        padding: 0 1;
    }

    #portfolio-title {
        text-style: bold;
        color: $text;
        margin: 0 0 1 0;
    }

    #portfolio-summary {
        margin: 0 0 1 0;
        height: auto;
    }

    #portfolio-table {
        height: 1fr;
    }

    #portfolio-stats {
        margin: 1 0 0 0;
        height: auto;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        broker=None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.broker = broker

    def compose(self) -> ComposeResult:
        yield Label("Portfolio", id="portfolio-title")
        yield Static(self._get_summary(), id="portfolio-summary")
        table = DataTable(id="portfolio-table")
        table.add_columns("Ticker", "Shares", "Avg Price", "Current", "Mkt Value", "P&L", "P&L %")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table
        yield Static(self._get_stats(), id="portfolio-stats")

    def on_mount(self) -> None:
        """Populate on mount."""
        self._refresh_data()

    def _get_summary(self) -> str:
        """Get portfolio summary text."""
        if not self.broker:
            return "No broker connected. Using paper broker with $10,000 starting balance."

        try:
            total = self.broker.get_total_value()
            cash = self.broker.get_balance()
            positions = self.broker.get_positions()
            total_pnl = total - 10000.0
            pnl_pct = (total_pnl / 10000.0) * 100

            return (
                f"**Total Value**: ${total:,.2f}  |  "
                f"**Cash**: ${cash:,.2f}  |  "
                f"**P&L**: ${total_pnl:+,.2f} ({pnl_pct:+.2f}%)  |  "
                f"**Positions**: {len(positions)}"
            )
        except Exception:
            return "Error loading portfolio data."

    def _get_stats(self) -> str:
        """Get game mode / trading stats."""
        if not self.broker:
            return "Start a game session to track stats"

        try:
            trades = self.broker.get_trade_history()
            total_value = self.broker.get_total_value()
            starting = 10000.0  # Default starting balance

            wins = 0
            losses = 0
            for t in trades:
                if t.get("action") == "SELL":
                    pnl = t.get("realized_pnl", 0)
                    if pnl > 0:
                        wins += 1
                    elif pnl < 0:
                        losses += 1

            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

            return (
                f"Trades: {total_trades}  |  "
                f"Wins: {wins}  |  Losses: {losses}  |  "
                f"Win Rate: {win_rate:.1f}%  |  "
                f"Return: {((total_value - starting) / starting * 100):+.2f}%"
            )
        except Exception:
            return "Stats unavailable"

    def _refresh_data(self) -> None:
        """Refresh all portfolio data."""
        try:
            # Update summary
            self.query_one("#portfolio-summary", Static).update(self._get_summary())

            # Update table
            table = self.query_one("#portfolio-table", DataTable)
            table.clear()

            if self.broker:
                positions = self.broker.get_positions()
                for pos in positions:
                    pnl_pct = ((pos.current_price - pos.avg_price) / pos.avg_price * 100) if pos.avg_price else 0
                    label = "price-up" if pos.unrealized_pnl >= 0 else "price-down"
                    table.add_row(
                        pos.ticker,
                        str(pos.shares),
                        f"${pos.avg_price:.2f}",
                        f"${pos.current_price:.2f}",
                        f"${pos.market_value:,.2f}",
                        f"${pos.unrealized_pnl:+,.2f}",
                        f"{pnl_pct:+.2f}%",
                        label=label,
                    )
            else:
                # Mock positions
                mock_positions = [
                    ("AAPL", 10, 170.00, 178.50),
                    ("NVDA", 5, 480.00, 495.50),
                    ("MSFT", 8, 370.00, 378.90),
                ]
                for ticker, shares, avg, current in mock_positions:
                    mv = shares * current
                    pnl = (current - avg) * shares
                    pnl_pct = ((current - avg) / avg) * 100
                    label = "price-up" if pnl >= 0 else "price-down"
                    table.add_row(
                        ticker, str(shares), f"${avg:.2f}",
                        f"${current:.2f}", f"${mv:,.2f}",
                        f"${pnl:+,.2f}", f"{pnl_pct:+.2f}%",
                        label=label,
                    )

            # Update stats
            self.query_one("#portfolio-stats", Static).update(self._get_stats())

        except Exception as exc:
            logger.error("Portfolio refresh error: %s", exc)

    def refresh_data(self) -> None:
        """Public refresh method."""
        self._refresh_data()
