# OpenQuant

**The open-source operating system for quant trading**

[![PyPI](https://img.shields.io/pypi/v/openquant.svg)](https://pypi.org/project/openquant/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Stars](https://img.shields.io/github/stars/openquant/openquant.svg)](https://github.com/openquant/openquant)

> Works without any API key. Zero config. Zero cost.

OpenQuant is an open-source quant trading framework that combines insider trading analysis, fundamental screening, technical signals, and risk management into a single system you can run from your terminal.

No LLM. No API key required. Pure quantitative analysis.

---

## Quick Start

```bash
pip install openquant
openquant run AAPL
```

That's it. OpenQuant ships with free data providers (yfinance, SEC EDGAR) and works out of the box.

```bash
# Full analysis of a stock
openquant run TSLA

# Insider trading scan
openquant insider AAPL

# Risk assessment
openquant risk MSFT

# Run a specific strategy
openquant strategy run insider-momentum --ticker AAPL

# Paper trading game mode
openquant game start --balance 10000
```

---

## Game Mode

Paper trading with gamification. Start with $10,000 in virtual capital, trade based on strategy signals, and unlock achievements.

```
$ openquant game start --balance 10000

+------------------------------------------+
|           GAME MODE                       |
|  Strategy: insider-momentum              |
|  Starting Balance: $10,000.00            |
|  Paper trading -- no real money at risk.  |
+------------------------------------------+

> BUY 10 AAPL @ $178.50
[FILLED] BUY 10.00 AAPL @ $178.50 = $1,785.00 | Balance: $8,215.00

> SELL 10 AAPL @ $185.20
[SOLD] 10.00 AAPL @ $185.20 (P/L: +$67.00)

Portfolio Value: $10,067.00 | P/L: +0.67%
Trades: 2 | Wins: 1 | Losses: 0

[*] Achievement Unlocked: First Trade
```

### Achievements

| Icon | Achievement | How to Unlock |
|------|------------|---------------|
| >    | First Trade | Execute your first trade |
| ~    | 3-Day Streak | Trade 3 days in a row |
| +    | 5 Wins | Close 5 profitable trades |
| ^    | 10% Return | Achieve 10% portfolio return |
| <>   | Diamond Hands | Hold a position for 30+ days |
| !    | Quick Draw | Trade within 5 minutes of a signal |

---

## Built-in Strategies

### Insider Momentum

Trade on insider buying momentum signals.

- **Trigger**: 3+ insider buys in same week OR CEO purchase
- **Entry**: Insider signal score > +40
- **Exit**: Stop loss at -5%, take profit at +15%, or 30-day time stop
- **Position size**: Half Kelly based on historical win rate

```bash
openquant strategy run insider-momentum --ticker AAPL
```

### Value Deep

Deep value investing based on fundamental criteria.

- **Criteria**: P/E < 15, ROE > 15%, Debt/Equity < 0.5, insider buying
- **Entry**: All value criteria met + insider score > 0
- **Exit**: P/E > 25 or fundamental deterioration
- **Hold**: Long-term

```bash
openquant strategy run value-deep --ticker BRK-B
```

### Earnings Surge

Capture post-earnings announcement drift.

- **Pre-earnings**: Buy if estimate revisions trending up + insider buying
- **Post-earnings**: Sell 2 days after if beat, sell immediately if miss
- **Hold**: Short-term (10-day time stop)

```bash
openquant strategy run earnings-surge --ticker NVDA
```

### Technical Breakout

Trend-following with insider confirmation.

- **Entry**: Price breaks above 50-day SMA with 2x volume + insider buying
- **Exit**: Price falls below 20-day SMA or stop at -3%
- **Hold**: Medium-term

```bash
openquant strategy run technical-breakout --ticker MSFT
```

---

## Brokers

OpenQuant supports a permission model for trade execution:

```
Game Mode (paper) --> Signal Mode (alerts only) --> Live Mode (real money)
```

You must explicitly confirm live trading. There are no accidents.

### Paper Broker (default)

In-memory paper trading. No API key required. Used by game mode.

```python
from openquant.brokers import PaperBroker

broker = PaperBroker(starting_balance=10000)
result = broker.place_order("AAPL", "BUY", 10, limit_price=150.00)
```

### Alpaca Broker

Commission-free trading via Alpaca. Paper keys by default.

```bash
pip install alpaca-trade-api
export ALPACA_API_KEY=your_key
export ALPACA_SECRET_KEY=your_secret
```

```python
from openquant.brokers import AlpacaBroker

# Paper trading (default)
broker = AlpacaBroker()

# Live trading (requires explicit confirmation)
broker = AlpacaBroker(paper=False, live_confirmed=True)
```

### Kalshi Broker

Prediction market contracts on Kalshi.

```bash
pip install kalshi-trade-api
export KALSHI_API_KEY=your_key
export KALSHI_API_SECRET=your_secret
```

```python
from openquant.brokers import KalshiBroker

broker = KalshiBroker()  # Demo mode
result = broker.place_order("INXD-2412-1000", "BUY", 10)
```

---

## MCP Integration

Connect OpenQuant to any AI agent via the Model Context Protocol.

```bash
pip install openquant[mcp]
openquant-mcp  # Starts the MCP server with SSE transport
```

### Available Tools

| Tool | Description |
|------|-------------|
| `openquant_analyze` | Full analysis of a ticker |
| `openquant_strategy_run` | Run a specific strategy |
| `openquant_strategy_list` | List available strategies |
| `openquant_portfolio_status` | Current portfolio state |
| `openquant_risk_assessment` | Portfolio risk metrics |
| `openquant_insider_scan` | Insider trading scan |
| `openquant_backtest` | Backtest a strategy |
| `openquant_game_status` | Game mode stats |
| `openquant_trade_execute` | Execute a paper trade |
| `openquant_trade_history` | Trade history |

### Example Agent Usage

```python
from openquant.mcp import create_server

server = create_server()
server.run(transport="sse")  # SSE for remote access
```

Connect from any MCP client (Claude, GPT, LangChain, etc.) and your agent can analyze stocks, run strategies, and execute paper trades.

---

## How It Works

OpenQuant runs 5 analysis agents in parallel, each producing a quantitative signal:

1. **Insider Agent** - Detects cluster buys, CEO activity, unusual trade sizes
2. **Value Agent** - Evaluates P/E, ROE, debt ratios, free cash flow
3. **Growth Agent** - Revenue growth, earnings acceleration, forward estimates
4. **Technical Agent** - SMA crossovers, RSI, MACD, volume patterns
5. **Sentiment Agent** - News flow, analyst consensus, estimate revisions

Strategies combine these signals with entry/exit rules and position sizing.

Data flows through a resolver chain: QuantFetch (if key) -> yfinance -> SEC EDGAR. Falls back automatically. Works without any API key.

---

## Comparison

| Feature | OpenQuant | ai-hedge-fund | OpenBB |
|---------|-----------|---------------|--------|
| Insider trading analysis | Yes | No | No |
| Game mode | Yes | No | No |
| Works without API key | Yes | No | Partial |
| Strategy backtesting | Yes | No | No |
| MCP server | Yes | No | No |
| Risk engine (VaR, Kelly) | Yes | No | No |
| Prediction markets (Kalshi) | Yes | No | No |
| Broker integration | Yes | No | No |
| Position sizing | Yes | No | No |
| No LLM required | Yes | No | Yes |
| Open source | Yes | Yes | Yes |

---

## Architecture

```
openquant/
  agents/         -- 5 analysis agents (insider, value, growth, technical, sentiment)
  strategies/     -- 4 built-in strategies (insider-momentum, value-deep, earnings-surge, technical-breakout)
  risk/           -- Risk engine (VaR, Kelly, position sizing, drawdown)
  insider/        -- Insider monitor + scorer (cluster detection, CEO signals)
  brokers/        -- Paper, Alpaca, Kalshi brokers
  game/           -- Game engine + achievements
  data/           -- Data providers + resolver chain
  mcp/            -- FastMCP server for AI agent integration
  cli/            -- Terminal interface (Click + Rich)
  config.py      -- YAML config management
  storage.py     -- Local JSONL/YAML storage
```

---

## Configuration

OpenQuant stores config in `~/.openquant/config.yaml`. It's created automatically on first run.

```yaml
brokers:
  paper:
    enabled: true
    mode: game
  alpaca:
    enabled: false
    mode: game
    api_key_env: ALPACA_API_KEY
    api_secret_env: ALPACA_SECRET_KEY

strategy_defaults:
  default_strategy: insider-momentum
  position_size_max: 0.25
  stop_loss_default: 0.05
  take_profit_default: 0.15
  confidence_threshold: 40

game_starting_balance: 10000
```

API keys are read from environment variables, never stored in config.

---

## Storage

All data stays local in `~/.openquant/`:

- `trades.jsonl` - Append-only trade log
- `positions.yaml` - Current positions
- `state.yaml` - Game engine state
- `strategies/` - Strategy results
- `config.yaml` - Configuration

No data leaves your machine.

---

## Contributing

We welcome contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas we need help with:
- More strategies (mean reversion, pairs trading, etc.)
- Additional broker integrations (Interactive Brokers, TD Ameritrade)
- More data providers (Polygon, Alpha Vantage)
- Web dashboard / UI
- Tests and documentation

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

**Built by traders, for traders. No API key required.**
