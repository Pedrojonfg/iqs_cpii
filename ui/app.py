import streamlit as st

st.title("IQS Trading Dashboard")

st.write("UI working 🚀")

import json
from pathlib import Path

STATE_PATH = Path("ui/ui_state.json")

def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
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

st.subheader("Estado del sistema")

col1, col2, col3 = st.columns(3)

col1.metric("Conexión", status["connection_status"])
col2.metric("Símbolo", status["symbol"])
col3.metric("Precio", status["last_price"])

col4, col5 = st.columns(2)

col4.metric("Señal", status["signal"])
col5.metric("Posición", status["position_state"])
st.subheader("Logs recientes")

logs = [
    "CONNECTED to broker",
    "Received new volume bar for AAPL",
    "Strategy returned BUY",
    "Order sent successfully"
]

for log in logs:
    st.write(f"- {log}")