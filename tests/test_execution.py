from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iqs.data.instruments import Instrument
from iqs.execution.execution import ExecutionHandler


class FakeIB:
    def __init__(self) -> None:
        self.qualifyContracts = MagicMock()
        self.placeOrder = MagicMock()
        self.bracketOrder = MagicMock(return_value=[MagicMock(), MagicMock(), MagicMock()])


@pytest.fixture
def handler() -> ExecutionHandler:
    return ExecutionHandler(FakeIB())


def test_send_order_rejects_non_positive_quantity(handler: ExecutionHandler) -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        handler.send_order("AAA", "BUY", 0, 100.0, 10_000.0)


def test_send_order_rejects_non_positive_entry_price(handler: ExecutionHandler) -> None:
    with pytest.raises(ValueError, match="entry_price must be positive"):
        handler.send_order("AAA", "BUY", 1.0, 0.0, 10_000.0)


def test_send_order_rejects_invalid_action(handler: ExecutionHandler) -> None:
    with pytest.raises(ValueError, match="action must be BUY or SELL"):
        handler.send_order("AAA", "HOLD", 1.0, 100.0, 10_000.0)


def test_send_order_rejects_insufficient_funds_for_buy(handler: ExecutionHandler) -> None:
    with pytest.raises(ValueError, match="insufficient funds"):
        handler.send_order("AAA", "BUY", 10.0, 100.0, 500.0)


def test_send_order_rejects_partial_bracket(handler: ExecutionHandler) -> None:
    with pytest.raises(ValueError, match="take_profit and stop_loss must be both set or both zero"):
        handler.send_order("AAA", "BUY", 1.0, 100.0, 10_000.0, take_profit=110.0, stop_loss=0.0)


def test_send_order_valid_without_bracket_places_single_limit_order(handler: ExecutionHandler) -> None:
    instrument = Instrument(symbol="AAA", exchange="CHIX", currency="EUR")

    handler.send_order(instrument, "BUY", 2.0, 50.0, 10_000.0)

    fake_ib = handler.ib
    fake_ib.qualifyContracts.assert_called_once()
    fake_ib.placeOrder.assert_called_once()
    fake_ib.bracketOrder.assert_not_called()


def test_send_order_valid_with_bracket_places_all_orders(handler: ExecutionHandler) -> None:
    bracket_orders = [MagicMock(), MagicMock(), MagicMock()]
    handler.ib.bracketOrder.return_value = bracket_orders

    handler.send_order("AAA", "BUY", 2.0, 50.0, 10_000.0, take_profit=55.0, stop_loss=45.0)

    fake_ib = handler.ib
    fake_ib.qualifyContracts.assert_called_once()
    fake_ib.bracketOrder.assert_called_once_with("BUY", 2.0, 50.0, 55.0, 45.0)
    assert fake_ib.placeOrder.call_count == len(bracket_orders)
