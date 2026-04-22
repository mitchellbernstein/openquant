# OpenQuant Trading — Hermes Skill

## Overview

OpenQuant is an open-source quant trading framework with MCP server integration. This skill teaches you how to connect to OpenQuant, use its tools effectively, and follow proper risk management when analyzing and trading stocks.

## MCP Server Connection

Start the server:
```bash
pip install openquant[mcp]
openquant-mcp
```

Default endpoint: `http://localhost:8000/sse` (SSE transport)

Connect as an MCP client with SSE transport to that URL. Alternatively, spawn `openquant-mcp` as a stdio process.

The server name is `openquant`. No authentication required to connect — data access uses the resolver chain internally.

## Available Tools (10)

### Research & Analysis Layer

**`openquant_analyze(ticker, days=90)`**
Full analysis of a stock. Returns current price, 52-day range, insider score (with label, patterns, alerts), and risk metrics (risk_level, var_95, max_drawdown, kelly_fraction, warnings). This is your first call for any new ticker — it combines multiple data sources into one report.

**`openquant_insider_scan(ticker, days=90)`**
Deep insider trading scan. Returns ticker, score (-100 to +100), label (STRONG BUY through STRONG SELL), detected patterns, alerts, trade_count, buy_count, sell_count. Use this when you need the full insider picture that `openquant_analyze` summarizes.

**`openquant_risk_assessment(tickers, days=252)`**
Risk metrics for one or more tickers. `tickers` is comma-separated (e.g., "AAPL,MSFT"). Returns risk_level (VERY LOW / LOW / MODERATE / HIGH), var_95, var_99, max_drawdown, kelly_fraction, position_sizes (per ticker), warnings, recommendations. **Always call this before any trade execution.**

### Strategy & Signals Layer

**`openquant_strategy_list()`**
Returns the 4 available strategies: insider-momentum, value-deep, earnings-surge, technical-breakout. Call this when the user asks what strategies are available.

**`openquant_strategy_run(strategy_name, ticker)`**
Generate a trading signal from a specific strategy. Returns: strategy name, ticker, action (BUY/SELL/HOLD), confidence (0–100), entry_price, stop_loss, take_profit, position_size_pct, reasoning. This is the actionable signal — use it to decide whether to trade.

**`openquant_backtest(strategy_name, ticker, days=252)`**
Backtest a strategy on historical data. Returns: total_trades, win_rate, total_return, max_drawdown, sharpe_ratio, avg_holding_days. Use this to validate a strategy before trusting its signals.

### Portfolio & Execution Layer

**`openquant_portfolio_status()`**
Current portfolio: balance, total_value, total_pnl, total_pnl_pct, trade_count, win_count, loss_count, positions (dict of ticker → shares/avg_price/current_price/unrealized_pnl/pnl_pct), achievements. Call before and after trades to see impact.

**`openquant_trade_execute(action, ticker, shares, price)`**
Execute a paper trade in game mode. `action` is "BUY" or "SELL". Returns success, ticker, action, shares, price, total_cost, message, new_balance. **This modifies state — only call after user confirmation.**

**`openquant_trade_history(limit=20)`**
Recent trade log. Returns list of trade dicts. Use to review past decisions.

**`openquant_game_status()`**
Game mode leaderboard and stats. Use for gamification context.

## Tool Combination Patterns

These composite patterns handle common scenarios efficiently:

### Full Stock Analysis
```
analyze_stock = openquant_analyze(ticker) → openquant_insider_scan(ticker) → openquant_risk_assessment(ticker)
```
Start with `openquant_analyze` for the overview, then drill into insider details and risk. This gives you the full picture.

### Strategy Validation Before Trading
```
validate = openquant_strategy_run(strategy, ticker) → openquant_backtest(strategy, ticker) → openquant_risk_assessment(ticker)
```
Run the strategy signal, verify it with a backtest, then assess risk. Only proceed to execution if all three align.

### Portfolio Review
```
review = openquant_portfolio_status() → openquant_trade_history(limit=10)
```
Check current positions and recent trade history together to understand the portfolio state.

### New Trade Decision
```
decide = openquant_analyze(ticker) → openquant_strategy_run(strategy, ticker) → openquant_risk_assessment(ticker) → [CONFIRM WITH USER] → openquant_trade_execute(...)
```
Never skip the risk assessment or user confirmation step.

## Interpreting Signals

### Agent Signals (-1.0 to +1.0)

The 5 analysis agents (insider, value, growth, technical, sentiment) each produce a signal:

| Range | Direction | Meaning |
|-------|-----------|---------|
| +1.0 to +0.7 | STRONG BULLISH | High conviction buy signal |
| +0.7 to +0.4 | MODERATE BULLISH | Cautiously bullish |
| +0.4 to +0.3 | WEAK BULLISH | Marginal buy signal |
| +0.3 to -0.3 | NEUTRAL | No actionable signal |
| -0.3 to -0.4 | WEAK BEARISH | Marginal sell signal |
| -0.4 to -0.7 | MODERATE BEARISH | Cautiously bearish |
| -0.7 to -1.0 | STRONG BEARISH | High conviction sell signal |

### Insider Scores (-100 to +100)

| Score Range | Label | Action |
|-------------|-------|--------|
| +60 to +100 | STRONG BUY | Strong insider buying conviction |
| +25 to +59 | BUY | Insider buying detected |
| -24 to +24 | NEUTRAL | No clear insider pattern |
| -59 to -25 | SELL | Insider selling detected |
| -100 to -60 | STRONG SELL | Heavy insider selling |

### Strategy Confidence (0–100)

- **>= 60**: High conviction — proceed to risk check and potential execution
- **40–59**: Moderate — proceed with caution, may want additional confirmation
- **< 40**: Low conviction — monitor only, do not trade

### Strategy Actions

- **BUY**: Strategy recommends entering a long position
- **SELL**: Strategy recommends exiting or shorting
- **HOLD**: No action recommended — either already in position or no clear signal

## Risk Management Workflow

### Before Every Trade

1. **Call `openquant_risk_assessment`** — get var_95, max_drawdown, kelly_fraction
2. **Check risk_level** — if HIGH, reduce position size or skip the trade
3. **Verify position size** — must not exceed 10% of portfolio value
4. **Check Kelly fraction** — position_size_pct should use 0.25x Kelly (built into tools)
5. **Confirm multi-factor alignment** — prefer trades where 2+ agents agree

### Risk Rules (Non-Negotiable)

- **0.25x Kelly**: Quarter-Kelly for all position sizing. If the tool says 5%, that's already quarter-Kelly. Do not multiply by 4.
- **Max 10% position**: Hard limit per single position. The system enforces this.
- **Confidence >= 40**: Only trade when strategy confidence meets this threshold.
- **VaR awareness**: Show the user the 95% VaR before executing. If VaR > 10% of portfolio, flag the risk.

### Position Sizing Logic

The `position_size_pct` in strategy results is already calculated using:
1. Full Kelly fraction from risk assessment
2. Multiplied by 0.25 (quarter-Kelly)
3. Capped at 10% of portfolio

Do not re-calculate or override this. Trust the tool output.

## When to Hand Off to Execution

Only proceed to `openquant_trade_execute` when ALL of these conditions are met:

1. Strategy action is BUY or SELL (not HOLD)
2. Strategy confidence >= 40
3. Risk assessment has been run and shown to user
4. At least 2 agents agree on direction (check via `openquant_analyze` signals)
5. User has given explicit confirmation

### Stay in Research Mode When

- The user asks "what do you think about X?" — analyze, don't trade
- Strategy confidence < 40 — signal is too weak
- Risk level is HIGH — flag the concern, don't execute
- User hasn't explicitly confirmed — always ask first
- You're comparing multiple stocks — complete the comparison first

## QuantFetch Data Unit Conventions

QuantFetch (when available via `QUANTFETCH_API_KEY`) reports data in specific units:

| Data Type | Unit | Example | Conversion |
|-----------|------|---------|------------|
| Earnings per share | Cents | 250 means $2.50 EPS | Divide by 100 |
| Revenue | Thousands | 50000 means $50M | Divide by 1000 |
| Insider trade amounts | Dollars | 500000 means $500K | Use as-is |

Always convert before presenting to the user. The raw numbers from QuantFetch are not in standard dollar units for EPS and revenue.

## Built-in Strategies

### insider-momentum
Trigger: 3+ insider buys in same week OR CEO purchase. Entry: insider signal > +40. Exit: stop at -5%, profit at +15%, or 30-day time stop. Position: half-Kelly. Best for short-term momentum.

### value-deep
Criteria: P/E < 15, ROE > 15%, Debt/Equity < 0.5, insider buying. Entry: all criteria met + insider score > 0. Exit: P/E > 25 or fundamental deterioration. Long-term hold.

### earnings-surge
Pre-earnings: buy if estimate revisions trending up + insider buying. Post-earnings: sell 2 days after beat, sell immediately if miss. 10-day time stop. Best for earnings season.

### technical-breakout
Entry: price breaks 50-day SMA with 2x volume + insider buying. Exit: below 20-day SMA or -3% stop. Medium-term hold.

## CLI Alternative

If MCP is not available, use the CLI directly:
```bash
openquant run AAPL              # Full analysis
openquant insider AAPL          # Insider scan
openquant risk MSFT             # Risk assessment
openquant strategy run insider-momentum --ticker AAPL  # Strategy signal
openquant game start --balance 10000  # Paper trading
```

## Safety Guardrails

- Never execute live trades without user confirmation
- All analysis is educational — you are not a registered investment advisor
- Paper/game mode is the default and safe for experimentation
- Data stays local in `~/.openquant/` — nothing leaves the machine
- QuantFetch API key is optional — the system works with free yfinance data
