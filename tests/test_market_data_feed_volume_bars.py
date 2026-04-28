import asyncio

from iqs.strategy.events import VolumeBar
from iqs.data.instruments import Instrument
from iqs.data.market_data_feed import FeedConfig, MarketDataFeed


class _FakeBroker:
    def __init__(self):
        self.callbacks = []

    def subscribe_to_data(self, instrument: Instrument | str, callback_function):
        self.callbacks.append(callback_function)


def test_feed_emits_volume_bar_when_bucket_fills():
    loop = asyncio.new_event_loop()
    try:
        q: asyncio.Queue[VolumeBar] = asyncio.Queue()
        broker = _FakeBroker()
        ins = [Instrument(symbol="AAA", exchange="SMART", currency="USD")]

        cfg = FeedConfig(default_bucket_volume=100.0, calibration_path="__missing__.json")
        feed = MarketDataFeed(broker=broker, instruments=ins, out_queue=q, loop=loop, config=cfg)
        feed.start()

        cb = broker.callbacks[0]

        # Two ticks that fill the bucket.
        cb(price=10.0, size=60.0)
        cb(price=11.0, size=50.0)

        # The bar is enqueued via call_soon_threadsafe; run loop briefly to flush.
        loop.run_until_complete(asyncio.sleep(0))

        bar = q.get_nowait()
        assert bar.symbol == "AAA"
        assert bar.open == 10.0
        assert bar.close == 11.0
        assert bar.high == 11.0
        assert bar.low == 10.0
        assert bar.volume >= 100.0
    finally:
        loop.close()

