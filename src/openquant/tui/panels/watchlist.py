"""Watchlist panel for OpenQuant TUI.

Shows a DataTable of tickers with:
  - Ticker symbol
  - Current price
  - Change %
  - Color-coded green/red

Data is mock for now; will connect to QuantFetch later.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Label, Static

from openquant.data.protocol import Price  # noqa: F401 - used in type hints

logger = logging.getLogger(__name__)

# ── Mock data for initial display ──────────────────────────────────────────

MOCK_WATCHLIST = [
    ("AAPL", 178.50, 1.23),
    ("GOOGL", 141.80, -0.45),
    ("MSFT", 378.90, 0.87),
    ("TSLA", 245.20, -1.56),
    ("NVDA", 495.50, 3.21),
    ("AMZN", 178.30, 0.34),
    ("META", 356.00, 1.89),
    ("JPM", 172.40, -0.22),
]


class WatchlistPanel(Vertical):
    """Watchlist panel showing ticker prices and changes."""

    CSS = """
    WatchlistPanel {
        height: 100%;
        padding: 0 1;
    }

    #watchlist-title {
        text-style: bold;
        color: $text;
        margin: 0 0 1 0;
    }

    #watchlist-table {
        height: 1fr;
    }
    """

    tickers: reactive[list] = reactive([])

    def __init__(
        self,
        resolver=None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.resolver = resolver
        self._initial_tickers = list(MOCK_WATCHLIST)

    def compose(self) -> ComposeResult:
        yield Label("Watchlist", id="watchlist-title")
        table = DataTable(id="watchlist-table")
        table.add_columns("Ticker", "Price", "Change %", "Volume")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table

    def on_mount(self) -> None:
        """Populate the table on mount."""
        self._populate_table()

    def _populate_table(self) -> None:
        """Fill the table with data."""
        try:
            table = self.query_one("#watchlist-table", DataTable)
            table.clear()

            if self.resolver:
                # Try to get real data
                for ticker, _, _ in self._initial_tickers:
                    try:
                        prices = self.resolver.get_prices(
                            ticker,
                            date.today() - timedelta(days=5),
                            date.today(),
                        )
                        if prices and len(prices) >= 2:
                            last = prices[-1]
                            prev = prices[-2]
                            change_pct = ((last.close - prev.close) / prev.close) * 100
                            label = "price-up" if change_pct >= 0 else "price-down"
                            table.add_row(
                                ticker,
                                f"${last.close:.2f}",
                                f"{change_pct:+.2f}%",
                                str(last.volume) if hasattr(last, 'volume') else "-",
                                label=label,
                            )
                            continue
                    except Exception:
                        pass

            # Fallback to mock data
            for ticker, price, change in self._initial_tickers:
                label = "price-up" if change >= 0 else "price-down"
                table.add_row(
                    ticker,
                    f"${price:.2f}",
                    f"{change:+.2f}%",
                    "-",
                    label=label,
                )
        except Exception as exc:
            logger.error("Watchlist populate error: %s", exc)

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the watchlist."""
        # Check if already present
        for t, _, _ in self._initial_tickers:
            if t == ticker:
                return

        self._initial_tickers.append((ticker, 0.0, 0.0))

        # Try to get price
        price = 0.0
        change = 0.0
        if self.resolver:
            try:
                prices = self.resolver.get_prices(
                    ticker,
                    date.today() - timedelta(days=5),
                    date.today(),
                )
                if prices and len(prices) >= 2:
                    price = prices[-1].close
                    change = ((prices[-1].close - prices[-2].close) / prices[-2].close) * 100
            except Exception:
                pass

        self._initial_tickers[-1] = (ticker, price, change)
        self._populate_table()

    def refresh_data(self) -> None:
        """Refresh all watchlist data."""
        self._populate_table()
