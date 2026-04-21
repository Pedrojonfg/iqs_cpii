from __future__ import annotations

import asyncio
import os
import time

from dotenv import load_dotenv
from ib_insync import IB

from iqs.broker import BrokerData
from iqs.execution import ExecutionHandler
from iqs.fundamental import FundamentalAnalyzer
from iqs.manager import Manager
from iqs.technical import TechnicalAnalyzer

async def main() -> None:
    load_dotenv()

    ib_host = os.getenv("IB_HOST")
    ib_port = int(os.getenv("IB_PORT"))
    ib_client_id = int(os.getenv("IB_CLIENT_ID"))

    connection: IB = IB()
    await connection.connectAsync(ib_host, ib_port, clientId=ib_client_id)

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
