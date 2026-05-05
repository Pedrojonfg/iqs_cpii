# IQS Trading System

A Python-based trading system that connects to Interactive Brokers, transforms live ticks into **volume bars**, generates trading signals, and sends orders through a modular pipeline.

This project is designed as a practical, event-driven architecture for algorithmic trading.  
In plain English: it listens to market data, groups raw ticks into meaningful chunks, decides whether to buy/sell, and executes trades while exposing live system state in a Streamlit dashboard.

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

### Event-driven vs polling modes

IQS has two runtime modes controlled by `IQS_EVENT_DRIVEN`:

- `IQS_EVENT_DRIVEN=1` (**event-driven mode**, recommended):  
  uses tick subscriptions + volume-bar pipeline + `manager.on_volume_bar(...)`.

- `IQS_EVENT_DRIVEN=0` (**polling/legacy loop**):  
  main loop runs periodically and calls manager entry/exit management methods on a time cadence.

---

## Main Components

- `src/iqs/app/main.py`  
  Application entrypoint (`iqs` CLI). Loads `.env`, connects to IB, chooses mode (event-driven or polling), initializes all core services, and runs the main loop.

- `src/iqs/app/manager.py`  
  Orchestrator layer. Receives strategy decisions, performs fundamental veto checks, triggers execution, and writes UI state to `ui/ui_state.json`.

- `src/iqs/data/market_data_feed.py`  
  Converts tick stream into per-symbol volume bars using configurable bucket sizes (optionally loaded from calibration JSON).

- `src/iqs/strategy/technical.py`  
  Strategy layer:
  - `TechnicalAnalyzer` for historical/OHLCV checks
  - `EventDrivenTechnicalAnalyzer` for hot-path volume-bar decisions

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
IQS_EVENT_DRIVEN - mode switch:
1 = event-driven (volume bars)
0 = polling/legacy loop
Useful event-driven settings:

IQS_CALIBRATION_PATH - JSON file with per-symbol volume buckets
IQS_DEFAULT_BUCKET_VOLUME - fallback bucket if symbol calibration is missing
IQS_BAR_QUEUE_MAX - max queued bars before backpressure
##How to Run
Trading engine
iqs
Streamlit dashboard
streamlit run ui/app.py
##Running Without Interactive Brokers (Degraded Mode)
If IB is not reachable, main.py switches to degraded behavior:

connection status is written as DEGRADED_NO_IB in ui/ui_state.json
no live broker feed or order execution is performed
process stays alive and updates heartbeat/UI state periodically
This is useful for UI demos and operational monitoring when broker connectivity is down.

##UI Dashboard
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

##Notes
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

