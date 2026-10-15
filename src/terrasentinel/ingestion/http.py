"""HTTP fetching with bounded retries, rate limiting, and secret redaction."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


def redact(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


class RateLimiter:
    def __init__(self, min_interval_s: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval_s = min_interval_s
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None:
            remaining = self.min_interval_s - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


def fetch_with_retry(
    url: str,
    *,
    session: requests.Session | None = None,
    max_retries: int = 3,
    backoff_s: float = 2.0,
    timeout_s: float = 60.0,
    rate_limiter: RateLimiter | None = None,
    secrets: Iterable[str] = (),
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    session = session or requests.Session()
    secrets = tuple(secrets)
    last_error = ""
    for attempt in range(max_retries + 1):
        if rate_limiter:
            rate_limiter.wait()
        try:
            resp = session.get(url, timeout=timeout_s)
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code == 200:
                return resp.content
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if resp.status_code not in RETRYABLE_STATUS:
                break
        if attempt < max_retries:
            sleep(backoff_s * (2**attempt))
    raise FetchError(redact(f"Request failed for {url}: {last_error}", secrets))
