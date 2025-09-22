"""Retry helpers shared across services."""

from __future__ import annotations

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class TransientError(Exception):
    """Error used to indicate that an operation may succeed when retried."""


retry3 = retry(
    retry=retry_if_exception_type(TransientError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
)
