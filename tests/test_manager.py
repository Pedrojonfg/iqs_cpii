from __future__ import annotations

import asyncio
import json
from dataclasses import fields
from typing import Any

from iqs.app.manager import Manager, SystemState
from iqs.data.instruments import Instrument
from iqs.strategy.events import VolumeBar


class FakeBroker:
    def get_active_positions(self) -> list[str]:
        return []

    def get_position_market_value(self, symbol: str) -> float:
        return 0.0

    def get_disp_money(self, currency: str = "EUR") -> float:
        return 10_000.0


class FakeTechnical:
    def __init__(self, decision: dict[str, Any]) -> None:
        self._decision = decision

    def check_sell(self, ticker: Instrument | str) -> dict[str, Any]:
        return {"signal": "DON'T SELL"}

    def check_trade(self, ticker: Instrument | str) -> dict[str, Any]:
        return {"signal": "DON'T BUY"}

    def on_volume_bar(self, bar: VolumeBar) -> dict[str, Any]:
        return dict(self._decision)


class FakeFundamental:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict

    def check_trade(self, ticker: str) -> str:
        return self.verdict


class FakeExecution:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def send_order(
        self,
        instrument: Instrument | str,
        action: str,
        quantity: float,
        entry_price: float,
        disp_money: float,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
    ) -> None:
        self.calls.append(
            (
                (instrument, action, quantity, entry_price, disp_money, take_profit, stop_loss),
                {},
            )
        )


def _make_bar() -> VolumeBar:
    return VolumeBar(
        symbol="AAA",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10_000.0,
        start_ts=1.0,
        end_ts=2.0,
    )


def _make_manager(
    *,
    fundamental_verdict: str = "CLEAR",
    technical_decision: dict[str, Any] | None = None,
    execution: FakeExecution | None = None,
) -> tuple[Manager, FakeExecution]:
    decision = technical_decision or {
        "signal": "BUY",
        "quantity": 5.0,
        "entry_price": 100.0,
        "take_profit": 106.0,
        "stop_loss": 97.0,
    }
    fake_execution = execution or FakeExecution()
    manager = Manager(
        broker=FakeBroker(),
        tickers=[Instrument(symbol="AAA", exchange="CHIX", currency="EUR")],
        fundamental_analyzer=FakeFundamental(fundamental_verdict),
        technical_analyzer=FakeTechnical(decision),
        execution_handler=fake_execution,
    )
    return manager, fake_execution


def test_to_ui_state_returns_system_state_fields() -> None:
    manager, _ = _make_manager()
    manager._ui_state.connection_status = "CONNECTED"
    manager._ui_state.symbol = "AAA"
    manager._ui_state.last_price = 100.5
    manager._ui_state.signal = "BUY"
    manager._ui_state.position_state = "OPEN"
    manager._ui_state.last_event_time = "2026-01-01T00:00:00+00:00"
    manager._ui_state.last_error = None

    state = manager.to_ui_state()

    assert set(state.keys()) == {field.name for field in fields(SystemState)}
    assert state["connection_status"] == "CONNECTED"
    assert state["symbol"] == "AAA"
    assert state["last_price"] == 100.5
    assert state["signal"] == "BUY"
    assert state["position_state"] == "OPEN"


def test_save_ui_state_writes_valid_json(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manager, _ = _make_manager()
    manager._ui_state.connection_status = "CONNECTED"
    manager._ui_state.symbol = "AAA"
    manager._ui_state.last_price = 100.5
    manager._ui_state.signal = "DON'T BUY"
    manager._ui_state.position_state = "CLOSED"

    manager._save_ui_state()

    payload = json.loads((tmp_path / "ui" / "ui_state.json").read_text(encoding="utf-8"))
    assert set(payload.keys()) == {field.name for field in fields(SystemState)}
    assert payload["connection_status"] == "CONNECTED"
    assert payload["symbol"] == "AAA"
    assert payload["last_price"] == 100.5
    assert payload["signal"] == "DON'T BUY"
    assert payload["position_state"] == "CLOSED"
    assert payload["last_event_time"] is not None


def test_on_volume_bar_with_clear_fundamental_executes_order() -> None:
    manager, execution = _make_manager(fundamental_verdict="CLEAR")

    asyncio.run(manager.on_volume_bar(_make_bar()))

    assert len(execution.calls) == 1
    args, _ = execution.calls[0]
    assert args[1] == "BUY"
    assert args[2] == 5.0
    assert args[3] == 100.0


def test_on_volume_bar_with_fundamental_veto_does_not_execute() -> None:
    manager, execution = _make_manager(fundamental_verdict="VETO")

    asyncio.run(manager.on_volume_bar(_make_bar()))

    assert execution.calls == []
