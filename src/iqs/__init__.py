from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "BrokerData",
    "DataCalibrator",
    "ExecutionHandler",
    "FundamentalAnalyzer",
    "LLMCheck",
    "Manager",
    "NewsFetcher",
    "TechnicalAnalyzer",
]

def __getattr__(name: str):
    """
    Lazy attribute loading for optional / heavyweight dependencies.

    This keeps `import iqs` lightweight and avoids importing modules that may
    require optional packages until actually needed.
    """
    if name == "BrokerData":
        from iqs.broker import BrokerData as v

        return v
    if name == "DataCalibrator":
        from iqs.calibrator import DataCalibrator as v

        return v
    if name == "ExecutionHandler":
        from iqs.execution import ExecutionHandler as v

        return v
    if name == "FundamentalAnalyzer":
        from iqs.fundamental import FundamentalAnalyzer as v

        return v
    if name == "LLMCheck":
        from iqs.nlp_veto import LLMCheck as v

        return v
    if name == "Manager":
        from iqs.manager import Manager as v

        return v
    if name == "NewsFetcher":
        from iqs.news import NewsFetcher as v

        return v
    if name == "TechnicalAnalyzer":
        from iqs.technical import TechnicalAnalyzer as v

        return v
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

if TYPE_CHECKING:
    from iqs.broker import BrokerData
    from iqs.calibrator import DataCalibrator
    from iqs.execution import ExecutionHandler
    from iqs.fundamental import FundamentalAnalyzer
    from iqs.manager import Manager
    from iqs.news import NewsFetcher
    from iqs.nlp_veto import LLMCheck
    from iqs.technical import TechnicalAnalyzer
