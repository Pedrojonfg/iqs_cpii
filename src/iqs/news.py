import yfinance as yf

class NewsFetcher:
    def __init__(self):
        self.max_chars_headline = 100
        self.max_total_headlines=15
    
    def fetch_headlines(self, ticker):
        raw_news=yf.Ticker(ticker).news
        clean_headlines=[]
        for article in raw_news[:self.max_total_headlines]:
            content= article.get("content", {})
            headline = content.get("title", "")
            if headline:
                clean_headlines.append(headline)
        return clean_headlines
    
    def format_and_sanitize(self, clean_headlines):
        healthy_headlines = []
        for headline in clean_headlines:
            headline = headline[:self.max_chars_headline]
            headline= headline.replace("<", " ").replace(">", " ")
            headline = "<new>"+ headline +"</new>"
            healthy_headlines.append(headline)
        headline_string= "<news>"+ ("\n".join(healthy_headlines))+ "</news>"
        return headline_string
    
    def newsfetcher(self, ticker):
        news=self.format_and_sanitize(self.fetch_headlines(ticker))
        return news