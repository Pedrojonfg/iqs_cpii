from __future__ import annotations

import asyncio
import os
import time

from dotenv import load_dotenv
from ib_insync import IB
import logging

from iqs.broker import BrokerData
from iqs.market_data_feed import FeedConfig, MarketDataFeed
from iqs.execution import ExecutionHandler
from iqs.fundamental import FundamentalAnalyzer
from iqs.instruments import Instrument
from iqs.manager import Manager
from iqs.technical import EventDrivenTechnicalAnalyzer, TechnicalAnalyzer

def _touch_heartbeat() -> None:
    """
    Write a heartbeat file for an external watchdog.

    Set `IQS_HEARTBEAT_PATH` to control the file location.
    Set it to an empty string to disable.
    """

    path = os.getenv("IQS_HEARTBEAT_PATH", ".iqs_heartbeat").strip()
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        # Heartbeat failure should never stop trading logic.
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

async def main() -> None:
    _setup_logging()
    load_dotenv()

    ib_host = _get_required_env("IB_HOST")
    ib_port = _get_required_int_env("IB_PORT")
    ib_client_id = _get_required_int_env("IB_CLIENT_ID")

    connection: IB = IB()
    await connection.connectAsync(ib_host, ib_port, clientId=ib_client_id)

    try:
        _touch_heartbeat()
        execution_handler: ExecutionHandler = ExecutionHandler(connection)
        fundamental_analyzer: FundamentalAnalyzer = FundamentalAnalyzer()
        broker: BrokerData = BrokerData(connection)
        event_driven = os.getenv("IQS_EVENT_DRIVEN", "0").strip() == "1"
        if event_driven:
            technical_analyzer = EventDrivenTechnicalAnalyzer()
        else:
            technical_analyzer = TechnicalAnalyzer(broker)
        # Universe with IB contract metadata from the provided table.
        tickers: list[Instrument] = [
            Instrument(symbol="AIR", exchange="CHIX", currency="EUR"),  # Airbus
            Instrument(symbol="HO", exchange="CHIX", currency="EUR"),  # Thales
            Instrument(symbol="SAF", exchange="CHIX", currency="EUR"),  # Safran
            Instrument(symbol="AM", exchange="CHIX", currency="EUR"),  # Dassault Aviation
            Instrument(symbol="RHM", exchange="CHIX", currency="EUR"),  # Rheinmetall
            Instrument(symbol="HAG", exchange="CHIX", currency="EUR"),  # Hensoldt
            Instrument(symbol="MTX", exchange="CHIX", currency="EUR"),  # MTU Aero Engines
            Instrument(symbol="RENK", exchange="CHIX", currency="EUR"),  # Renk Group
            Instrument(symbol="BA.", exchange="CHIX", currency="GBP"),  # BAE Systems
            Instrument(symbol="RR.", exchange="CHIX", currency="GBP"),  # Rolls-Royce
            Instrument(symbol="QQQ.", exchange="CHIX", currency="GBP"),  # QinetiQ
            Instrument(symbol="CHG", exchange="CHIX", currency="GBP"),  # Chemring
            Instrument(symbol="BAB", exchange="CHIX", currency="GBP"),  # Babcock
            Instrument(symbol="LDO", exchange="CHIX", currency="EUR"),  # Leonardo
            Instrument(symbol="SAAB-B", exchange="CHIX", currency="SEK"),  # Saab AB
            Instrument(symbol="IDR", exchange="CHIX", currency="EUR"),  # Indra
            Instrument(symbol="KOG", exchange="CHIX", currency="NOK"),  # Kongsberg
        ]
        manager: Manager = Manager(
            broker=broker,
            tickers=tickers,
            fundamental_analyzer=fundamental_analyzer,
            technical_analyzer=technical_analyzer,
            execution_handler=execution_handler,
        )
        if not event_driven:
            while True:
                # Stage isolation: failures don't crash the process.
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

        # Event-driven mode: ticks -> volume bars -> manager.on_volume_bar(bar)
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


if __name__ == "__main__":
    asyncio.run(main())


def cli() -> None:
    asyncio.run(main())
