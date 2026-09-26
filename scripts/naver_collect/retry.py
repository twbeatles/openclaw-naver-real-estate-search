"""Retry helpers ported from scrapper error_handler + retry_handler (stdlib-only)."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError


class RetryCancelledError(Exception):
    """Caller가 취소한 재시도 흐름."""


class NetworkErrorHandler:
    RECOVERABLE_ERROR_TYPES = (
        ConnectionError,
        TimeoutError,
        ConnectionResetError,
        URLError,
        HTTPError,
        SocketTimeout,
    )
    RECOVERABLE_PATTERNS = (
        "connection",
        "timeout",
        "network",
        "socket",
        "temporary",
        "unavailable",
        "429",
        "too many requests",
        "rate limit",
    )

    @classmethod
    def is_recoverable(cls, error: Exception) -> bool:
        if isinstance(error, cls.RECOVERABLE_ERROR_TYPES):
            return True
        text = str(error or "").lower()
        return any(pattern in text for pattern in cls.RECOVERABLE_PATTERNS)

    @classmethod
    def get_wait_time(cls, error: Exception, attempt: int, base_delay: float = 2.0) -> float:
        del error
        unit = max(0.1, float(base_delay or 0))
        delay = min(unit * (2**attempt), 60.0)
        return delay + random.uniform(0, delay * 0.3)


class RetryHandler:
    """지수 백오프 + 취소 지원 재시도."""

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max(0, int(max_retries))
        self.base_delay = max(0.1, float(base_delay))

    def execute_with_retry(
        self,
        func: Callable[..., object],
        *args: object,
        cancel_checker: Callable[[], bool] | None = None,
        sleep_chunk_seconds: float = 0.2,
        **kwargs: object,
    ) -> object:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if _is_cancelled(cancel_checker):
                raise RetryCancelledError("retry cancelled before attempt")
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if _is_cancelled(cancel_checker):
                    raise RetryCancelledError("retry cancelled after exception") from exc
                if not NetworkErrorHandler.is_recoverable(exc):
                    raise
                if attempt >= self.max_retries:
                    break
                wait_time = NetworkErrorHandler.get_wait_time(exc, attempt, base_delay=self.base_delay)
                if self.is_rate_limited(exc):
                    wait_time = max(wait_time, 30.0)
                self._sleep_with_cancel(wait_time, cancel_checker, chunk_seconds=sleep_chunk_seconds)
        if last_error is not None:
            raise last_error
        raise RuntimeError("unknown retry error")

    def is_rate_limited(self, error: Exception) -> bool:
        text = str(error or "").lower()
        return any(token in text for token in ("429", "too many requests", "rate limit", "접속이 차단", "일시적으로 사용", "잠시 후"))

    def _sleep_with_cancel(
        self,
        wait_time: float,
        cancel_checker: Callable[[], bool] | None,
        chunk_seconds: float = 0.2,
    ) -> None:
        remaining = max(0.0, float(wait_time or 0.0))
        chunk = min(0.5, max(0.05, float(chunk_seconds or 0.2)))
        while remaining > 0:
            if _is_cancelled(cancel_checker):
                raise RetryCancelledError("retry cancelled while waiting")
            step = min(remaining, chunk)
            time.sleep(step)
            remaining -= step


def _is_cancelled(cancel_checker: Callable[[], bool] | None) -> bool:
    if not callable(cancel_checker):
        return False
    try:
        return bool(cancel_checker())
    except Exception:  # noqa: BLE001 - a broken checker must not block retry
        return False
