"""Ticker Detail panel for OpenQuant TUI.

Shows:
  - Price display + sparkline (asciichart)
  - Key metrics (P/E, market cap, volume)
  - Strategy signals

Data is mock/yfinance for now.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import DataTable, Label, Markdown, Static

logger = logging.getLogger(__name__)


class TickerDetailPanel(Vertical):
    """Ticker detail panel with price, metrics, and signals."""

    CSS = """
    TickerDetailPanel {
        height: 100%;
        padding: 0 1;
    }

    #detail-title {
        text-style: bold;
        color: $text;
        margin: 0 0 1 0;
    }

    #detail-sparkline {
        color: $success;
        margin: 0 0 1 0;
        height: auto;
    }

    #detail-metrics {
        margin: 0 0 1 0;
        height: auto;
    }

    #detail-signals {
        margin: 0 0 1 0;
        height: auto;
    }
    """

    def __init__(
        self,
        resolver=None,
        ticker: str = "AAPL",
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.resolver = resolver
        self._ticker = ticker

    def compose(self) -> ComposeResult:
        yield Label(f"Ticker Detail: {self._ticker}", id="detail-title")
        yield Static(self._get_sparkline(), id="detail-sparkline")
        yield Static(self._get_metrics(), id="detail-metrics")
        yield Static(self._get_signals(), id="detail-signals")

    def _get_sparkline(self) -> str:
        """Generate an ASCII sparkline for the ticker."""
        prices = []

        if self.resolver:
            try:
                price_data = self.resolver.get_prices(
                    self._ticker,
                    date.today() - timedelta(days=30),
                    date.today(),
                )
                if price_data:
                    prices = [p.close for p in price_data]
            except Exception:
                pass

        if not prices:
            # Mock data
            prices = [
                150, 152, 149, 153, 155, 154, 156, 158,
                157, 159, 161, 160, 162, 164, 163, 165,
                167, 166, 168, 170, 169, 171, 173, 172,
                174, 176, 175, 177, 178, 180,
            ]

        try:
            from asciichartpy import plot
            chart = plot(prices, {"height": 8})
            return f"```\n{chart}\n```"
        except ImportError:
            # Fallback to simple sparkline
            return self._simple_sparkline(prices)

    def _simple_sparkline(self, prices: list) -> str:
        """Generate a simple Unicode sparkline."""
        if not prices:
            return "No data"

        chars = "▁▂▃▄▅▆▇█"
        min_p = min(prices)
        max_p = max(prices)
        range_p = max_p - min_p if max_p > min_p else 1

        sparkline = ""
        for p in prices[-50:]:  # Last 50 points
            idx = int((p - min_p) / range_p * (len(chars) - 1))
            sparkline += chars[idx]

        return f"${prices[-1]:.2f}  {sparkline}"

    def _get_metrics(self) -> str:
        """Get key metrics display."""
        metrics = {}

        if self.resolver:
            try:
                info = self.resolver.get_company_info(self._ticker)
                if info:
                    metrics["Name"] = info.name
                    metrics["Sector"] = info.sector or "N/A"
                    metrics["Industry"] = info.industry or "N/A"
                    metrics["Market Cap"] = f"${info.market_cap:,.0f}" if info.market_cap else "N/A"

                price_data = self.resolver.get_prices(
                    self._ticker,
                    date.today() - timedelta(days=5),
                    date.today(),
                )
                if price_data:
                    last = price_data[-1]
                    metrics["Last Price"] = f"${last.close:.2f}"
                    metrics["Volume"] = f"{last.volume:,.0f}" if hasattr(last, 'volume') and last.volume else "N/A"

                from openquant.cli.main import _compute_basic_risk
                prices = self.resolver.get_prices(
                    self._ticker,
                    date.today() - timedelta(days=252),
                    date.today(),
                )
                risk = _compute_basic_risk(prices)
                if risk:
                    metrics["Volatility"] = f"{risk.get('volatility', 'N/A')}%"
                    metrics["Max Drawdown"] = f"{risk.get('max_drawdown', 'N/A')}%"
                    metrics["Sharpe Ratio"] = str(risk.get('sharpe_ratio', 'N/A'))
                    metrics["Risk Rating"] = risk.get('overall_rating', 'N/A')
            except Exception:
                pass

        if not metrics:
            metrics = {
                "Name": "Apple Inc.",
                "Sector": "Technology",
                "Market Cap": "$2,800,000,000,000",
                "P/E": "28.5",
                "Last Price": "$178.50",
                "Volume": "52,300,000",
                "52w High": "$199.62",
                "52w Low": "$124.17",
                "Volatility": "22.3%",
                "Sharpe Ratio": "1.45",
                "Risk Rating": "Medium",
            }

        lines = ["## Key Metrics", ""]
        for key, value in metrics.items():
            lines.append(f"  **{key}**: {value}")

        return "\n".join(lines)

    def _get_signals(self) -> str:
        """Get strategy signals display."""
        signals = []

        if self.resolver:
            try:
                from datetime import date, timedelta
                prices = self.resolver.get_prices(
                    self._ticker,
                    date.today() - timedelta(days=90),
                    date.today(),
                )
                trades = self.resolver.get_insider_trades(self._ticker)
                estimates = self.resolver.get_analyst_estimates(self._ticker)
                from openquant.cli.main import _generate_signals
                signals = _generate_signals(prices, trades, estimates)
            except Exception:
                pass

        if not signals:
            signals = [
                {"agent": "Momentum", "signal": "BUY", "confidence": 0.72, "reasoning": "Price above 20d MA"},
                {"agent": "InsiderSentiment", "signal": "BUY", "confidence": 0.65, "reasoning": "3 buys vs 1 sell"},
                {"agent": "AnalystConsensus", "signal": "HOLD", "confidence": 0.55, "reasoning": "EPS est $6.25 (28 analysts)"},
            ]

        lines = ["## Strategy Signals", ""]
        for sig in signals:
            signal = sig.get("signal", "N/A")
            agent = sig.get("agent", "Unknown")
            conf = sig.get("confidence", 0)
            reason = sig.get("reasoning", "")

            # Color code
            if signal == "BUY":
                icon = "▲"
            elif signal == "SELL":
                icon = "▼"
            else:
                icon = "◆"

            lines.append(f"  {icon} **{agent}**: {signal} (conf: {conf:.0%}) — {reason}")

        return "\n".join(lines)

    def set_ticker(self, ticker: str) -> None:
        """Update the displayed ticker."""
        self._ticker = ticker.upper()
        try:
            self.query_one("#detail-title", Label).update(f"Ticker Detail: {self._ticker}")
            self.query_one("#detail-sparkline", Static).update(self._get_sparkline())
            self.query_one("#detail-metrics", Static).update(self._get_metrics())
            self.query_one("#detail-signals", Static).update(self._get_signals())
        except Exception:
            pass
