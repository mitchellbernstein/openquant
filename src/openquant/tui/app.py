"""OpenQuant Textual TUI — the sentient Bloomberg terminal experience.

Dark finance theme with:
  - Green = up/profit
  - Red = down/loss
  - Cyan = highlight/active
  - Yellow = warning/attention

Panels:
  1 - Watchlist
  2 - Chat
  3 - Ticker Detail
  4 - Portfolio
  5-8 - Reserved for future panels

Key bindings:
  1-8  Switch panels
  Tab  Cycle panels
  /    Command bar
  ?    Help
  q    Quit
  j/k  Scroll down/up
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    Static,
    TabbedContent,
    TabPane,
)

from openquant.tui.panels.watchlist import WatchlistPanel
from openquant.tui.panels.chat import ChatPanel
from openquant.tui.panels.ticker_detail import TickerDetailPanel
from openquant.tui.panels.portfolio import PortfolioPanel

logger = logging.getLogger(__name__)


# ── Custom CSS ─────────────────────────────────────────────────────────────

OPENQUANT_CSS = """
Screen {
    background: $surface;
}

#header-bar {
    background: $primary;
    color: $text;
    padding: 0 1;
    height: 3;
}

#header-bar .label {
    color: $text;
}

#mode-label {
    color: $warning;
}

#broker-label {
    color: $success;
}

#time-label {
    color: $text-muted;
    text-align: right;
}

#command-bar {
    dock: bottom;
    height: 3;
    padding: 0 1;
    background: $primary-background;
    border-top: solid $primary;
}

#command-input {
    width: 100%;
}

.status-ok {
    color: $success;
}

.status-warn {
    color: $warning;
}

.status-error {
    color: $error;
}

.price-up {
    color: $success;
}

.price-down {
    color: $error;
}

.price-neutral {
    color: $text-muted;
}
"""


class OpenQuantHeader(Static):
    """Custom header bar showing mode, broker, and time."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Label("OpenQuant v0.2.0", classes="label")
            yield Label(" | ", classes="label")
            yield Label("Mode: Research", id="mode-label")
            yield Label(" | ", classes="label")
            yield Label("Broker: Paper", id="broker-label")
            yield Label(" | ", classes="label")
            yield Label(datetime.now().strftime("%H:%M:%S"), id="time-label")

    def on_mount(self) -> None:
        self.set_interval(1, self._update_clock)

    def _update_clock(self) -> None:
        """Update the clock every second."""
        try:
            time_label = self.query_one("#time-label", Label)
            time_label.update(datetime.now().strftime("%H:%M:%S"))
        except NoMatches:
            pass


class OpenQuantApp(App):
    """The OpenQuant Textual TUI application."""

    TITLE = "OpenQuant"
    CSS = OPENQUANT_CSS

    BINDINGS = [
        Binding("1", "switch_panel(0)", "Watchlist", show=False),
        Binding("2", "switch_panel(1)", "Chat", show=False),
        Binding("3", "switch_panel(2)", "Ticker Detail", show=False),
        Binding("4", "switch_panel(3)", "Portfolio", show=False),
        Binding("5", "switch_panel(4)", "Panel 5", show=False),
        Binding("6", "switch_panel(5)", "Panel 6", show=False),
        Binding("7", "switch_panel(6)", "Panel 7", show=False),
        Binding("8", "switch_panel(7)", "Panel 8", show=False),
        Binding("tab", "cycle_panel", "Next Panel", show=False),
        Binding("shift+tab", "cycle_panel_back", "Prev Panel", show=False),
        Binding("/", "focus_command", "Command", show=True),
        Binding("question_mark", "toggle_help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
    ]

    current_panel: reactive[int] = reactive(0)

    def __init__(self, broker=None, resolver=None, mode: str = "paper"):
        super().__init__()
        self.broker = broker
        self.resolver = resolver
        self.mode = mode
        self._command_active = False

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield OpenQuantHeader()
        with TabbedContent(id="main-tabs"):
            with TabPane("1 Watchlist", id="tab-watchlist"):
                yield WatchlistPanel(resolver=self.resolver)
            with TabPane("2 Chat", id="tab-chat"):
                yield ChatPanel(
                    broker=self.broker,
                    resolver=self.resolver,
                    mode=self.mode,
                )
            with TabPane("3 Detail", id="tab-detail"):
                yield TickerDetailPanel(resolver=self.resolver)
            with TabPane("4 Portfolio", id="tab-portfolio"):
                yield PortfolioPanel(broker=self.broker)
            with TabPane("5 News", id="tab-news"):
                yield Static("News feed — coming soon", classes="price-neutral")
            with TabPane("6 Alerts", id="tab-alerts"):
                yield Static("Alerts — coming soon", classes="price-neutral")
            with TabPane("7 Research", id="tab-research"):
                yield Static("Research notes — coming soon", classes="price-neutral")
            with TabPane("8 Settings", id="tab-settings"):
                yield Static("Settings — coming soon", classes="price-neutral")
        yield Horizontal(
            Label("> ", classes="label"),
            Input(placeholder="Type / for commands, or chat in Chat panel", id="command-input"),
            id="command-bar",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app on mount."""
        self.switch_panel(0)

    # ── Panel switching ────────────────────────────────────────────────

    def action_switch_panel(self, index: int) -> None:
        """Switch to a specific panel by index."""
        try:
            tabs = self.query_one("#main-tabs", TabbedContent)
            tab_ids = [
                "tab-watchlist", "tab-chat", "tab-detail", "tab-portfolio",
                "tab-news", "tab-alerts", "tab-research", "tab-settings",
            ]
            if 0 <= index < len(tab_ids):
                tabs.active = tab_ids[index]
                self.current_panel = index
        except NoMatches:
            pass

    def action_cycle_panel(self) -> None:
        """Cycle to next panel."""
        next_panel = (self.current_panel + 1) % 8
        self.action_switch_panel(next_panel)

    def action_cycle_panel_back(self) -> None:
        """Cycle to previous panel."""
        prev_panel = (self.current_panel - 1) % 8
        self.action_switch_panel(prev_panel)

    # ── Command bar ────────────────────────────────────────────────────

    def action_focus_command(self) -> None:
        """Focus the command input bar."""
        try:
            cmd_input = self.query_one("#command-input", Input)
            cmd_input.focus()
            self._command_active = True
        except NoMatches:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input submission."""
        if event.input.id == "command-input":
            value = event.value.strip()
            event.input.value = ""

            if not value:
                return

            # Route to chat if on chat panel, otherwise treat as command
            if value.startswith("/"):
                await self._handle_command(value[1:])
            else:
                # Route to chat panel
                self.action_switch_panel(1)
                try:
                    chat = self.query_one(ChatPanel)
                    await chat.handle_input(value)
                except NoMatches:
                    pass

    async def _handle_command(self, cmd: str) -> None:
        """Handle a slash command."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "help":
            self.action_toggle_help()
        elif command == "quit" or command == "q":
            self.exit()
        elif command == "analyze" and args:
            self.action_switch_panel(1)
            try:
                chat = self.query_one(ChatPanel)
                await chat.handle_input(f"Analyze {args.strip()}")
            except NoMatches:
                pass
        elif command == "buy" and args:
            self.action_switch_panel(1)
            try:
                chat = self.query_one(ChatPanel)
                await chat.handle_input(f"Buy {args.strip()}")
            except NoMatches:
                pass
        elif command == "sell" and args:
            self.action_switch_panel(1)
            try:
                chat = self.query_one(ChatPanel)
                await chat.handle_input(f"Sell {args.strip()}")
            except NoMatches:
                pass
        elif command == "watch" and args:
            self.action_switch_panel(0)
            try:
                watchlist = self.query_one(WatchlistPanel)
                watchlist.add_ticker(args.strip().upper())
            except NoMatches:
                pass
        else:
            # Unknown command — send to chat
            self.action_switch_panel(1)
            try:
                chat = self.query_one(ChatPanel)
                await chat.handle_input(cmd)
            except NoMatches:
                pass

    # ── Scroll actions ─────────────────────────────────────────────────

    def action_scroll_down(self) -> None:
        """Scroll down in the current panel."""
        try:
            # Try to scroll the active tab content
            tabs = self.query_one("#main-tabs", TabbedContent)
            active_pane = tabs.query_one(f"#{tabs.active}", TabPane)
            # Scroll the first scrollable widget
            for widget in active_pane.query(Static):
                widget.scroll_relative(3)
                break
        except (NoMatches, Exception):
            pass

    def action_scroll_up(self) -> None:
        """Scroll up in the current panel."""
        try:
            tabs = self.query_one("#main-tabs", TabbedContent)
            active_pane = tabs.query_one(f"#{tabs.active}", TabPane)
            for widget in active_pane.query(Static):
                widget.scroll_relative(-3)
                break
        except (NoMatches, Exception):
            pass

    def action_toggle_help(self) -> None:
        """Toggle help overlay."""
        # For now, just switch to chat and show help
        self.action_switch_panel(1)
        try:
            chat = self.query_one(ChatPanel)
            chat.show_help()
        except NoMatches:
            pass


def run_tui(broker=None, resolver=None, mode: str = "paper") -> None:
    """Launch the OpenQuant TUI application."""
    app = OpenQuantApp(broker=broker, resolver=resolver, mode=mode)
    app.run()
