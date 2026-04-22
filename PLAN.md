# OpenQuant v0.2.0 — The Sentient Bloomberg Terminal

## TL;DR

OpenQuant is a **trading-first agent** + **beautiful terminal** + **MCP server**. It works three ways:
1. **Standalone** — `openquant` launches a Bloomberg-grade TUI with built-in AI chat
2. **Plugged in** — Hermes/Claude Code/Codex connect via MCP and get trading superpowers
3. **Skill files** — drop-in configs teach any agent how to trade

The built-in agent is NOT a general-purpose harness. It's a **trading specialist** — a thin conversational skin over quantitative tools. When you need cron, memory, recursive learning, multi-step orchestration — that's what Hermes is for. OpenQuant is the hands. The harness brings the brain.

QuantFetch is the backend. The TUI shows your account data — watchlists, simulations, strategies, portfolio, positions — synced from QuantFetch.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interfaces                           │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              OpenQuant TUI (Textual)                  │    │
│  │                                                       │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │    │
│  │  │Watchlist │ │ Portfolio│ │  Risk    │ │  Chat  │ │    │
│  │  │ + Prices │ │ + P&L   │ │ Dashboard│ │ Agent  │ │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │    │
│  │  │Insider  │ │ Strategy │ │  News    │ │Screenr │ │    │
│  │  │ Monitor │ │ Signals  │ │  Feed    │ │        │ │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ │    │
│  └───────────────────────┬─────────────────────────────┘    │
│                          │                                    │
│  ┌──────────────┐       │     ┌──────────────────────┐      │
│  │  CLI Commands │       │     │  External Agents     │      │
│  │  openquant    │       │     │  Hermes, CC, Codex   │      │
│  │  run AAPL     │       │     │  Cursor, OpenClaw    │      │
│  │  risk AAPL    │       │     │                      │      │
│  │  --json       │       │     │  + Skill Files       │      │
│  └──────┬───────┘       │     │  CLAUDE.md           │      │
│         │               │     │  AGENTS.md           │      │
│         │               │     │  .cursorrules        │      │
│         │               │     └──────────┬───────────┘      │
│         │               │                │                   │
└─────────┼───────────────┼────────────────┼───────────────────┘
          │               │                │
          ▼               ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server (SSE, 25 tools)                │
│                                                              │
│  Data: get_prices, get_insider, get_financials, get_news,   │
│        get_earnings, get_analyst_estimates, screen_stocks,   │
│        get_institutional, get_crypto, get_market_snapshot    │
│                                                              │
│  Compute: run_risk, get_signal, run_backtest,                │
│           calculate_position_size, compare_tickers            │
│                                                              │
│  Execute: game_trade, place_order, get_portfolio,            │
│           close_position, get_balance                         │
│                                                              │
│  Portfolio: get_watchlist, add_watchlist, set_alert,          │
│             get_game_state                                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   OpenQuant Engine                            │
│                                                              │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │
│  │   Data    │ │   Risk    │ │ Strategy  │ │  Broker   │  │
│  │ Providers │ │  Engine   │ │   Layer   │ │   Layer   │  │
│  │           │ │           │ │           │ │           │  │
│  │ yfinance  │ │ VaR/CVaR  │ │ Signal ABC│ │   Paper   │  │
│  │ SEC EDGAR │ │ Kelly     │ │ 4 built-in│ │  Alpaca   │  │
│  │QuantFetch │ │ Drawdown  │ │ Backtest  │ │  Kalshi   │  │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## The Built-In Agent: Architecture Decision

After inspecting 7 agent frameworks (OpenCode, pi-mono, sst/opencode, pydantic-ai, smolagents, agno, OpenCode Go), here's the decision:

### Why NOT adopt an existing framework?

| Framework | Why Not |
|-----------|---------|
| pydantic-ai | Graph abstraction overkill. We don't need UserPrompt->ModelRequest->CallTools nodes. |
| smolagents | Too simple — no before/after hooks, no context management, no parallel tool calls |
| agno/phidata | Too heavy — session persistence, memory managers, background hooks we don't need |
| OpenCode/pi-mono | Wrong language (Go/TypeScript) |

### What we BUILD: A trading-specialist agent loop

Steal the best patterns from all of them, adapted for trading:

**From pi-mono (the cleanest agent architecture):**
- Dual-loop pattern (outer: follow-up messages, inner: stream + execute + steer)
- `beforeToolCall` / `afterToolCall` hooks → our risk guardrails
- `terminate` hint on tool results → stop after risk check fails
- Event stream for TUI updates
- Parallel tool execution mode

**From agno/phidata (best tool organization):**
- `Toolkit` grouping → market_data_toolkit, risk_toolkit, execution_toolkit
- `stop_after_tool_call` → after `place_order`, stop and confirm
- `requires_confirmation` → dangerous operations need user approval
- `tool_hooks` middleware → logging, rate limiting

**From smolagents (simplest working agent):**
- Generator-based streaming
- `final_answer` tool for clean termination
- Planning steps (think before trading)

**From pydantic-ai (best developer UX):**
- Pydantic auto-schema from function signatures
- `infer_provider("openai:gpt-5.2")` pattern

**Agent loop estimate: ~400 lines of Python.** Not a general-purpose harness. Just:
1. User sends message
2. LLM reasons and calls trading tools
3. Tools execute (with risk guardrails)
4. Results feed back to LLM
5. LLM responds or calls more tools
6. Loop until `final_answer` or max turns

Uses **litellm** for LLM provider abstraction (100+ providers, one API).

What we DON'T build (that full harnesses have):
- Memory persistence across sessions → Hermes handles
- Cron scheduling → Hermes handles
- MCP client → we're a server, not client
- Multi-agent orchestration → external harness handles
- File editing tools → that's for coding agents
- Recursive/self-improving loops → external harness handles

---

## The TUI: Sentient Bloomberg Terminal

### Framework: Textual (35.5K stars)

Built on Rich. Full widget system. Async. The definitive Python TUI framework.

Key dependencies:
- `textual` — TUI framework
- `textual-plotext` — candlestick/line charts in terminal
- `textual-autocomplete` — fuzzy ticker search
- `rich` — styling (already used)
- `asciichart` — inline sparklines in tables

### Layout Design

Inspired by Bloomberg Terminal + cointop + ticker:

```
┌─ OpenQuant v0.2.0 ─── Mode: Research ─── Broker: Paper ── 14:32:05 ──┐
│ ┌─ Watchlist ────────┐ ┌─ AAPL ────────────────────────────────────┐  │
│ │ SYM   PRICE  CHG%  │ │ $252.82  ▼-3.2%  Vol: 32.1M             │  │
│ │ AAPL  252.82 -3.2  │ │ ┌─────────────────────────────────────┐  │  │
│ │ MSFT  415.50 +0.8  │ │ │         ▄▄▄█                       │  │  │
│ │ NVDA  920.15 +2.4  │ │ │    ▄▄▄██   █                       │  │  │
│ │ TSLA  258.75 -1.1  │ │ │ ▄▄██      █  ▄▄                    │  │  │
│ │ SPY   512.40 +0.5  │ │ │██         ███  ██                   │  │  │
│ │                     │ │ └─────────────────────────────────────┘  │  │
│ │ [1] Watchlist      │ │ 90d OHLCV | Insider: 6 sells (bearish)  │  │
│ │ [2] Portfolio      │ │ Risk: 95% VaR -4.1% | Kelly: 2.3%      │  │
│ │ [3] Risk           │ └─────────────────────────────────────────┘  │
│ │ [4] Chat     [F1]  │ ┌─ Strategy Signals ─────────────────────┐  │
│ │ [5] Insider  [F2]  │ │ value-deep:   -0.3 (slight sell)       │  │
│ │ [6] News     [F3]  │ │ insider-mom:  -0.7 (sell)              │  │
│ │ [7] Screener [F4]  │ │ earnings:     +0.1 (neutral)           │  │
│ │ [8] Markets  [F5]  │ │ technical:    +0.5 (buy)               │  │
│ └─────────────────────┘ │ COMPOSITE:    -0.1 (neutral)           │  │
│                          └───────────────────────────────────────┘  │
│ ┌─ Chat ─────────────────────────────────────────────────────────┐  │
│ │ > how's AAPL looking compared to MSFT?                         │  │
│ │                                                                 │  │
│ │ [calling get_prices(AAPL), get_prices(MSFT), run_risk(AAPL)]   │  │
│ │                                                                 │  │
│ │ AAPL down 3.2% over 90d with 6 insider sells. MSFT up 0.8%    │  │
│ │ with no insider activity. Risk is higher on AAPL (VaR -4.1%    │  │
│ │ vs -2.3%). MSFT looks safer here.                              │  │
│ │                                                                 │  │
│ │ > _                                                              │  │
│ └─────────────────────────────────────────────────────────────────┘  │
│ [Tab] Panels [1-8] Switch [q] Quit [?] Help [/] Command             │
└──────────────────────────────────────────────────────────────────────┘
```

### TUI Key Bindings

| Key | Action |
|-----|--------|
| 1-8 | Switch panel focus |
| Tab | Cycle panels |
| / | Command bar (search, go to ticker, set alert) |
| ? | Help overlay |
| q | Quit |
| Enter | In chat: send message. In watchlist: drill into ticker |
| F1-F5 | Quick panel groups |
| j/k | Scroll within panels (vim) |
| g/G | Top/bottom of list |

### Bloomberg Principles We Steal

1. **Information density** — maximum data in minimum space, glanceable in <2s
2. **Command-first** — `/` opens command bar, type `AAPL` to go to ticker
3. **Color as signal** — green=up, red=down, yellow=warning, cyan=highlight
4. **Keyboard-driven** — every action has a shortcut
5. **Progressive disclosure** — summary first, drill down on demand
6. **Persistent state** — remember layouts, watchlists, preferences in ~/.openquant/
7. **Real-time everywhere** — prices update live via QuantFetch SSE/polling

---

## QuantFetch as Backend

The TUI connects to QuantFetch API. Your account determines what you see:

| Feature | Free (no key) | With API Key | Pro/Alpha |
|---------|--------------|-------------|-----------|
| Data source | yfinance + SEC EDGAR | QuantFetch API | QuantFetch API |
| Watchlist | Local only | Synced to account | Synced |
| Portfolio | Game mode only | Paper + Real | Paper + Real |
| Strategies | 4 built-in | Custom + share | Custom + share |
| Chat AI | Your API key | Your API key | Included |
| History | Session only | Persisted | Persisted |

When logged in (`openquant login`), the TUI shows:
- Your watchlists from QuantFetch account
- Your portfolio positions (real or paper)
- Your saved strategies and backtests
- Your game mode progress and achievements
- Your alert history

---

## virattt v2 Competitive Gap

**v2 is 90% stubs.** Only the data layer and signal base class have real code. Everything else (portfolio, risk, backtesting, validation, execution) is docstring-only.

**What v2 has on paper but hasn't built:**
- Marchenko-Pastur eigenvalue cleaning
- Almgren-Chriss execution model
- CPCV/PBO validation
- Event study framework
- Point-in-time data constraints

**What OpenQuant has that v2 doesn't:**
- Actually working code (risk engine, strategies, brokers, MCP)
- Multiple data providers (not locked to FD API)
- Interactive interface (TUI + chat + CLI)
- MCP server for external agents
- Broker execution (paper + Alpaca + Kalshi)
- Skill files for agent integration

**Our positioning:** v1 is a chat demo. v2 is a vision document. OpenQuant is working software you can use today.

---

## Updated Task List

### Phase 1: MCP Server → 25 Tools
**Priority: HIGH. This is the crown jewel.**

Current 10 tools → target 25.

- [ ] 1.1 get_earnings
- [ ] 1.2 get_analyst_estimates
- [ ] 1.3 get_institutional_holdings
- [ ] 1.4 screen_stocks
- [ ] 1.5 get_crypto_prices
- [ ] 1.6 get_market_snapshot
- [ ] 1.7 run_backtest (basic)
- [ ] 1.8 calculate_position_size
- [ ] 1.9 compare_tickers
- [ ] 1.10 place_order (broker)
- [ ] 1.11 get_portfolio
- [ ] 1.12 close_position
- [ ] 1.13 get_account_balance
- [ ] 1.14 get_watchlist / add_watchlist
- [ ] 1.15 get_game_state

### Phase 2: Trading Agent Loop
**Priority: HIGH. This is the built-in brain.**

- [ ] 2.1 Install litellm dependency
- [ ] 2.2 Build `openquant/agent/loop.py` — async agent loop (~400 lines)
  - Dual-loop pattern from pi-mono
  - Generator-based streaming from smolagents
  - beforeToolCall / afterToolCall hooks (risk guardrails)
  - Event stream for TUI
  - Max turns / doom loop detection
  - final_answer termination
- [ ] 2.3 Build `openquant/agent/tools.py` — trading tool schemas
  - Pydantic auto-schema from function signatures
  - Toolkit grouping: market_data, risk, strategy, execution, portfolio
  - stop_after_tool_call for place_order
  - requires_confirmation for dangerous ops
- [ ] 2.4 Build `openquant/agent/system.py` — system prompts
  - Hedge fund analyst persona
  - Trading context injection (current portfolio, open positions)
  - Risk management conventions (0.25x Kelly)
- [ ] 2.5 Build `openquant/agent/providers.py` — LLM provider config
  - litellm for 100+ providers
  - Model string format: "openai/gpt-4o-mini", "anthropic/claude-sonnet-4"
  - Fallback model support
  - Local model support (ollama)

### Phase 3: Textual TUI
**Priority: HIGH. This is the flagship experience.**

- [ ] 3.1 Install textual, textual-plotext, textual-autocomplete
- [ ] 3.2 Build `openquant/tui/app.py` — main Textual app
  - Configurable grid layout with named panels
  - Keyboard shortcuts (1-8, Tab, /, ?, q, j/k)
  - Persistent state (~/.openquant/tui-state.json)
  - Dark theme with finance color scheme
- [ ] 3.3 Build `openquant/tui/panels/watchlist.py`
  - Live prices (streaming or polling)
  - Ticker search with fuzzy autocomplete
  - Progressive disclosure (flags add detail)
  - Group/tab cycling
- [ ] 3.4 Build `openquant/tui/panels/portfolio.py`
  - Position tracking with P&L
  - Cost basis lots
  - Allocation breakdown
  - Game mode stats
- [ ] 3.5 Build `openquant/tui/panels/ticker_detail.py`
  - Price chart (textual-plotext candlestick/line)
  - Time frame switching (1D/1W/1M/3M/6M/1Y/5Y)
  - Insider trade summary
  - Risk metrics
  - Strategy signals
- [ ] 3.6 Build `openquant/tui/panels/chat.py`
  - Conversational interface with agent loop
  - Streaming output
  - Tool call visualization (showing which tools are being called)
  - Slash commands (/model, /tools, /cost, /clear)
- [ ] 3.7 Build `openquant/tui/panels/risk_dashboard.py`
  - VaR/CVaR display
  - Position sizing (Kelly)
  - Drawdown chart
  - Correlation matrix (top holdings)
- [ ] 3.8 Build `openquant/tui/panels/insider_monitor.py`
  - Recent insider trades across watchlist
  - Sentiment scoring (cluster detection)
  - Alerts for unusual activity
- [ ] 3.9 Build `openquant/tui/panels/news.py`
  - News feed for active ticker / watchlist
  - Sentiment coloring
- [ ] 3.10 Build `openquant/tui/panels/screener.py`
  - Stock screener with filter bar
  - Pre-built screens (value, growth, momentum, insider buying)
- [ ] 3.11 Add `openquant tui` CLI command
- [ ] 3.12 Merge quant-cli REPL pieces (OAuth, onboarding, slash commands)
- [ ] 3.13 Delete quant-cli repo (fold complete)

### Phase 4: Skill Files for External Agents
**Priority: MEDIUM. Distribution hack.**

- [ ] 4.1 `SKILLS/hermes.md` — Hermes skill
  - MCP server connection config
  - When to use each tool
  - Risk management conventions
  - Strategy workflow patterns
- [ ] 4.2 `CLAUDE.md` — Claude Code instructions
  - MCP connection + trading context
  - Tool usage guide
  - Risk constraints
- [ ] 4.3 `AGENTS.md` — Codex/OpenCode instructions
  - Same content, different format
- [ ] 4.4 `.cursorrules` — Cursor AI rules
- [ ] 4.5 `skills/openquant-trading/SKILL.md` — installable Hermes skill
- [ ] 4.6 Test: Hermes connects to MCP and runs a full analysis
- [ ] 4.7 Test: Claude Code uses tools via MCP

### Phase 5: CLI Improvements
**Priority: MEDIUM. Power user features.**

- [ ] 5.1 Add `--json` flag to all CLI commands
- [ ] 5.2 Add `--format csv` option
- [ ] 5.3 Add `openquant chat` command (non-TUI, just agent loop in terminal)
- [ ] 5.4 Add `openquant login` (QuantFetch OAuth)
- [ ] 5.5 Add `openquant config` (set API keys, default provider, etc.)

### Phase 6: Viral README + Distribution
**Priority: LOW. Do last, needs everything working.**

- [ ] 6.1 One-liner install (`pip install openquant`)
- [ ] 6.2 "Works free" demo
- [ ] 6.3 MCP connection example (3 lines)
- [ ] 6.4 Skill file drop-in for Hermes/Claude Code
- [ ] 6.5 Comparison table vs ai-hedge-fund + financialdatasets.ai
- [ ] 6.6 TUI screenshots
- [ ] 6.7 Demo GIF
- [ ] 6.8 Blog post: "Your AI can trade. Here's how."

---

## Execution Order

```
Phase 1 (MCP)  ──┐
                  ├── Phase 2 (Agent) ──┐
Phase 3 (TUI)  ──┘                      ├── Phase 4 (Skills)
                                         ├── Phase 5 (CLI)
                                         └── Phase 6 (README)
```

Phase 1 + 3 can start in parallel (different code paths).
Phase 2 depends on Phase 1 (agent uses MCP tools).
Phase 4 + 5 + 6 happen after 1-3.

---

## Estimated Effort

| Phase | Time | Can Parallelize? |
|-------|------|------------------|
| Phase 1: MCP 25 tools | 4-6 hours | Yes, with Phase 3 |
| Phase 2: Agent loop | 4-6 hours | After Phase 1 |
| Phase 3: Textual TUI | 8-12 hours | Yes, with Phase 1 |
| Phase 4: Skill files | 2-3 hours | After Phase 1 |
| Phase 5: CLI improvements | 2-3 hours | After Phase 1+2 |
| Phase 6: README + distribution | 2-3 hours | Last |
| **Total** | **22-33 hours** | |

---

## New Dependencies

```
# Agent
litellm>=1.0

# TUI
textual>=3.0
textual-plotext>=0.2
textual-autocomplete>=0.1
asciichart>=1.5

# Already have
rich>=13.0
click>=8.0
pydantic>=2.0
```

---

## File Structure After v0.2.0

```
openquant/
├── src/openquant/
│   ├── __init__.py
│   ├── config.py
│   ├── storage.py
│   │
│   ├── agent/              # Built-in trading agent
│   │   ├── __init__.py
│   │   ├── loop.py         # Agent loop (~400 lines)
│   │   ├── tools.py        # Tool schemas + toolkit grouping
│   │   ├── system.py       # System prompts
│   │   └── providers.py    # LLM provider config (litellm)
│   │
│   ├── data/               # Data providers
│   │   ├── __init__.py
│   │   ├── protocol.py
│   │   ├── resolver.py
│   │   ├── yfinance_provider.py
│   │   ├── sec_edgar_provider.py
│   │   └── quantfetch_provider.py
│   │
│   ├── risk/               # Risk engine
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── models.py
│   │   ├── sizing.py
│   │   └── var.py
│   │
│   ├── insider/            # Insider monitor
│   │   ├── __init__.py
│   │   ├── monitor.py
│   │   ├── scorer.py
│   │   └── models.py
│   │
│   ├── strategies/         # Trading strategies
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── insider_momentum.py
│   │   ├── value_deep.py
│   │   ├── earnings_surge.py
│   │   └── technical_breakout.py
│   │
│   ├── game/               # Game mode
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── models.py
│   │
│   ├── brokers/            # Broker integrations
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── paper.py
│   │   ├── alpaca.py
│   │   └── kalshi.py
│   │
│   ├── mcp/                # MCP server
│   │   ├── __init__.py
│   │   └── server.py       # 25 tools
│   │
│   ├── tui/                # Textual TUI
│   │   ├── __init__.py
│   │   ├── app.py          # Main app
│   │   ├── panels/
│   │   │   ├── watchlist.py
│   │   │   ├── portfolio.py
│   │   │   ├── ticker_detail.py
│   │   │   ├── chat.py
│   │   │   ├── risk_dashboard.py
│   │   │   ├── insider_monitor.py
│   │   │   ├── news.py
│   │   │   └── screener.py
│   │   └── theme.py
│   │
│   └── cli/                # CLI commands
│       ├── __init__.py
│       ├── main.py
│       └── display.py
│
├── SKILLS/                 # Agent skill files
│   └── hermes.md
├── CLAUDE.md
├── AGENTS.md
├── .cursorrules
│
├── pyproject.toml
├── README.md
├── PLAN.md
└── LICENSE
```
