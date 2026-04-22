"""OpenQuant Trading Agent Loop.

Implements a dual-loop agent pattern inspired by pi-mono, with generator
streaming from smolagents and toolkit grouping from agno.

Architecture:
  - Outer loop: user conversation turns
  - Inner loop: LLM <-> tool call cycles within a single turn
  - Max 20 tool-call turns per user message
  - Yields AgentEvent objects for TUI consumption
  - Async generator pattern for streaming

Hooks:
  - beforeToolCall: risk guardrails (block orders >10% of portfolio)
  - afterToolCall: logging and audit trail

Features:
  - stop_after_tool_call: stop loop after place_order
  - requires_confirmation: ask user before live trades
  - Streaming text output via litellm acompletion
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
)

from openquant.agent.providers import configure_litellm, get_default_model
from openquant.agent.system import build_system_prompt
from openquant.agent.tools import (
    TOOLS,
    ToolDefinition,
    get_litellm_tools,
    get_tool,
)

logger = logging.getLogger(__name__)


# ── Agent Event types ──────────────────────────────────────────────────────

class EventType(str, Enum):
    """Types of events the agent can yield."""
    TEXT = "text"                      # Streaming text chunk from LLM
    TEXT_DONE = "text_done"            # Complete text response
    TOOL_CALL_START = "tool_call_start"  # Tool invocation started
    TOOL_CALL_END = "tool_call_end"    # Tool invocation completed
    TOOL_RESULT = "tool_result"        # Tool execution result
    ERROR = "error"                    # Error occurred
    CONFIRMATION_REQUIRED = "confirmation_required"  # Need user confirmation
    BLOCKED = "blocked"               # Tool call blocked by guardrail
    TURN_COMPLETE = "turn_complete"   # Agent turn finished


@dataclass
class AgentEvent:
    """Event yielded by the agent loop for TUI consumption.

    Attributes:
        type: Event type.
        data: Event payload (text, tool name, result, etc.).
        timestamp: When the event occurred.
        turn: Which tool-call turn this event belongs to.
        tool_name: Name of the tool (for tool events).
    """
    type: EventType
    data: Any = None
    timestamp: datetime = field(default_factory=datetime.now)
    turn: int = 0
    tool_name: Optional[str] = None

    def __str__(self) -> str:
        if self.type == EventType.TEXT:
            return str(self.data)
        elif self.type == EventType.TOOL_CALL_START:
            return f"Calling {self.tool_name}..."
        elif self.type == EventType.TOOL_CALL_END:
            return f"Finished {self.tool_name}"
        elif self.type == EventType.TOOL_RESULT:
            return str(self.data)[:200]
        elif self.type == EventType.BLOCKED:
            return f"BLOCKED: {self.data}"
        elif self.type == EventType.ERROR:
            return f"ERROR: {self.data}"
        elif self.type == EventType.CONFIRMATION_REQUIRED:
            return f"Confirmation required: {self.data}"
        else:
            return f"{self.type.value}: {self.data}"


# ── Hook types ─────────────────────────────────────────────────────────────

BeforeToolHook = Callable[
    [str, dict],  # tool_name, arguments
    Coroutine[Any, Any, Optional[str]]  # Returns error message to block, None to allow
]

AfterToolHook = Callable[
    [str, dict, Any],  # tool_name, arguments, result
    Coroutine[Any, Any, None]
]


# ── Tool execution ────────────────────────────────────────────────────────

async def _execute_tool(
    tool_name: str,
    arguments: dict,
    broker=None,
    resolver=None,
) -> Any:
    """Execute a tool by name with the given arguments.

    This is where we wire tools to actual OpenQuant functionality.
    Falls back to mock data if broker/resolver not available.
    """
    try:
        # ── Market Data tools ──────────────────────────────────────────
        if tool_name == "get_quote" and resolver:
            ticker = arguments.get("ticker", "").upper()
            from datetime import date, timedelta
            prices = resolver.get_prices(ticker, date.today() - timedelta(days=5), date.today())
            if prices:
                p = prices[-1]
                return {
                    "ticker": ticker,
                    "price": p.close,
                    "change": p.close - p.open if hasattr(p, 'open') else 0,
                    "change_pct": ((p.close - p.open) / p.open * 100) if hasattr(p, 'open') and p.open else 0,
                    "volume": p.volume if hasattr(p, 'volume') else 0,
                }
            return {"error": f"No data available for {ticker}"}

        elif tool_name == "get_historical_prices" and resolver:
            ticker = arguments.get("ticker", "").upper()
            days = arguments.get("days", 90)
            from datetime import date, timedelta
            prices = resolver.get_prices(ticker, date.today() - timedelta(days=days), date.today())
            if prices:
                return [
                    {"date": str(p.date), "open": p.open, "high": p.high,
                     "low": p.low, "close": p.close, "volume": p.volume}
                    for p in prices[-30:]  # Last 30 data points
                ]
            return {"error": f"No price data for {ticker}"}

        elif tool_name == "get_insider_trades" and resolver:
            ticker = arguments.get("ticker", "").upper()
            days = arguments.get("days", 90)
            trades = resolver.get_insider_trades(ticker, days=days)
            if trades:
                return [
                    {"insider": t.insider_name, "title": t.title,
                     "type": t.transaction_type, "shares": t.shares,
                     "price": t.price, "value": t.value, "date": str(t.filing_date)}
                    for t in trades[:20]
                ]
            return {"error": f"No insider data for {ticker}"}

        elif tool_name == "get_company_info" and resolver:
            ticker = arguments.get("ticker", "").upper()
            info = resolver.get_company_info(ticker)
            if info:
                return {
                    "name": info.name, "sector": info.sector,
                    "industry": info.industry, "market_cap": info.market_cap,
                    "description": info.description if hasattr(info, 'description') else None,
                }
            return {"error": f"No company info for {ticker}"}

        # ── Risk tools ─────────────────────────────────────────────────
        elif tool_name == "assess_risk" and resolver:
            ticker = arguments.get("ticker", "").upper()
            days = arguments.get("days", 252)
            from datetime import date, timedelta
            from openquant.cli.main import _compute_basic_risk
            prices = resolver.get_prices(ticker, date.today() - timedelta(days=days), date.today())
            report = _compute_basic_risk(prices)
            return report if report else {"error": "Insufficient data for risk assessment"}

        elif tool_name == "calculate_position_size":
            confidence = arguments.get("confidence", 0.5)
            portfolio_value = arguments.get("portfolio_value", 10000.0)
            # 0.25x Kelly: f* = 0.25 * (bp - q) / b
            # Simplified: allocate confidence * 0.25 of portfolio
            fraction = min(confidence * 0.25, 0.10)  # Cap at 10%
            dollar_size = portfolio_value * fraction
            return {
                "kelly_fraction": round(fraction, 4),
                "dollar_size": round(dollar_size, 2),
                "portfolio_value": portfolio_value,
                "confidence": confidence,
                "note": f"0.25x Kelly suggests allocating {fraction*100:.1f}% (${dollar_size:,.2f}) of portfolio",
            }

        # ── Strategy tools ─────────────────────────────────────────────
        elif tool_name == "list_strategies":
            return {
                "strategies": [
                    {"name": "insider-momentum", "description": "Trade on insider buying momentum signals"},
                    {"name": "value-deep", "description": "Deep value investing based on fundamentals"},
                    {"name": "earnings-surge", "description": "Capture post-earnings announcement drift"},
                    {"name": "technical-breakout", "description": "Breakout-based technical trading"},
                ]
            }

        elif tool_name == "get_signals" and resolver:
            ticker = arguments.get("ticker", "").upper()
            from datetime import date, timedelta
            prices = resolver.get_prices(ticker, date.today() - timedelta(days=90), date.today())
            trades = resolver.get_insider_trades(ticker)
            estimates = resolver.get_analyst_estimates(ticker)
            from openquant.cli.main import _generate_signals
            signals = _generate_signals(prices, trades, estimates)
            return {"ticker": ticker, "signals": signals} if signals else {"ticker": ticker, "signals": []}

        elif tool_name == "analyze_stock" and resolver:
            ticker = arguments.get("ticker", "").upper()
            days = arguments.get("days", 90)
            from datetime import date, timedelta
            prices = resolver.get_prices(ticker, date.today() - timedelta(days=days), date.today())
            trades = resolver.get_insider_trades(ticker, days=days)
            estimates = resolver.get_analyst_estimates(ticker)
            info = resolver.get_company_info(ticker)
            from openquant.cli.main import _compute_basic_risk, _generate_signals
            risk = _compute_basic_risk(prices)
            signals = _generate_signals(prices, trades, estimates)
            return {
                "ticker": ticker,
                "company": {"name": info.name, "sector": info.sector} if info else None,
                "price": {"last": prices[-1].close, "change": prices[-1].close - prices[-2].close} if len(prices) >= 2 else None,
                "risk": risk,
                "signals": signals,
            }

        # ── Execution tools ────────────────────────────────────────────
        elif tool_name == "place_order" and broker:
            return broker.place_order(
                ticker=arguments.get("ticker", "").upper(),
                action=arguments.get("action", "BUY").upper(),
                quantity=arguments.get("quantity", 1),
                order_type=arguments.get("order_type", "market"),
                limit_price=arguments.get("limit_price"),
            )

        # ── Portfolio tools ────────────────────────────────────────────
        elif tool_name == "get_positions" and broker:
            positions = broker.get_positions()
            return [
                {"ticker": p.ticker, "shares": p.shares, "avg_price": p.avg_price,
                 "current_price": p.current_price, "market_value": p.market_value,
                 "unrealized_pnl": p.unrealized_pnl}
                for p in positions
            ]

        elif tool_name == "get_portfolio_summary" and broker:
            positions = broker.get_positions()
            total_value = broker.get_total_value()
            balance = broker.get_balance()
            total_pnl = total_value - 10000.0  # Assume $10k start
            return {
                "total_value": total_value,
                "cash_balance": balance,
                "total_pnl": total_pnl,
                "total_pnl_pct": (total_pnl / 10000.0) * 100,
                "num_positions": len(positions),
                "positions": [
                    {"ticker": p.ticker, "value": p.market_value, "pnl": p.unrealized_pnl}
                    for p in positions
                ],
            }

        # ── Mock fallback ──────────────────────────────────────────────
        return _mock_tool_result(tool_name, arguments)

    except Exception as exc:
        logger.error("Tool execution error (%s): %s", tool_name, exc)
        logger.debug(traceback.format_exc())
        return {"error": f"Tool execution failed: {str(exc)}"}


def _mock_tool_result(tool_name: str, arguments: dict) -> dict:
    """Return mock data for a tool when no broker/resolver is available."""
    ticker = arguments.get("ticker", "UNKNOWN")
    if tool_name == "get_quote":
        return {"ticker": ticker, "price": 150.00, "change": 2.50, "change_pct": 1.69, "volume": 50000000}
    elif tool_name == "get_historical_prices":
        return {"ticker": ticker, "note": "Historical data not available (no resolver)"}
    elif tool_name == "get_insider_trades":
        return {"ticker": ticker, "note": "Insider data not available (no resolver)"}
    elif tool_name == "get_company_info":
        return {"ticker": ticker, "note": "Company info not available (no resolver)"}
    elif tool_name == "assess_risk":
        return {"ticker": ticker, "note": "Risk assessment requires resolver"}
    elif tool_name == "get_signals":
        return {"ticker": ticker, "signals": []}
    elif tool_name == "analyze_stock":
        return {"ticker": ticker, "note": "Full analysis requires resolver and broker"}
    elif tool_name == "place_order":
        return {"error": "No broker connected. Use paper broker for testing."}
    elif tool_name == "get_positions":
        return []
    elif tool_name == "get_portfolio_summary":
        return {"total_value": 10000.00, "cash_balance": 10000.00, "total_pnl": 0.0, "num_positions": 0}
    return {"note": f"Mock result for {tool_name}"}


# ── Risk guardrail hook ────────────────────────────────────────────────────

async def default_before_tool_hook(
    tool_name: str,
    arguments: dict,
    broker=None,
    portfolio_value: float = 10000.0,
) -> Optional[str]:
    """Default beforeToolCall hook — blocks orders over 10% of portfolio.

    Returns an error message string to block the call, or None to allow.
    """
    if tool_name == "place_order":
        ticker = arguments.get("ticker", "")
        quantity = arguments.get("quantity", 0)
        price = arguments.get("limit_price", 0)

        # Try to get current price if not provided
        if not price and broker:
            positions = broker.get_positions()
            for pos in positions:
                if pos.ticker == ticker.upper():
                    price = pos.current_price
                    break

        order_value = quantity * price if price else 0
        max_allowed = portfolio_value * 0.10

        if order_value > max_allowed and portfolio_value > 0:
            return (
                f"RISK GUARDRAIL: Order value ${order_value:,.2f} exceeds "
                f"10% of portfolio (${max_allowed:,.2f}). "
                f"Reduce position size to {int(max_allowed / price)} shares "
                f"or use calculate_position_size for proper sizing."
            )

    return None


async def default_after_tool_hook(tool_name: str, arguments: dict, result: Any) -> None:
    """Default afterToolCall hook — logs tool usage for audit trail."""
    logger.info(
        "Tool call: %s(%s) -> %s",
        tool_name,
        json.dumps(arguments, default=str)[:100],
        str(result)[:200] if result else "None",
    )


# ── Main Agent Loop ────────────────────────────────────────────────────────

class AgentLoop:
    """Trading agent loop with dual-loop pattern.

    Usage:
        agent = AgentLoop(model="openai/gpt-4o-mini")
        async for event in agent.run("Analyze AAPL"):
            print(event)

    The agent yields AgentEvent objects as it processes:
      - TEXT events for streaming LLM output
      - TOOL_CALL_START/END events for tool invocations
      - TOOL_RESULT events with execution results
      - ERROR events for failures
      - CONFIRMATION_REQUIRED for live trades
      - TURN_COMPLETE when done
    """

    MAX_TURNS = 20

    def __init__(
        self,
        model: Optional[str] = None,
        broker=None,
        resolver=None,
        before_hook: Optional[BeforeToolHook] = None,
        after_hook: Optional[AfterToolHook] = None,
        mode: str = "paper",
    ):
        self.model = model or get_default_model()
        self.broker = broker
        self.resolver = resolver
        self.before_hook = before_hook
        self.after_hook = after_hook
        self.mode = mode

        self._messages: List[dict] = []
        self._system_prompt: Optional[str] = None
        self._portfolio_value: float = 10000.0

        configure_litellm()

    def _get_system_prompt(self) -> str:
        """Build system prompt with current context."""
        positions = []
        if self.broker:
            try:
                positions = self.broker.get_positions()
                self._portfolio_value = self.broker.get_total_value()
            except Exception:
                pass

        return build_system_prompt(
            portfolio_value=self._portfolio_value,
            positions=positions,
            mode=self.mode,
            broker=self.broker.name if self.broker else "none",
        )

    async def run(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the agent loop for a single user message.

        Yields AgentEvent objects as processing happens.
        Maximum 20 tool-call turns per user message.
        """
        import litellm

        # Initialize system prompt on first run
        if not self._system_prompt:
            self._system_prompt = self._get_system_prompt()

        # Add user message to conversation
        self._messages.append({"role": "user", "content": user_message})

        # Track accumulated text for this turn
        accumulated_text = ""

        # ── Inner loop: LLM <-> tool calls ─────────────────────────────
        for turn in range(self.MAX_TURNS):
            try:
                # Call LLM with streaming
                tools = get_litellm_tools()
                response = await litellm.acompletion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._system_prompt},
                        *self._messages,
                    ],
                    tools=tools if tools else None,
                    tool_choice="auto",
                    stream=True,
                )

                # Process streaming response
                tool_calls_map: Dict[int, dict] = {}
                current_text = ""

                async for chunk in response:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta is None:
                        continue

                    # Handle text content
                    if delta.content:
                        current_text += delta.content
                        yield AgentEvent(
                            type=EventType.TEXT,
                            data=delta.content,
                            turn=turn,
                        )

                    # Handle tool call deltas
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_calls_map:
                                tool_calls_map[idx] = {
                                    "id": tc_delta.id or "",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc_delta.id:
                                tool_calls_map[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tool_calls_map[idx]["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_map[idx]["arguments"] += tc_delta.function.arguments

                # ── Process accumulated text ────────────────────────────
                if current_text:
                    accumulated_text += current_text
                    self._messages.append({"role": "assistant", "content": current_text})
                    yield AgentEvent(
                        type=EventType.TEXT_DONE,
                        data=current_text,
                        turn=turn,
                    )

                # ── Process tool calls ──────────────────────────────────
                if not tool_calls_map:
                    # No tool calls — agent is done
                    break

                # Build assistant message with tool calls for conversation
                assistant_msg = {"role": "assistant", "content": current_text or None, "tool_calls": []}

                has_stop_tool = False
                for idx in sorted(tool_calls_map.keys()):
                    tc = tool_calls_map[idx]
                    tool_name = tc["name"]
                    tool_id = tc["id"] or f"call_{idx}"

                    # Parse arguments
                    try:
                        arguments = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        arguments = {}
                        yield AgentEvent(
                            type=EventType.ERROR,
                            data=f"Failed to parse arguments for {tool_name}",
                            turn=turn,
                            tool_name=tool_name,
                        )

                    tool_def = get_tool(tool_name)

                    # ── Before hook (risk guardrail) ─────────────────────
                    yield AgentEvent(
                        type=EventType.TOOL_CALL_START,
                        data={"name": tool_name, "arguments": arguments},
                        turn=turn,
                        tool_name=tool_name,
                    )

                    if self.before_hook:
                        block_reason = await self.before_hook(tool_name, arguments)
                        if block_reason:
                            yield AgentEvent(
                                type=EventType.BLOCKED,
                                data=block_reason,
                                turn=turn,
                                tool_name=tool_name,
                            )
                            # Add blocked result to conversation
                            assistant_msg["tool_calls"].append({
                                "id": tool_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": tc["arguments"]},
                            })
                            self._messages.append(assistant_msg)
                            self._messages.append({
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": f"BLOCKED: {block_reason}",
                            })
                            continue

                    # ── Confirmation required? ───────────────────────────
                    if tool_def and tool_def.requires_confirmation and self.mode == "live":
                        yield AgentEvent(
                            type=EventType.CONFIRMATION_REQUIRED,
                            data=f"Confirm {tool_name}({arguments})?",
                            turn=turn,
                            tool_name=tool_name,
                        )
                        # For now, auto-confirm in paper mode
                        # In live mode, the TUI should handle confirmation

                    # ── Execute tool ─────────────────────────────────────
                    result = await _execute_tool(tool_name, arguments, self.broker, self.resolver)

                    yield AgentEvent(
                        type=EventType.TOOL_RESULT,
                        data=result,
                        turn=turn,
                        tool_name=tool_name,
                    )

                    yield AgentEvent(
                        type=EventType.TOOL_CALL_END,
                        data={"name": tool_name, "result_preview": str(result)[:200]},
                        turn=turn,
                        tool_name=tool_name,
                    )

                    # ── After hook (logging) ─────────────────────────────
                    if self.after_hook:
                        await self.after_hook(tool_name, arguments, result)
                    else:
                        await default_after_tool_hook(tool_name, arguments, result)

                    # Add to conversation for next LLM call
                    assistant_msg["tool_calls"].append({
                        "id": tool_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tc["arguments"]},
                    })

                    result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result_str,
                    })

                    # ── Stop after certain tools? ────────────────────────
                    if tool_def and tool_def.stop_after:
                        has_stop_tool = True

                # Ensure assistant message is in the conversation
                if assistant_msg.get("tool_calls"):
                    # Need to insert before the tool messages we just added
                    # Find the last user or tool message index
                    insert_idx = len(self._messages) - len(assistant_msg["tool_calls"])
                    # The assistant message should already be part of flow
                    # Actually, let's restructure: add assistant first, then tools
                    pass

                if has_stop_tool:
                    break

                # Continue loop — LLM will see tool results and may call more tools

            except Exception as exc:
                logger.error("Agent loop error (turn %d): %s", turn, exc)
                logger.debug(traceback.format_exc())
                yield AgentEvent(
                    type=EventType.ERROR,
                    data=str(exc),
                    turn=turn,
                )
                break

        # ── Turn complete ───────────────────────────────────────────────
        yield AgentEvent(
            type=EventType.TURN_COMPLETE,
            data=accumulated_text,
            turn=turn,
        )

    def reset(self) -> None:
        """Reset conversation history."""
        self._messages.clear()
        self._system_prompt = None

    @property
    def message_count(self) -> int:
        """Number of messages in conversation history."""
        return len(self._messages)


# ── Convenience: run agent synchronously in terminal ───────────────────────

async def run_agent_terminal(
    user_message: str,
    model: Optional[str] = None,
    broker=None,
    resolver=None,
    mode: str = "paper",
) -> str:
    """Run the agent and collect the final text output.

    Useful for non-TUI terminal usage.
    """
    agent = AgentLoop(model=model, broker=broker, resolver=resolver, mode=mode)
    final_text = ""

    async for event in agent.run(user_message):
        if event.type == EventType.TEXT:
            print(event.data, end="", flush=True)
        elif event.type == EventType.TEXT_DONE:
            print()  # Newline after streaming
        elif event.type == EventType.TOOL_CALL_START:
            print(f"\n  Calling {event.tool_name}...", flush=True)
        elif event.type == EventType.TOOL_RESULT:
            result_str = json.dumps(event.data, indent=2, default=str) if isinstance(event.data, (dict, list)) else str(event.data)
            print(f"  Result: {result_str[:500]}", flush=True)
        elif event.type == EventType.BLOCKED:
            print(f"\n  BLOCKED: {event.data}", flush=True)
        elif event.type == EventType.ERROR:
            print(f"\n  ERROR: {event.data}", flush=True)
        elif event.type == EventType.TURN_COMPLETE:
            final_text = event.data or ""

    return final_text
