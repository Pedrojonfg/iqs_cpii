from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from ib_insync import IB

from iqs.data.broker import BrokerData
from iqs.data.instruments import Instrument
from iqs.data.market_data_feed import FeedConfig, MarketDataFeed
from iqs.execution.execution import ExecutionHandler
from iqs.services.fundamental import FundamentalAnalyzer
from iqs.app.manager import Manager
from iqs.strategy.technical import EventDrivenTechnicalAnalyzer, TechnicalAnalyzer


def _touch_heartbeat() -> None:
    path = os.getenv("IQS_HEARTBEAT_PATH", ".iqs_heartbeat").strip()
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        return


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get_required_int_env(name: str) -> int:
    raw = _get_required_env(name)
    try:
        return int(raw)
    except ValueError as e:
        raise RuntimeError(f"Environment variable {name} must be an integer, got: {raw!r}") from e


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def _write_ui_state(*, connection_status: str, last_error: str | None = None) -> None:
    state_path = Path("ui/ui_state.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "connection_status": connection_status,
        "symbol": "-",
        "last_price": None,
        "signal": "DON'T BUY",
        "position_state": "CLOSED",
        "last_event_time": datetime.now(timezone.utc).isoformat(),
        "last_error": last_error,
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def main() -> None:
    _setup_logging()
    logger = logging.getLogger("iqs")
    load_dotenv()

    ib_host = _get_required_env("IB_HOST")
    ib_port = _get_required_int_env("IB_PORT")
    ib_client_id = _get_required_int_env("IB_CLIENT_ID")

    connection: IB = IB()
    connected = False
    try:
        await connection.connectAsync(ib_host, ib_port, clientId=ib_client_id)
        connected = connection.isConnected()
        if connected:
            logger.info("Connected to IB")
            _write_ui_state(connection_status="CONNECTED", last_error=None)
        else:
            logger.warning("connectAsync returned without an active IB session")
    except Exception as e:
        logger.warning("No IB connection, running in degraded mode: %s", e)

    if not connected:
        logger.error("Interactive Brokers unavailable; running in degraded UI-only mode")
        degraded_sleep_secs = max(1, int(os.getenv("IQS_DEGRADED_SLEEP_SECS", "5")))
        while True:
            _touch_heartbeat()
            _write_ui_state(
                connection_status="DEGRADED_NO_IB",
                last_error="Interactive Brokers unavailable. Running without broker/feed.",
            )
            await asyncio.sleep(degraded_sleep_secs)

    try:
        _touch_heartbeat()
        execution_handler = ExecutionHandler(connection)
        fundamental_analyzer = FundamentalAnalyzer()
        broker = BrokerData(connection)

        event_driven = os.getenv("IQS_EVENT_DRIVEN", "0").strip() == "1"
        if event_driven:
            technical_analyzer = EventDrivenTechnicalAnalyzer()
        else:
            technical_analyzer = TechnicalAnalyzer(broker)

        tickers: list[Instrument] = [
            Instrument(symbol="AIR", exchange="CHIX", currency="EUR"),
            Instrument(symbol="HO", exchange="CHIX", currency="EUR"),
            Instrument(symbol="SAF", exchange="CHIX", currency="EUR"),
            Instrument(symbol="AM", exchange="CHIX", currency="EUR"),
            Instrument(symbol="RHM", exchange="CHIX", currency="EUR"),
            Instrument(symbol="HAG", exchange="CHIX", currency="EUR"),
            Instrument(symbol="MTX", exchange="CHIX", currency="EUR"),
            Instrument(symbol="RENK", exchange="CHIX", currency="EUR"),
            Instrument(symbol="BA.", exchange="CHIX", currency="GBP"),
            Instrument(symbol="RR.", exchange="CHIX", currency="GBP"),
            Instrument(symbol="QQQ.", exchange="CHIX", currency="GBP"),
            Instrument(symbol="CHG", exchange="CHIX", currency="GBP"),
            Instrument(symbol="BAB", exchange="CHIX", currency="GBP"),
            Instrument(symbol="LDO", exchange="CHIX", currency="EUR"),
            Instrument(symbol="SAAB-B", exchange="CHIX", currency="SEK"),
            Instrument(symbol="IDR", exchange="CHIX", currency="EUR"),
            Instrument(symbol="KOG", exchange="CHIX", currency="NOK"),
        ]

        manager = Manager(
            broker=broker,
            tickers=tickers,
            fundamental_analyzer=fundamental_analyzer,
            technical_analyzer=technical_analyzer,
            execution_handler=execution_handler,
        )

        if not event_driven:
            while True:
                try:
                    await manager.manage_exits()
                except Exception:
                    logging.getLogger("iqs").exception("manage_exits failed; continuing")
                try:
                    await manager.manage_entries()
                except Exception:
                    logging.getLogger("iqs").exception("manage_entries failed; continuing")
                _touch_heartbeat()
                secs_until_next_min = 60 - (int(time.time()) % 60)
                await asyncio.sleep(secs_until_next_min)

        queue: asyncio.Queue = asyncio.Queue(maxsize=int(os.getenv("IQS_BAR_QUEUE_MAX", "1000")))
        feed_cfg = FeedConfig(
            default_bucket_volume=float(os.getenv("IQS_DEFAULT_BUCKET_VOLUME", "10000")),
            calibration_path=os.getenv("IQS_CALIBRATION_PATH", "data/calibration/calibration_latest.json"),
        )
        loop = asyncio.get_running_loop()
        feed = MarketDataFeed(broker=broker, instruments=tickers, out_queue=queue, loop=loop, config=feed_cfg)
        feed.start()

        logger = logging.getLogger("iqs")
        logger.info("Event-driven mode started: waiting for volume bars")

        while True:
            bar = await queue.get()
            try:
                await manager.on_volume_bar(bar)
            except Exception:
                logger.exception("manager.on_volume_bar failed for symbol=%s", getattr(bar, "symbol", "?"))
            _touch_heartbeat()
    finally:
        connection.disconnect()


def cli() -> None:
    asyncio.run(main())

