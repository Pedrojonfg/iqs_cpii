# IQS Trading System

> **Note:** this is an academic project, not a production system. It has never
> operated with real capital. The goal is the event-driven infrastructure itself
> (tick ingestion, volume bar construction, hot/cold path separation, an
> execution layer with risk validations) — not a validated strategy. The
> included technical strategy (VWAP bands with a trailing stop, `strategy/hotpath.py`) is an
> example to exercise the end-to-end pipeline, deliberately replaceable: the design is meant so that
> any strategy (yours) can be plugged in on top of this base.

## Known Limitations

- **SELL position sizing** (`EventDrivenTechnicalAnalyzer.on_volume_bar`) is
  fixed at `quantity=1.0` and does not query the actual open position size
  from the broker. A real deployment would need the broker abstraction to
  expose per-symbol position size (it currently only exposes the list of
  symbols with open positions), and `Manager` would need to use it before
  closing.
- **No portfolio-level risk management**: no max drawdown, no exposure limits
  across the universe, no correlation checks across the hand-picked European
  A&D basket in `main.py`.
- **No reconnection/reconciliation logic**: if the IB connection drops
  mid-session, the process stops feeding bars until manually restarted; no
  re-subscription or order-state reconciliation on reconnect.
- **Broker coupling**: `BrokerData`/`ExecutionHandler` are written directly
  against `ib_insync`; there's no broker-agnostic interface, so swapping
  broker would mean rewriting both.

---

A Python-based trading system that connects to Interactive Brokers, transforms live ticks into **volume bars**, generates trading signals, and sends orders through a modular pipeline.

This project is designed as a practical, event-driven architecture for algorithmic trading.  
In plain English: it listens to market data, groups raw ticks into meaningful chunks, decides whether to buy/sell, and executes trades while exposing live system state in a Streamlit dashboard.

---

## LLM veto layer

Before a `BUY` reaches execution, `Manager` asks `FundamentalAnalyzer` for a verdict
(`CLEAR` / `VETO`). The LLM is a **guardrail, not a signal source**: it can only block
an entry the technical strategy already proposed, never create one.

**Design rules**

- **Fail-closed.** Anything that is not an explicit, valid `CLEAR` is a `VETO`: missing
  API key, no headlines, malformed JSON, a `decision` outside `{CLEAR, VETO}`, timeout,
  open circuit breaker. (Absence of news is *not* a green light: with an empty headline
  list the model is never called.)
- **Untrusted input.** Headlines are truncated (100 chars), XML-escaped, wrapped in
  `<news><new>...</new></news>` and the system prompt declares that block as data only.
  A headline cannot close the block (covered by tests).
- **Cheap and auditable.** Verdicts are cached per ticker for 30 min *keyed on the exact
  headlines* (new headlines trigger a fresh call). Every verdict is appended to
  `veto_audit.log` (path: `IQS_VETO_AUDIT_LOG`) with model and a hash of the headlines.
- **Isolated failures.** Timeouts and a circuit breaker around both the news fetch and the
  LLM call.

**What this does *not* show**

- The prompt-injection defence is a mitigation (escaping + prompt instructions), not a
  proof. The tests check that a malicious headline cannot break the XML structure and
  that invalid model output is vetoed; they do not measure how often a real model obeys
  an injected instruction.
- There is **no evaluation** of whether the veto improves outcomes (precision/recall on
  labelled headlines, or a backtest). Headlines come from yfinance (titles only) and the
  prompt is tuned for European aerospace & defence.
- `ui/demo_runner.py` calls the real veto but has `override_veto_for_demo=True` so the
  BUY→SELL walkthrough completes; a demo run is not evidence of what the veto blocks.

---

## What This Project Does (and Why)

Traditional bots often poll prices on a timer (for example, every minute). That can miss important micro-moves or react too slowly during volatile periods.

IQS focuses on an event-driven flow:

- reacts to **market events** (ticks and volume bars), not just fixed time intervals
- separates responsibilities into clear components (data, strategy, manager, execution)
- keeps a simple UI state file (`ui/ui_state.json`) so the dashboard can show current status without tight coupling to the trading engine
- supports a **degraded mode** when IB is unavailable, so monitoring/UI can still run

---

## Architecture Overview

### Data flow

`ticks -> volume bars -> strategy -> manager -> execution`

1. **Ticks** arrive from IB (`BrokerData.subscribe_to_data`).
2. `MarketDataFeed` accumulates ticks per symbol until a volume bucket is reached.
3. A `VolumeBar` event is emitted to an async queue.
4. Strategy (`EventDrivenTechnicalAnalyzer`) processes each bar and returns a decision (`BUY`, `SELL`, or `DON'T BUY`).
5. `Manager` applies orchestration logic (including fundamental/LLM veto for entries), updates UI state, and calls execution.
6. `ExecutionHandler` validates and places IB orders (limit or bracket).

### Event-driven architecture

IQS runs in **event-driven mode only**: tick subscriptions feed a volume-bar
pipeline and each completed bar is dispatched to `manager.on_volume_bar(...)`.
There is no polling/legacy loop.

---

## Main Components

- `src/iqs/app/main.py`  
  Application entrypoint (`iqs` CLI). Loads `.env`, connects to IB, initializes all core services, and runs the event-driven main loop.

- `src/iqs/app/manager.py`  
  Orchestrator layer. Receives strategy decisions, performs fundamental veto checks, triggers execution, and writes UI state to `ui/ui_state.json`.

- `src/iqs/data/market_data_feed.py`  
  Converts tick stream into per-symbol volume bars using configurable bucket sizes (optionally loaded from calibration JSON).

- `src/iqs/strategy/technical.py`  
  Strategy layer:
  - `EventDrivenTechnicalAnalyzer` for hot-path volume-bar decisions

- `src/iqs/services/` (`news.py`, `nlp_veto.py`, `fundamental.py`)  
  Fundamental veto layer: yfinance headlines -> sanitisation -> LLM (Groq). See "LLM veto layer" below.

- `src/iqs/execution/execution.py`  
  Execution adapter around `ib_insync`. Validates order inputs and submits limit or bracket orders to IB.

---

## Setup


### 1) Clone the repository

```bash
git clone <your-repo-url>
cd iqs_cpii
```

### 2) Create and activate Conda environment
conda env create -f environment.yml
conda activate iqs_env
### 3) Install package in editable mode
pip install -e .

## Configuration (.env)
Create a .env file (or copy from .env.example) in the project root.

Core variables:

IB_HOST - IB Gateway/TWS host (example: 127.0.0.1)
IB_PORT - IB Gateway/TWS port (example: 7497)
IB_CLIENT_ID - IB client ID for the session

Useful event-driven settings:

IQS_CALIBRATION_PATH - JSON file with per-symbol volume buckets
IQS_DEFAULT_BUCKET_VOLUME - fallback bucket if symbol calibration is missing
IQS_BAR_QUEUE_MAX - max queued bars before backpressure
## How to Run
Trading engine
iqs
Streamlit dashboard
streamlit run ui/app.py
## Running Without Interactive Brokers (Degraded Mode)
If IB is not reachable, main.py switches to degraded behavior:

connection status is written as DEGRADED_NO_IB in ui/ui_state.json
no live broker feed or order execution is performed
process stays alive and updates heartbeat/UI state periodically
This is useful for UI demos and operational monitoring when broker connectivity is down.

## UI Dashboard
The Streamlit app (ui/app.py) reads:

ui/ui_state.json for current system state:
connection status
symbol
last price
signal
position state
last event/error
ui/ui_logs.txt for recent logs (color-coded by component tags)
It gives a lightweight real-time view of engine health and latest decision context.

## Notes
Python requirement is >=3.12 (see pyproject.toml).
Main CLI entrypoint is registered as iqs = iqs.app.main:cli.
For local development, tests are available under tests/.
## Technical Notes

### Performance
- The technical analysis layer uses `numba` for performance-critical calculations.

### Calibration
- Calibration runs when the market is closed and uses the Jarque-Bera test as part of the validation/calibration process.

### Deployment
- The project is designed to be deployed on a VPS, with deployment-related files under `/deploy`.

### LLM Safety
- The LLM-based veto layer is designed to reduce prompt-injection risk.

