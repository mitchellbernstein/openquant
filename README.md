<div align="center">

# OpenQuant

### The open-source operating system for quant trading

**Works without any API key. Zero config. Zero cost.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/openquant.svg)](https://pypi.org/project/openquant/)

</div>

---

> **This is a proof of concept for an AI-powered personal hedge fund.**
> It uses a team of AI agents to analyze stocks, manage risk, and execute strategies — from your terminal.

---

## The Agents

| Agent | What It Does |
|-------|-------------|
| 🕵️ **Insider Sentiment** | Tracks Form 4 filings. Scores insider buying/selling momentum. |
| 📈 **Momentum** | Detects breakouts, trend shifts, and regime changes from OHLCV data. |
| 🔍 **Value Deep** | Digs into fundamentals — P/E, FCF, margins, balance sheet health. |
| 💰 **Earnings Surge** | Monitors EPS surprises, guidance shifts, and post-earnings drift. |
| 📊 **Analyst Consensus** | Aggregates Wall Street estimates and tracks revision momentum. |

Each agent generates independent signals. A risk engine sizes positions. You decide what to trade.

---

## 30-Second Demo

```bash
# Install
pip install openquant

# Run — no API key needed (uses yfinance by default)
openquant analyze AAPL

# Get structured JSON for your own agent
openquant --json analyze AAPL

# Check risk
openquant risk TSLA

# Track insiders
openquant insider NVDA

# Run a strategy
openquant strategy run insider-momentum -t AAPL
```

```
$ openquant analyze AAPL

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AAPL · Apple Inc. · Technology · Consumer Electronics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Price:    $198.42    Vol: 52,841,300    MCap: $3.01T
  52w High: $260.10    52w Low: $164.08

  ┌─ Signals ──────────────────────────────────────────┐
  │  🕵️ Insider Sentiment    BULLISH  (+0.72)          │
  │     3 insider buys in last 30 days                  │
  │                                                     │
  │  📈 Momentum            NEUTRAL  (+0.18)           │
  │     Price below 50-day MA, RSI: 44.2               │
  │                                                     │
  │  🔍 Value Deep           BULLISH  (+0.65)          │
  │     P/E 28.4x, FCF yield 3.8%, margins expanding   │
  │                                                     │
  │  💰 Earnings Surge       BULLISH  (+0.81)          │
  │     Last EPS: +8.2% surprise, guidance raised       │
  │                                                     │
  │  📊 Analyst Consensus    BULLISH  (+0.54)          │
  │     22 Buy / 6 Hold / 2 Sell, PT $225 avg          │
  └─────────────────────────────────────────────────────┘

  Risk:    Vol 22.4%  |  MaxDD 13.8%  |  Sharpe 0.99  |  VaR95 -2.0%
```

---

## How It Works

```
  Your Agent (Claude Code, Hermes, Codex...)
       │
       ▼
  ┌─────────────────────────────────────────┐
  │           OpenQuant Engine              │
  │                                         │
  │  ┌──────────┐  ┌──────────┐  ┌───────┐ │
  │  │ Data      │  │ Compute  │  │ Exec  │ │
  │  │           │  │          │  │       │ │
  │  │ yfinance  │  │ 5 agents │  │ Paper │ │
  │  │ SEC EDGAR │  │ Risk     │  │ Alpaca│ │
  │  │ QuantFetch│  │ Strategy │  │ Kalshi│ │
  │  └──────────┘  └──────────┘  └───────┘ │
  │                                         │
  │  Interfaces: CLI · TUI · MCP · JSON    │
  └─────────────────────────────────────────┘
       │              │            │
       ▼              ▼            ▼
    Terminal      AI Agents    Your Code
```

**Three layers, one engine:**
1. **Data** — yfinance (free), SEC EDGAR (free), or QuantFetch API (premium)
2. **Compute** — 5 analysis agents, risk engine, Monte Carlo VaR, strategy framework
3. **Execution** — Paper trading, Alpaca (stocks), Kalshi (prediction markets)

---

## Built-in Strategies

| Strategy | Signal | Style |
|----------|--------|-------|
| `insider-momentum` | Insider buying + price momentum | Aggressive growth |
| `value-deep` | Fundamental value + margin expansion | Patient value |
| `earnings-surge` | EPS surprise + guidance drift | Event-driven |
| `technical-breakout` | Breakout + volume confirmation | Momentum |

```bash
# List all strategies
openquant strategy list

# Run a strategy in paper mode
openquant strategy run insider-momentum -t AAPL -m paper

# Run in game mode (gamified paper trading with achievements)
openquant game start -s earnings-surge -b 100000
```

---

## Game Mode

Paper trading, but fun. Track your P&L, earn achievements, and compete on the leaderboard.

```bash
openquant game start -s value-deep -b 100000
```

- Start with $100K virtual capital
- Execute trades through any strategy
- Track wins, streaks, and risk management
- Upgrade to Signal Mode (real signals, manual approval) or Live Mode (automated with risk limits)

---

## For AI Agents

OpenQuant is designed to be the **hands** for any AI agent — Claude Code, Hermes, Codex, Cursor.

### MCP Server

```bash
# Start the MCP server (SSE transport)
openquant-mcp

# 10 tools available:
# openquant_analyze, openquant_strategy_run, openquant_risk_assessment,
# openquant_insider_scan, openquant_backtest, openquant_trade_execute,
# openquant_portfolio_status, openquant_game_status, openquant_trade_history,
# openquant_strategy_list
```

Connect from Claude Desktop, Cursor, or any MCP client:

```json
{
  "mcpServers": {
    "openquant": {
      "url": "http://localhost:8001/sse"
    }
  }
}
```

### JSON Output

Every CLI command supports `--json` for programmatic consumption:

```bash
openquant --json analyze AAPL | python3 -m json.tool
```

```json
{
  "command": "analyze",
  "ticker": "AAPL",
  "data": {
    "company_info": {"name": "Apple Inc.", "sector": "Technology"},
    "prices": [{"date": "2026-04-21", "close": 198.42, "volume": 52841300}],
    "signals": {
      "InsiderSentiment": {"score": 0.72, "direction": "bullish"},
      "Momentum": {"score": 0.18, "direction": "neutral"}
    },
    "risk": {"volatility": 22.4, "sharpe_ratio": 0.99, "var_95": -2.0}
  },
  "timestamp": "2026-04-22T14:30:00Z"
}
```

### Skill Files

Drop-in files for popular AI tools:

- **CLAUDE.md** — Claude Code instructions (MCP tools, trading workflow, risk rules)
- **AGENTS.md** — Codex/OpenCode instructions
- **.cursorrules** — Cursor AI rules
- **SKILLS/hermes.md** — Hermes agent skill (signal interpretation, position sizing)

---

## QuantFetch Integration

OpenQuant works out of the box with free data (yfinance + SEC EDGAR). For production-grade data, connect [QuantFetch](https://quantfetch.ai):

| | Free (yfinance) | QuantFetch Pro |
|---|---|---|
| **Stock prices** | ~800 tickers, 5yr history | 8,000+ tickers, 30yr history |
| **Financials** | Basic income/balance | Full XBRL with line items |
| **Insider trades** | Limited | All Form 4 filings, real-time |
| **SEC filings** | Basic metadata | Full-text search, section parsing |
| **Earnings** | Basic EPS | Surprises, guidance, consensus |
| **Crypto** | — | BTC, ETH, SOL + 50 more |
| **Speed** | Rate-limited | 100 req/day free, unlimited Pro |
| **Cost** | $0 | $29.99/mo |

```bash
# Set your QuantFetch API key
export QUANTFETCH_API_KEY=qf_demo_key_2026

# All commands automatically use QuantFetch when key is set
openquant analyze AAPL
```

Get a free API key at [quantfetch.ai](https://quantfetch.ai) — 100 requests/day, no credit card.

---

## Risk Engine

Built-in risk management that doesn't let you blow up:

- **Value at Risk (VaR)** — 95% and 99% confidence intervals
- **Monte Carlo simulation** — 10,000 path projections
- **Kelly criterion** — Optimal position sizing (with 0.25x conservative multiplier)
- **Max drawdown** — Historical worst-case tracking
- **Beta** — Market correlation for hedging
- **Stop-loss guards** — Automatic position limits

```bash
openquant risk AAPL
# Volatility: 22.4%  |  Max Drawdown: 13.8%  |  Sharpe: 0.99
# VaR 95%: -2.0%  |  Beta: 1.24  |  Rating: MODERATE
```

---

## Insider Monitor

Real-time scoring of insider Form 4 filings:

```bash
openquant insider AAPL
```

- Scores each filing: buy vs sell, size, officer vs director
- Aggregates 30-day insider sentiment score
- Flags cluster buying (multiple insiders buying simultaneously)
- Cross-references with price action for confirmation

---

## Architecture

```
src/openquant/
├── agent/          # Dual-loop agent (20-turn limit, streaming, risk hooks)
├── agents/         # 5 analysis agents (insider, momentum, value, earnings, analyst)
├── brokers/        # Paper, Alpaca, Kalshi execution
├── cli/            # Click-based CLI (--json, Rich output)
├── data/           # Pluggable data protocol (yfinance, SEC, QuantFetch)
├── game/           # Game mode engine (achievements, leaderboard)
├── insider/        # Insider scoring (Form 4, cluster detection)
├── mcp/            # MCP server (SSE transport, 10 tools)
├── risk/           # Risk engine (VaR, Monte Carlo, Kelly, sizing)
├── strategies/     # 4 built-in strategies + framework
└── tui/            # Textual TUI (watchlist, chat, portfolio panels)
```

---

## Install

```bash
pip install openquant
```

That's it. No API keys required. Works immediately with free data sources.

### With QuantFetch (optional)

```bash
export QUANTFETCH_API_KEY=your_key_here
```

Get a free key at [quantfetch.ai](https://quantfetch.ai).

---

## Comparison

| Feature | OpenQuant | virattt/ai-hedge-fund | OpenBB |
|---------|-----------|----------------------|--------|
| **Free data** | yfinance + SEC EDGAR | Requires API key | Requires API key |
| **Risk engine** | VaR, Monte Carlo, Kelly | None | Basic |
| **Strategy framework** | 4 built-in + custom | Single analysis script | None |
| **Paper trading** | Game mode + achievements | None | None |
| **Live execution** | Alpaca, Kalshi | None | None |
| **MCP server** | 10 tools | None | None |
| **AI agent support** | JSON, MCP, skill files | CLI only | SDK |
| **Insider monitoring** | Real-time scoring | Basic agent | Basic |
| **--json output** | All commands | None | Partial |
| **License** | MIT | MIT | MIT |

---

## Disclaimer

This is an educational and research tool. It is **not** financial advice. Trading involves substantial risk of loss. Past performance does not guarantee future results. Always do your own research and never trade money you can't afford to lose.

---

<div align="center">

**Built by [Mitchell Bernstein](https://x.com/mitchellbe) · Powered by [QuantFetch](https://quantfetch.ai)**

[Get a free API key](https://quantfetch.ai) · [Report a bug](https://github.com/mitchellbernstein/openquant/issues) · [Contribute](CONTRIBUTING.md)

</div>
