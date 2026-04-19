from ib_insync import IB, Stock, LimitOrder
class ExecutionHandler:
    def __init__(self, ib_connection):
        self.ib = ib_connection

    def disconnect(self):
        self.ib.disconnect()
    
    def send_order(self, ticker, action, quantity, entry_price, disp_money, take_profit=0.0, stop_loss=0.0):
        #Checks
        if len(ticker)==0:
            raise ValueError("Invalid ticker")
        
        action =action.upper()
        if action not in ["BUY", "SELL"]:
            raise ValueError("The action is not BUY or SELL")
        
        cost=quantity*entry_price
        if cost<=0 or quantity<0:
            raise ValueError("Incorrect Quantity-Price")
        if action=="BUY" and cost>disp_money:
            raise ValueError("Incorrect Quantity-Price")
        

        contract= Stock(ticker, "SMART", "EUR")
        self.ib.qualifyContracts(contract)

        if take_profit==0.0 and stop_loss==0.0:
            order= LimitOrder(action, quantity, entry_price)
            self.ib.placeOrder(contract, order)

        else:
            order_list=self.ib.bracketOrder(action, quantity, entry_price, take_profit, stop_loss)
            for order in order_list:
              self.ib.placeOrder(contract, order)  
