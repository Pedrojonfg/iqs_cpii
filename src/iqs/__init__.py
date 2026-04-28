from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "BrokerData",
    "Instrument",
    "MarketDataFeed",
    "FeedConfig",
    "DataCalibrator",
    "ExecutionHandler",
    "FundamentalAnalyzer",
    "LLMCheck",
    "HotPathEngine",
    "HotPathParams",
    "Manager",
    "NewsFetcher",
    "TechnicalAnalyzer",
    "EventDrivenTechnicalAnalyzer",
    "VolumeBar",
    "HotPathResult",
]

def __getattr__(name: str):
    """
    Lazy attribute loading for optional / heavyweight dependencies.

    This keeps `import iqs` lightweight and avoids importing modules that may
    require optional packages until actually needed.
    """
    if name == "BrokerData":
        from iqs.data.broker import BrokerData as v

        return v
    if name == "Instrument":
        from iqs.data.instruments import Instrument as v

        return v
    if name == "MarketDataFeed":
        from iqs.data.market_data_feed import MarketDataFeed as v

        return v
    if name == "FeedConfig":
        from iqs.data.market_data_feed import FeedConfig as v

        return v
    if name == "DataCalibrator":
        from iqs.coldpath.calibrator import DataCalibrator as v

        return v
    if name == "ExecutionHandler":
        from iqs.execution.execution import ExecutionHandler as v

        return v
    if name == "FundamentalAnalyzer":
        from iqs.services.fundamental import FundamentalAnalyzer as v

        return v
    if name == "LLMCheck":
        from iqs.services.nlp_veto import LLMCheck as v

        return v
    if name == "HotPathEngine":
        from iqs.strategy.hotpath import HotPathEngine as v

        return v
    if name == "HotPathParams":
        from iqs.strategy.hotpath import HotPathParams as v

        return v
    if name == "Manager":
        from iqs.app.manager import Manager as v

        return v
    if name == "NewsFetcher":
        from iqs.services.news import NewsFetcher as v

        return v
    if name == "TechnicalAnalyzer":
        from iqs.strategy.technical import TechnicalAnalyzer as v

        return v
    if name == "EventDrivenTechnicalAnalyzer":
        from iqs.strategy.technical import EventDrivenTechnicalAnalyzer as v

        return v
    if name == "VolumeBar":
        from iqs.strategy.events import VolumeBar as v

        return v
    if name == "HotPathResult":
        from iqs.strategy.events import HotPathResult as v

        return v
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

if TYPE_CHECKING:
    from iqs.data.broker import BrokerData
    from iqs.data.instruments import Instrument
    from iqs.data.market_data_feed import FeedConfig, MarketDataFeed
    from iqs.coldpath.calibrator import DataCalibrator
    from iqs.execution.execution import ExecutionHandler
    from iqs.services.fundamental import FundamentalAnalyzer
    from iqs.strategy.hotpath import HotPathEngine, HotPathParams
    from iqs.app.manager import Manager
    from iqs.services.news import NewsFetcher
    from iqs.services.nlp_veto import LLMCheck
    from iqs.strategy.events import HotPathResult, VolumeBar
    from iqs.strategy.technical import TechnicalAnalyzer
