from fundamental import FundamentalAnalyzer
from technical import TechnicalAnalyzer
from execution import ExecutionHandler     

class Manager:
    """
    tfdg
    """
    def __init__(self, broker, tickers, fundamental_analyzer, technical_analyzer, execution_handler):
            self.broker = broker
            self.tickers = tickers
            self.fundamental = fundamental_analyzer
            self.technical = technical_analyzer
            self.execution = execution_handler
    def manage_exits(self):
          open_positions = self.broker.get_active_positions()
          for ticker in open_positions:
            decision = self.technical.check_sell(ticker)
            if decision.get("signal", "DON'T SELL") == "SELL":
                self.execution.send_order(
                ticker, 
                action = "SELL", 
                quantity = decision[quantity], 
                entry_price = decision[entry_price], 
                disp_money=self.broker.get_disp_money()
                )
    def manage_entries(self):
        for ticker in self.tickers:
            decision = self.technical.check_trade(ticker)
            if decision.get("signal", "DON'T BUY") == "BUY":
                llmcheck = self.fundamental.check_trade(ticker)
                if llmcheck=="CLEAR":
                    self.execution.send_order(
                    ticker, 
                    action = "BUY", 
                    quantity = decision[quantity], 
                    entry_price = decision[entry_price], 
                    disp_money=self.broker.get_disp_money(), 
                    take_profit=decision[take_profit], 
                    stop_loss=decision[take_profit])
                     
                     
                    

