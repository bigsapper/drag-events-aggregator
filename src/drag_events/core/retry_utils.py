"""Shared retry logic with aggregated telemetry."""

from copy import deepcopy
import time


def _empty_retry_stats() -> dict:
    return {
        "operations": 0,
        "attempts": 0,
        "retries": 0,
        "successful_retries": 0,
        "failed_operations": 0,
        "slept_seconds": 0.0,
    }


_RETRY_TELEMETRY = {
    "http": _empty_retry_stats(),
    "claude": _empty_retry_stats(),
}


def reset_retry_telemetry() -> None:
    global _RETRY_TELEMETRY
    _RETRY_TELEMETRY = {
        "http": _empty_retry_stats(),
        "claude": _empty_retry_stats(),
    }


def get_retry_telemetry() -> dict:
    return deepcopy(_RETRY_TELEMETRY)


def _category_stats(category: str) -> dict:
    if category not in _RETRY_TELEMETRY:
        _RETRY_TELEMETRY[category] = _empty_retry_stats()
    return _RETRY_TELEMETRY[category]


def _record_retry_result(category: str, *, attempts: int, slept_seconds: float, success: bool) -> None:
    stats = _category_stats(category)
    stats["operations"] += 1
    stats["attempts"] += attempts
    stats["retries"] += max(0, attempts - 1)
    stats["slept_seconds"] = round(stats["slept_seconds"] + slept_seconds, 2)
    if success and attempts > 1:
        stats["successful_retries"] += 1
    if not success:
        stats["failed_operations"] += 1


def execute_with_retries(
    operation,
    *,
    category: str,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    sleep=time.sleep,
    should_retry=None,
):
    attempts = 0
    slept_seconds = 0.0

    while True:
        attempts += 1
        try:
            result = operation()
            _record_retry_result(category, attempts=attempts, slept_seconds=slept_seconds, success=True)
            return result
        except Exception as exc:
            retryable = attempts < max_attempts
            if should_retry is not None:
                retryable = retryable and should_retry(exc)

            if not retryable:
                _record_retry_result(category, attempts=attempts, slept_seconds=slept_seconds, success=False)
                raise

            delay = round(base_delay_seconds * (2 ** (attempts - 1)), 2)
            slept_seconds += delay
            sleep(delay)
