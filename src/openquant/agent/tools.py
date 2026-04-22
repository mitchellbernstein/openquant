"""Trading tool schemas for litellm function calling.

Converts OpenQuant functions to litellm tool format with toolkit grouping:
  - market_data: price lookup, quotes, historical data
  - risk: risk assessment, VaR, position sizing
  - strategy: strategy listing, signal generation
  - execution: order placement, position management
  - portfolio: portfolio summary, P&L tracking

Each tool has: name, description, parameters (Pydantic-derived JSON schema).
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Toolkit groups ─────────────────────────────────────────────────────────

class Toolkit(str, Enum):
    """Tool grouping for organized access."""
    MARKET_DATA = "market_data"
    RISK = "risk"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    PORTFOLIO = "portfolio"


# ── Parameter models (Pydantic -> JSON Schema) ────────────────────────────

class GetQuoteParams(BaseModel):
    """Get current quote for a ticker."""
    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL")


class GetHistoricalPricesParams(BaseModel):
    """Get historical price data for a ticker."""
    ticker: str = Field(..., description="Stock ticker symbol")
    days: int = Field(default=90, description="Number of days of history")


class GetInsiderTradesParams(BaseModel):
    """Get recent insider trades for a ticker."""
    ticker: str = Field(..., description="Stock ticker symbol")
    days: int = Field(default=90, description="Lookback period in days")


class GetCompanyInfoParams(BaseModel):
    """Get company information for a ticker."""
    ticker: str = Field(..., description="Stock ticker symbol")


class AssessRiskParams(BaseModel):
    """Run risk assessment on a ticker."""
    ticker: str = Field(..., description="Stock ticker symbol")
    days: int = Field(default=252, description="Lookback in trading days")


class CalculatePositionSizeParams(BaseModel):
    """Calculate position size using Kelly criterion."""
    ticker: str = Field(..., description="Stock ticker symbol")
    confidence: float = Field(..., description="Signal confidence 0-1", ge=0, le=1)
    portfolio_value: float = Field(default=10000.0, description="Total portfolio value")


class ListStrategiesParams(BaseModel):
    """List available trading strategies."""
    pass


class GetSignalsParams(BaseModel):
    """Get trading signals for a ticker."""
    ticker: str = Field(..., description="Stock ticker symbol")
    strategy: Optional[str] = Field(default=None, description="Specific strategy name")


class PlaceOrderParams(BaseModel):
    """Place a trade order. REQUIRES CONFIRMATION in live mode."""
    ticker: str = Field(..., description="Stock ticker symbol")
    action: str = Field(..., description="BUY or SELL")
    quantity: float = Field(..., description="Number of shares", gt=0)
    order_type: str = Field(default="market", description="Order type: market, limit, stop")
    limit_price: Optional[float] = Field(default=None, description="Limit price for limit orders")


class GetPositionsParams(BaseModel):
    """Get current portfolio positions."""
    pass


class GetPortfolioSummaryParams(BaseModel):
    """Get portfolio summary with total value and P&L."""
    pass


class AnalyzeStockParams(BaseModel):
    """Full AI analysis of a stock including signals and risk."""
    ticker: str = Field(..., description="Stock ticker symbol")
    days: int = Field(default=90, description="Lookback period in days")


# ── Tool definitions ───────────────────────────────────────────────────────

class ToolDefinition:
    """A tool definition for litellm function calling."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: type[BaseModel],
        toolkit: Toolkit,
        requires_confirmation: bool = False,
        stop_after: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.toolkit = toolkit
        self.requires_confirmation = requires_confirmation
        self.stop_after = stop_after

    def to_litellm_format(self) -> dict:
        """Convert to litellm/openai function calling format."""
        schema = self.parameters.model_json_schema()
        # Remove title from schema since litellm doesn't need it
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ── Tool registry ──────────────────────────────────────────────────────────

TOOLS: Dict[str, ToolDefinition] = {}


def register_tool(tool: ToolDefinition) -> None:
    """Register a tool definition."""
    TOOLS[tool.name] = tool


def _init_tools() -> None:
    """Initialize all built-in tools."""
    # Market Data tools
    register_tool(ToolDefinition(
        name="get_quote",
        description="Get current price quote for a stock ticker including bid/ask, volume, and change.",
        parameters=GetQuoteParams,
        toolkit=Toolkit.MARKET_DATA,
    ))
    register_tool(ToolDefinition(
        name="get_historical_prices",
        description="Get historical OHLCV price data for a stock ticker over a specified number of days.",
        parameters=GetHistoricalPricesParams,
        toolkit=Toolkit.MARKET_DATA,
    ))
    register_tool(ToolDefinition(
        name="get_insider_trades",
        description="Get recent insider buying/selling activity for a stock ticker. Shows officer/director transactions.",
        parameters=GetInsiderTradesParams,
        toolkit=Toolkit.MARKET_DATA,
    ))
    register_tool(ToolDefinition(
        name="get_company_info",
        description="Get company information including sector, industry, market cap, and description.",
        parameters=GetCompanyInfoParams,
        toolkit=Toolkit.MARKET_DATA,
    ))

    # Risk tools
    register_tool(ToolDefinition(
        name="assess_risk",
        description="Run risk assessment on a ticker. Returns volatility, max drawdown, Sharpe ratio, VaR, and overall risk rating.",
        parameters=AssessRiskParams,
        toolkit=Toolkit.RISK,
    ))
    register_tool(ToolDefinition(
        name="calculate_position_size",
        description="Calculate recommended position size using 0.25x Kelly criterion. Returns number of shares to buy/sell.",
        parameters=CalculatePositionSizeParams,
        toolkit=Toolkit.RISK,
    ))

    # Strategy tools
    register_tool(ToolDefinition(
        name="list_strategies",
        description="List all available trading strategies with descriptions.",
        parameters=ListStrategiesParams,
        toolkit=Toolkit.STRATEGY,
    ))
    register_tool(ToolDefinition(
        name="get_signals",
        description="Get trading signals for a ticker. Optionally specify a strategy. Returns BUY/SELL/HOLD with confidence.",
        parameters=GetSignalsParams,
        toolkit=Toolkit.STRATEGY,
    ))

    # Execution tools
    register_tool(ToolDefinition(
        name="place_order",
        description="Place a buy or sell order. REQUIRES CONFIRMATION in live trading mode. Use calculate_position_size first.",
        parameters=PlaceOrderParams,
        toolkit=Toolkit.EXECUTION,
        requires_confirmation=True,
        stop_after=True,
    ))

    # Portfolio tools
    register_tool(ToolDefinition(
        name="get_positions",
        description="Get all current portfolio positions with shares, average price, and unrealized P&L.",
        parameters=GetPositionsParams,
        toolkit=Toolkit.PORTFOLIO,
    ))
    register_tool(ToolDefinition(
        name="get_portfolio_summary",
        description="Get portfolio summary: total value, cash balance, total P&L, and allocation breakdown.",
        parameters=GetPortfolioSummaryParams,
        toolkit=Toolkit.PORTFOLIO,
    ))

    # Composite analysis tool
    register_tool(ToolDefinition(
        name="analyze_stock",
        description="Full analysis of a stock: combines price data, insider trades, risk metrics, and AI signals into one report.",
        parameters=AnalyzeStockParams,
        toolkit=Toolkit.STRATEGY,
    ))


# Initialize on import
_init_tools()


# ── Public API ─────────────────────────────────────────────────────────────

def get_all_tools() -> List[ToolDefinition]:
    """Get all registered tool definitions."""
    return list(TOOLS.values())


def get_tools_by_toolkit(toolkit: Toolkit) -> List[ToolDefinition]:
    """Get tools filtered by toolkit group."""
    return [t for t in TOOLS.values() if t.toolkit == toolkit]


def get_litellm_tools() -> List[dict]:
    """Get all tools in litellm function calling format."""
    return [t.to_litellm_format() for t in TOOLS.values()]


def get_litellm_tools_by_toolkit(toolkit: Toolkit) -> List[dict]:
    """Get tools in litellm format filtered by toolkit."""
    return [t.to_litellm_format() for t in TOOLS.values() if t.toolkit == toolkit]


def get_tool(name: str) -> Optional[ToolDefinition]:
    """Get a specific tool by name."""
    return TOOLS.get(name)
