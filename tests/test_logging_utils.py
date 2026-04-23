"""Tests for logging_utils.py."""

import logging

from drag_events.core import logging_utils


def _reset_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    return logger


def test_should_log_to_file_defaults_off(monkeypatch):
    monkeypatch.delenv("DRAG_EVENTS_LOG_TO_FILE", raising=False)
    assert logging_utils.should_log_to_file() is False


def test_should_log_to_file_accepts_truthy_values(monkeypatch):
    monkeypatch.setenv("DRAG_EVENTS_LOG_TO_FILE", "true")
    assert logging_utils.should_log_to_file() is True


def test_get_log_file_path_uses_override(monkeypatch, tmp_path):
    path = tmp_path / "custom.log"
    monkeypatch.setenv("DRAG_EVENTS_LOG_FILE", str(path))
    assert logging_utils.get_log_file_path() == path


def test_get_logger_writes_to_file_when_enabled(monkeypatch, tmp_path):
    log_path = tmp_path / "runtime.log"
    monkeypatch.setenv("DRAG_EVENTS_LOG_TO_FILE", "1")
    monkeypatch.setenv("DRAG_EVENTS_LOG_FILE", str(log_path))
    logger_name = "drag_events.tests.logging.file"
    logger = _reset_logger(logger_name)

    logger = logging_utils.get_logger(logger_name)
    logger.info("hello file logging")
    for handler in logger.handlers:
        handler.flush()

    assert log_path.exists()
    content = log_path.read_text()
    assert "hello file logging" in content
    assert "INFO" in content


def test_get_logger_does_not_duplicate_file_handler(monkeypatch, tmp_path):
    log_path = tmp_path / "runtime.log"
    monkeypatch.setenv("DRAG_EVENTS_LOG_TO_FILE", "1")
    monkeypatch.setenv("DRAG_EVENTS_LOG_FILE", str(log_path))
    logger_name = "drag_events.tests.logging.dedup"
    _reset_logger(logger_name)

    logger = logging_utils.get_logger(logger_name)
    logger = logging_utils.get_logger(logger_name)

    file_handlers = [handler for handler in logger.handlers if getattr(handler, "_drag_events_file_handler", False)]
    assert len(file_handlers) == 1


def test_get_file_handler_returns_none_when_file_logging_disabled(monkeypatch):
    monkeypatch.delenv("DRAG_EVENTS_LOG_TO_FILE", raising=False)
    assert logging_utils._get_file_handler() is None
