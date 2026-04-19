from news import NewsFetcher
from nlp_veto import LLMCheck

class FundamentalAnalyzer:
    def __init__(self):
        self.news= NewsFetcher()
        self.analysis=LLMCheck()
    
    def check_trade(self, ticker):
        safe_news= self.news.newsfetcher(ticker)
        decision=self.analysis.decide(ticker, safe_news)