import ib_insync as ib
from fundamental import FundamentalAnalyzer
from execution import ExecutionHandler
from technical import TechnicalAnalyzer
from manager import Manager
from broker import BrokerData



if __name__== "__main__":
    connection= IB()
    connection.connect("172.31.48.1", 7947, ClientID=1)

    execution_handler = ExecutionHandler(connection) 
    technical_analyzer = TechnicalAnalyzer()
    fundamental_analyzer = FundamentalAnalyzer()
    broker= BrokerData()
    tickers =[]
    Manager1= Manager(broker=broker, 
                      tickers=tickers,
                      fundamental_analyzer=fundamental_analyzer,
                      technical_analyzer=technical_analyzer,
                      execution_handler=execution_handler
                      )
    while True:
        Manager1.manage_exits()
        Manager1.manage_entries()

        secs_until_next_min = 60 - (int(time.time()) % 60)
        connection.sleep(secs_until_next_min)
