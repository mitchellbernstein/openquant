"""Chat panel for OpenQuant TUI.

Features:
  - Input field at bottom
  - Message display area with Markdown rendering
  - Tool call visualization
  - Streaming output from agent loop
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Input, Label, Markdown, Static

from openquant.agent.loop import AgentEvent, AgentLoop, EventType

logger = logging.getLogger(__name__)

HELP_TEXT = """# OpenQuant Chat

Available commands:
- `/analyze TICKER` — Full AI analysis of a stock
- `/buy TICKER SHARES` — Buy shares (paper mode)
- `/sell TICKER SHARES` — Sell shares (paper mode)
- `/watch TICKER` — Add ticker to watchlist
- `/help` — Show this help
- `/quit` — Exit

Or just type naturally:
- "What's the risk profile of AAPL?"
- "Should I buy NVDA?"
- "Show me my portfolio"
- "Analyze TSLA insider trades"
"""


class ChatMessage(Static):
    """A single chat message."""

    CSS = """
    ChatMessage {
        margin: 0 0 1 0;
        padding: 0 1;
    }

    ChatMessage .role-user {
        color: $text;
        text-style: bold;
    }

    ChatMessage .role-assistant {
        color: $success;
        text-style: bold;
    }

    ChatMessage .role-tool {
        color: $warning;
    }

    ChatMessage .role-error {
        color: $error;
    }

    ChatMessage .role-system {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(
        self,
        role: str,
        content: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.role = role
        self.content = content

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Label(f"You: {self.content}", classes="role-user")
        elif self.role == "assistant":
            yield Markdown(self.content, classes="role-assistant")
        elif self.role == "tool":
            yield Label(f"  Tool: {self.content[:200]}", classes="role-tool")
        elif self.role == "error":
            yield Label(f"  Error: {self.content}", classes="role-error")
        elif self.role == "system":
            yield Label(f"  System: {self.content}", classes="role-system")
        elif self.role == "blocked":
            yield Label(f"  BLOCKED: {self.content}", classes="role-error")


class ChatPanel(Vertical):
    """Chat panel with agent loop integration."""

    CSS = """
    ChatPanel {
        height: 100%;
    }

    #chat-messages {
        height: 1fr;
        padding: 0 1;
        border: solid $primary;
    }

    #chat-input-container {
        height: 3;
        padding: 0 1;
        border-top: solid $primary;
    }

    #chat-input {
        width: 100%;
    }

    #chat-status {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    is_processing: reactive[bool] = reactive(False)

    def __init__(
        self,
        broker=None,
        resolver=None,
        mode: str = "paper",
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.broker = broker
        self.resolver = resolver
        self.mode = mode
        self._agent: Optional[AgentLoop] = None
        self._streaming_text = ""

    def compose(self) -> ComposeResult:
        yield Label("OpenQuant Chat — AI Trading Assistant", id="chat-title")
        yield VerticalScroll(id="chat-messages")
        yield Label("Ready", id="chat-status")
        yield Input(
            placeholder="Ask about any stock, strategy, or risk analysis...",
            id="chat-input",
        )

    def on_mount(self) -> None:
        """Initialize the agent and focus input."""
        self._agent = AgentLoop(
            broker=self.broker,
            resolver=self.resolver,
            mode=self.mode,
        )

        # Welcome message
        self._add_message("system", "Welcome to OpenQuant Chat. Type a question or use / commands. Type /help for help.")

        # Focus input
        try:
            self.query_one("#chat-input", Input).focus()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle chat input submission."""
        if event.input.id != "chat-input":
            return
        if self.is_processing:
            return

        text = event.value.strip()
        event.input.value = ""

        if not text:
            return

        await self.handle_input(text)

    async def handle_input(self, text: str) -> None:
        """Process user input text."""
        if self.is_processing:
            return

        self._add_message("user", text)
        self.is_processing = True
        self._update_status("Thinking...")

        # Run agent in background
        self._run_agent(text)

    @work(exclusive=True)
    async def _run_agent(self, user_message: str) -> None:
        """Run the agent loop and stream results."""
        self._streaming_text = ""
        streaming_widget = None

        try:
            async for event in self._agent.run(user_message):
                if event.type == EventType.TEXT:
                    self._streaming_text += event.data
                    # Update the streaming message
                    streaming_widget = self._update_streaming(
                        streaming_widget, self._streaming_text
                    )

                elif event.type == EventType.TEXT_DONE:
                    if self._streaming_text:
                        # Finalize the streaming message
                        if streaming_widget:
                            self._finalize_streaming(streaming_widget, self._streaming_text)
                        else:
                            self._add_message("assistant", self._streaming_text)
                    self._streaming_text = ""

                elif event.type == EventType.TOOL_CALL_START:
                    tool_name = event.tool_name or "unknown"
                    args = event.data.get("arguments", {}) if isinstance(event.data, dict) else {}
                    args_str = json.dumps(args, default=str)[:80]
                    self._add_message("tool", f"Calling {tool_name}({args_str})")
                    self._update_status(f"Running {tool_name}...")

                elif event.type == EventType.TOOL_RESULT:
                    result = event.data
                    result_str = json.dumps(result, indent=2, default=str) if isinstance(result, (dict, list)) else str(result)
                    self._add_message("system", f"Result: {result_str[:300]}")

                elif event.type == EventType.BLOCKED:
                    self._add_message("blocked", str(event.data))

                elif event.type == EventType.ERROR:
                    self._add_message("error", str(event.data))

                elif event.type == EventType.CONFIRMATION_REQUIRED:
                    self._add_message("system", f"Confirmation needed: {event.data}")

                elif event.type == EventType.TURN_COMPLETE:
                    if not self._streaming_text and event.data:
                        self._add_message("assistant", event.data)

        except Exception as exc:
            logger.error("Agent run error: %s", exc)
            self._add_message("error", f"Agent error: {exc}")
        finally:
            self.is_processing = False
            self._update_status("Ready")
            try:
                self.query_one("#chat-input", Input).focus()
            except Exception:
                pass

    def _add_message(self, role: str, content: str) -> None:
        """Add a message to the chat display."""
        try:
            messages = self.query_one("#chat-messages", VerticalScroll)
            msg = ChatMessage(role=role, content=content)
            messages.mount(msg)
            # Auto-scroll to bottom
            messages.scroll_end(animate=False)
        except Exception as exc:
            logger.error("Failed to add message: %s", exc)

    def _update_streaming(self, widget: Optional[Static], text: str) -> Optional[Static]:
        """Update or create a streaming message widget."""
        try:
            messages = self.query_one("#chat-messages", VerticalScroll)
            if widget is None:
                widget = Static(f"Assistant: {text}", classes="role-assistant")
                messages.mount(widget)
            else:
                widget.update(f"Assistant: {text}")
            messages.scroll_end(animate=False)
            return widget
        except Exception:
            return None

    def _finalize_streaming(self, widget: Static, text: str) -> None:
        """Replace streaming Static with a Markdown widget."""
        try:
            messages = self.query_one("#chat-messages", VerticalScroll)
            md = Markdown(text, classes="role-assistant")
            # Mount the Markdown right after the streaming widget
            idx = list(messages.children).index(widget)
            messages.mount(md, after=widget)
            widget.remove()
            messages.scroll_end(animate=False)
        except Exception:
            # If mounting fails, just update the text
            try:
                widget.update(text)
            except Exception:
                pass

    def _update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one("#chat-status", Label)
            status.update(text)
        except Exception:
            pass

    def show_help(self) -> None:
        """Show help in the chat."""
        self._add_message("system", HELP_TEXT)
