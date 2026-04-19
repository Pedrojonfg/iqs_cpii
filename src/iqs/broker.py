import ib_insync as ib
from ib_insync import Stock
import datetime

class BrokerData:
    def __init__(self, ib_connection):
        self.ib = ib_connection

    def get_active_positions(self):
        positions = self.ib.positions()
        return [pos.contract.symbol for pos in positions if pos.position > 0]

    def get_disp_money(self):
        acc_values = self.ib.accountValues()
        for value in acc_values:
            if value.tag == "AvailableFunds" and value.currency == "EUR":
                return float(value.value)
        return 0.0

    def subscribe_to_data(self, symbol, callback_function):
        contract = Stock(symbol, "SMART", "EUR")
        self.ib.qualifyContracts(contract)
        
        ticker_stream = self.ib.reqTickByTickData(contract, 'AllLast')
        ticker_stream.updateEvent += callback_function

    def fetch_past_data(self, symbol, days_back=5):
        contract = Stock(symbol, "SMART", "EUR")
        self.ib.qualifyContracts(contract)
        
        target_start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
        end_time = datetime.datetime.now(datetime.timezone.utc)
        
        all_ticks = []
        
        while end_time > target_start_time:
            tick_chunk = self.ib.reqHistoricalTicks(
                contract,
                startDateTime="",
                endDateTime=end_time,
                numberOfTicks=1000, 
                whatToShow="TRADES",
                useRth=False,
                ignoreSize=False
            ) 
            if len(tick_chunk)==0:
                break
            all_ticks = tick_chunk + all_ticks          
            end_time = tick_chunk[0].time
        
        return all_ticks