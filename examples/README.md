# Ejemplo de ejecución

Estos ficheros son la salida de una demo con datos **sintéticos** (símbolo `AAA`,
generado por `ColdPathRunner` en modo `synthetic`), no de una sesión con datos de
mercado reales ni con conexión a IB en real.

- `veto_audit.log` — log del veto layer (LLM + fundamental) sobre la demo.
- `ui_logs.txt` — log completo del pipeline: calibración de volume bars vía test de
  Jarque–Bera, arranque del hot path, decisiones de la estrategia.
- `ui_state.json` — snapshot final del estado que consume el dashboard de Streamlit.
- `.iqs_heartbeat` — heartbeat del watchdog durante esa misma ejecución.

Se incluyen como evidencia de que el pipeline corre end-to-end
(ticks → volume bars → estrategia → veto → estado), no como resultados de trading.
