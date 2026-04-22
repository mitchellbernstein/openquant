# OpenQuant — Claude Code Instructions

This file tells Claude Code how to use OpenQuant's trading tools via the MCP server.

## MCP Server Connection

OpenQuant exposes an MCP server with SSE transport. Start it with:

```bash
pip install openquant[mcp]
openquant-mcp
```

The server runs at `http://localhost:8000/sse` by default.

### Claude Code MCP Config

Add to your `.claude/settings.json` or project `.mcp.json`:

```json
{
  "mcpServers": {
    "openquant": {
      "url": "http://localhost:8000/sse",
      "transport": "sse"
    }
  }
}
```

If running locally with stdio transport instead:

```json
{
  "mcpServers": {
    "openquant": {
      "command": "openquant-mcp",
      "transport": "stdio"
    }
  }
}
```

## Available MCP Tools

### Research & Analysis

| Tool | When to Use | Key Params |
|------|-------------|------------|
| `openquant_analyze` | First stop for any ticker — full analysis combining prices, insider, risk | `ticker`, `days` (default 90) |
| `openquant_insider_scan` | Deep dive on insider buying/selling activity | `ticker`, `days` (default 90) |
| `openquant_risk_assessment` | Before any trade — volatility, VaR, drawdown, Kelly fraction | `tickers` (comma-separated), `days` (default 252) |

### Strategy & Signals

| Tool | When to Use | Key Params |
|------|-------------|------------|
| `openquant_strategy_list` | Discover available strategies | none |
| `openquant_strategy_run` | Generate a trade signal for a specific strategy + ticker | `strategy_name`, `ticker` |
| `openquant_backtest` | Validate a strategy on historical data | `strategy_name`, `ticker`, `days` (default 252) |

### Portfolio & Execution

| Tool | When to Use | Key Params |
|------|-------------|------------|
| `openquant_portfolio_status` | Check current positions, balance, P&L | none |
| `openquant_trade_execute` | Execute a paper trade (game mode) | `action`, `ticker`, `shares`, `price` |
| `openquant_trade_history` | Review recent trades | `limit` (default 20) |
| `openquant_game_status` | Game mode leaderboard and achievements | none |

## Trading Workflow

Follow this sequence for every trade idea:

1. **Research** — `openquant_analyze` on the ticker. Review price range, insider score, risk level.
2. **Analyze** — `openquant_insider_scan` for insider sentiment detail. `openquant_strategy_run` for a signal.
3. **Risk Check** — `openquant_risk_assessment` to get VaR, max drawdown, Kelly fraction. Never skip this step.
4. **Signal** — Confirm the strategy confidence is >= 40 (out of 100). Below 40 = HOLD, not actionable.
5. **Execute** — `openquant_trade_execute` only after showing the user your full reasoning and getting explicit confirmation.

## Interpreting Strategy Signals

Strategy results return:
- **action**: `BUY`, `SELL`, or `HOLD`
- **confidence**: 0–100 scale. Only act on confidence >= 40.
- **position_size_pct**: Fraction of portfolio to allocate (already Kelly-adjusted)
- **entry_price / stop_loss / take_profit**: Price levels for the trade
- **reasoning**: Human-readable explanation

Agent-level signals use a -1.0 to +1.0 scale:
- **+1.0 to +0.3**: BULLISH (signal to buy)
- **+0.3 to -0.3**: NEUTRAL (hold / no action)
- **-0.3 to -1.0**: BEARISH (signal to sell)

Insider scores use a -100 to +100 scale:
- **+60 to +100**: STRONG BUY
- **+25 to +59**: BUY
- **-24 to +24**: NEUTRAL
- **-59 to -25**: SELL
- **-100 to -60**: STRONG SELL

## Risk Management Rules

These are hard rules, not suggestions:

1. **0.25x Kelly**: Position sizes from `calculate_position_size` use quarter-Kelly. If full Kelly says 20%, use 5%. This is built into the tool — do not override it.
2. **Max 10% position**: No single position can exceed 10% of total portfolio value. The system blocks orders that violate this. Do not try to circumvent by splitting orders.
3. **Confidence threshold**: Only trade on signals with confidence >= 40. Low-conviction signals are for monitoring.
4. **Always run risk assessment**: Before `openquant_trade_execute`, you must run `openquant_risk_assessment` and show the user the VaR and max drawdown.
5. **Multi-factor confirmation**: Prefer trades where at least 2 of the 5 agents (insider, value, growth, technical, sentiment) agree on direction.

## Safety Guardrails

- **NEVER execute live trades without explicit user confirmation.** Show your reasoning, the risk assessment, and the exact order details before executing.
- In live trading mode (`mode=live`), all `place_order` calls require confirmation. The system enforces this.
- Paper trading / game mode is safe for experimentation. Default broker is in-memory paper.
- All analysis is for educational purposes. You are not a registered investment advisor.

## Built-in Strategies

| Strategy | Description | Best For |
|----------|-------------|----------|
| `insider-momentum` | Trade on insider buying clusters + CEO purchases | Short-term momentum plays |
| `value-deep` | Deep value: low P/E, high ROE, low debt + insider buying | Long-term value investing |
| `earnings-surge` | Post-earnings announcement drift capture | Earnings season trades |
| `technical-breakout` | 50-day SMA breakout with volume + insider confirmation | Medium-term trend following |

## QuantFetch API Key (Optional)

OpenQuant works without any API key using yfinance and SEC EDGAR data. To enable QuantFetch for real-time data:

```bash
export QUANTFETCH_API_KEY=your_key_here
```

Set this in `.env` or your shell profile. The data resolver chain is: QuantFetch (if key set) → yfinance → SEC EDGAR. Falls back automatically.

### Data Unit Conventions

When reading QuantFetch data:
- **Earnings per share**: reported in cents (e.g., 250 = $2.50 EPS)
- **Revenue**: reported in thousands (e.g., 50000 = $50M revenue)
- Always divide by the appropriate factor when presenting to the user.

## Quick Reference Patterns

```
# Quick analysis of a stock
openquant_analyze(ticker="AAPL", days=90)

# Check if insiders are buying
openquant_insider_scan(ticker="AAPL", days=90)

# Get a strategy signal
openquant_strategy_run(strategy_name="insider-momentum", ticker="AAPL")

# Check risk before trading
openquant_risk_assessment(tickers="AAPL", days=252)

# Execute a paper trade (game mode)
openquant_trade_execute(action="BUY", ticker="AAPL", shares=10, price=178.50)

# Review portfolio
openquant_portfolio_status()
```
