from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass
class CircuitBreaker:
    """
    Minimal circuit breaker.

    - CLOSED: calls are allowed
    - OPEN: calls are blocked until `open_until` expires
    """

    fail_threshold: int = 3
    reset_after_s: float = 120.0
    fail_count: int = 0
    open_until: float = 0.0

    def allow(self) -> bool:
        return time.time() >= self.open_until

    def record_success(self) -> None:
        self.fail_count = 0
        self.open_until = 0.0

    def record_failure(self) -> None:
        self.fail_count += 1
        if self.fail_count >= self.fail_threshold:
            self.open_until = time.time() + self.reset_after_s


async def run_with_timeout(coro: Awaitable[T], timeout_s: float) -> T:
    return await asyncio.wait_for(coro, timeout=timeout_s)


async def run_sync_with_timeout(fn: Callable[[], T], timeout_s: float) -> T:
    """
    Runs a blocking callable in a thread and enforces an asyncio timeout.
    """

    return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout_s)

