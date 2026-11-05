"""Very small bounded retry helper for provider workers."""


class RateLimitError(Exception):
    """The provider returned a retryable HTTP 429 response."""


def run_with_bounded_retry(
    operation,
    maximum_attempts=3,
    wait_seconds=(0, 1, 2),
    sleep_function=lambda seconds: None,
):
    """Retry only timeouts and rate limits, and never retry forever."""
    if maximum_attempts < 1:
        raise ValueError("maximum_attempts must be at least 1")
    if maximum_attempts > len(wait_seconds):
        raise ValueError("wait_seconds must contain one value for every attempt")

    for attempt_number in range(maximum_attempts):
        if attempt_number > 0:
            sleep_function(wait_seconds[attempt_number])
        try:
            return operation()
        except (TimeoutError, RateLimitError):
            is_last_attempt = attempt_number == maximum_attempts - 1
            if is_last_attempt:
                raise

    raise RuntimeError("Retry loop ended unexpectedly")
