"""Tests for retry_utils.py."""

import pytest

from drag_events import retry_utils


def test_reset_retry_telemetry_restores_empty_state():
    retry_utils.reset_retry_telemetry()
    telemetry = retry_utils.get_retry_telemetry()
    assert telemetry["http"]["operations"] == 0
    assert telemetry["claude"]["retries"] == 0


def test_execute_with_retries_success_first_try_records_single_attempt():
    retry_utils.reset_retry_telemetry()

    result = retry_utils.execute_with_retries(lambda: "ok", category="http", sleep=lambda _: None)

    telemetry = retry_utils.get_retry_telemetry()
    assert result == "ok"
    assert telemetry["http"]["operations"] == 1
    assert telemetry["http"]["attempts"] == 1
    assert telemetry["http"]["retries"] == 0
    assert telemetry["http"]["successful_retries"] == 0


def test_execute_with_retries_success_after_retry_records_retry_and_sleep():
    retry_utils.reset_retry_telemetry()
    attempts = {"count": 0}
    sleeps = []

    def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary")
        return "ok"

    result = retry_utils.execute_with_retries(
        operation,
        category="claude",
        base_delay_seconds=0.5,
        sleep=sleeps.append,
    )

    telemetry = retry_utils.get_retry_telemetry()
    assert result == "ok"
    assert sleeps == [0.5]
    assert telemetry["claude"]["attempts"] == 2
    assert telemetry["claude"]["retries"] == 1
    assert telemetry["claude"]["successful_retries"] == 1
    assert telemetry["claude"]["slept_seconds"] == 0.5


def test_execute_with_retries_terminal_failure_records_failed_operation():
    retry_utils.reset_retry_telemetry()

    with pytest.raises(RuntimeError, match="boom"):
        retry_utils.execute_with_retries(
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            category="http",
            max_attempts=2,
            sleep=lambda _: None,
        )

    telemetry = retry_utils.get_retry_telemetry()
    assert telemetry["http"]["operations"] == 1
    assert telemetry["http"]["attempts"] == 2
    assert telemetry["http"]["retries"] == 1
    assert telemetry["http"]["failed_operations"] == 1


def test_execute_with_retries_respects_should_retry_predicate():
    retry_utils.reset_retry_telemetry()

    with pytest.raises(ValueError, match="no-retry"):
        retry_utils.execute_with_retries(
            lambda: (_ for _ in ()).throw(ValueError("no-retry")),
            category="claude",
            should_retry=lambda exc: not isinstance(exc, ValueError),
            sleep=lambda _: None,
        )

    telemetry = retry_utils.get_retry_telemetry()
    assert telemetry["claude"]["attempts"] == 1
    assert telemetry["claude"]["retries"] == 0
    assert telemetry["claude"]["failed_operations"] == 1


def test_execute_with_retries_initializes_custom_category():
    retry_utils.reset_retry_telemetry()

    retry_utils.execute_with_retries(lambda: "ok", category="custom", sleep=lambda _: None)

    telemetry = retry_utils.get_retry_telemetry()
    assert telemetry["custom"]["operations"] == 1
