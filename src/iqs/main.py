from __future__ import annotations

import asyncio
import time

from ib_insync import IB

from iqs.broker import BrokerData
from iqs.execution import ExecutionHandler
from iqs.fundamental import FundamentalAnalyzer
from iqs.manager import Manager
from iqs.technical import TechnicalAnalyzer

async def main() -> None:
    connection: IB = IB()
    await connection.connectAsync("172.31.48.1", 7947, clientId=1)

    try:
        execution_handler: ExecutionHandler = ExecutionHandler(connection)
        technical_analyzer: TechnicalAnalyzer = TechnicalAnalyzer()
        fundamental_analyzer: FundamentalAnalyzer = FundamentalAnalyzer()
        broker: BrokerData = BrokerData(connection)
        tickers: list[str] = []
        manager: Manager = Manager(
            broker=broker,
            tickers=tickers,
            fundamental_analyzer=fundamental_analyzer,
            technical_analyzer=technical_analyzer,
            execution_handler=execution_handler,
        )
        while True:
            manager.manage_exits()
            manager.manage_entries()

            secs_until_next_min = 60 - (int(time.time()) % 60)
            await asyncio.sleep(secs_until_next_min)
    finally:
        connection.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
