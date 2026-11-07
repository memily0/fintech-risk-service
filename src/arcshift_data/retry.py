"""Small bounded retry helper for provider workers."""

import math
import time


class RateLimitError(Exception):
    """The provider returned a retryable HTTP 429 response."""

    def __init__(self, message="provider rate limit", retry_after_seconds=None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def run_with_bounded_retry(
    operation,
    maximum_attempts=3,
    wait_seconds=(1, 2),
    maximum_wait_seconds=60,
    sleep_function=time.sleep,
):
    """Retry timeouts and 429s with a finite number of real waits.

    ``wait_seconds`` describes waits *between* attempts, so it must contain
    ``maximum_attempts - 1`` values.  A provider Retry-After value may replace
    the configured wait, but is capped to keep one worker run bounded.
    """
    if maximum_attempts < 1:
        raise ValueError("maximum_attempts must be at least 1")
    if len(wait_seconds) != maximum_attempts - 1:
        raise ValueError("wait_seconds must contain one value between every attempt")
    if not isinstance(maximum_wait_seconds, (int, float)) or maximum_wait_seconds < 0:
        raise ValueError("maximum_wait_seconds must be non-negative")
    for wait in wait_seconds:
        if not isinstance(wait, (int, float)) or not math.isfinite(wait) or wait < 0:
            raise ValueError("wait_seconds must contain finite non-negative numbers")

    for attempt_number in range(maximum_attempts):
        try:
            return operation()
        except (TimeoutError, RateLimitError) as error:
            is_last_attempt = attempt_number == maximum_attempts - 1
            if is_last_attempt:
                raise

            wait = wait_seconds[attempt_number]
            if isinstance(error, RateLimitError) and error.retry_after_seconds is not None:
                retry_after = error.retry_after_seconds
                if not isinstance(retry_after, (int, float)) or not math.isfinite(retry_after) or retry_after < 0:
                    raise ValueError("retry_after_seconds must be a finite non-negative number") from error
                wait = min(retry_after, maximum_wait_seconds)
            sleep_function(wait)

    raise RuntimeError("Retry loop ended unexpectedly")
