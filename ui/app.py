import streamlit as st

st.title("IQS Trading Dashboard")

import json
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Allow `import iqs` without installing the package (optional, but keeps UI consistent).
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

STATE_PATH = Path("ui/ui_state.json")
LOG_PATH = Path("ui/ui_logs.txt")
LOCAL_TZ = ZoneInfo("Europe/Madrid")

st.markdown(
    """
<style>
.iqs-log {
  padding: 6px 10px;
  border-radius: 8px;
  margin: 4px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.9rem;
  line-height: 1.35rem;
  border: 1px solid rgba(255,255,255,0.10);
  word-break: break-word;
}
.iqs-cold { background: rgba(59, 130, 246, 0.25); }   /* blue */
.iqs-hot  { background: rgba(239, 68, 68, 0.22); }    /* red  */
.iqs-other{ background: rgba(148, 163, 184, 0.12); }  /* gray */
</style>
""",
    unsafe_allow_html=True,
)


def _classify_log_line(line: str) -> str:
    # We classify by component tags emitted by ui/demo_runner.py: "[Component] message"
    cold_markers = (
        "[ColdPathRunner",
        "[DataCalibrator",
    )
    hot_markers = (
        "[HotPathRunner",
        "[HotPathConfig",
        "[HotPathParams",
        "[SyntheticMarket",
        "[MarketDataFeed",
        "[EventDrivenTechnicalAnalyzer",
        "[FundamentalAnalyzer",
        "[ExecutionHandler",
        "[DemoOrchestrator",
        "[iqs.app.manager.Manager",
    )
    if any(m in line for m in cold_markers):
        return "iqs-cold"
    if any(m in line for m in hot_markers):
        return "iqs-hot"
    return "iqs-other"


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {
        "connection_status": "NO DATA",
        "symbol": "-",
        "last_price": None,
        "signal": "DON'T BUY",
        "position_state": "CLOSED",
        "last_event_time": "-",
        "last_error": None,
    }

status = load_state()

st.subheader("System status")

col1, col2, col3 = st.columns(3)

col1.metric("Connection", status["connection_status"])
col2.metric("Symbol", status["symbol"])
col3.metric("Last price", status["last_price"])

col4, col5 = st.columns(2)

col4.metric("Signal", status["signal"])
col5.metric("Position", status["position_state"])

st.caption(f"UI updated: {datetime.now(LOCAL_TZ).isoformat()}")
if status.get("last_event_time"):
    st.caption(f"Last event: {status.get('last_event_time')}")
if status.get("last_error"):
    st.warning(status["last_error"])

st.subheader("Recent logs")

if not LOG_PATH.exists():
    st.info("No logs yet. Start the demo runner to generate events.")
else:
    raw = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = raw[-200:]
    for line in reversed(tail):
        css = _classify_log_line(line)
        st.markdown(f"<div class='iqs-log {css}'>{line}</div>", unsafe_allow_html=True)