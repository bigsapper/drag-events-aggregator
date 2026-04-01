"""Shared logging configuration for drag_events modules."""

import logging
import os
import sys
from pathlib import Path


class _StdoutProxy:
    def write(self, message: str) -> int:
        return sys.stdout.write(message)

    def flush(self) -> None:
        sys.stdout.flush()


_HANDLER = logging.StreamHandler(_StdoutProxy())
_HANDLER.setFormatter(logging.Formatter("%(message)s"))
_HANDLER._drag_events_handler = True

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOG_FILE = BASE_DIR / "runtime" / "tracing" / "drag_events.log"


def get_log_level() -> int:
    level_name = os.environ.get("DRAG_EVENTS_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def should_log_to_file() -> bool:
    return os.environ.get("DRAG_EVENTS_LOG_TO_FILE", "").lower() in {"1", "true", "yes", "on"}


def get_log_file_path() -> Path:
    override = os.environ.get("DRAG_EVENTS_LOG_FILE")
    return Path(override) if override else DEFAULT_LOG_FILE


def _get_file_handler() -> logging.Handler | None:
    if not should_log_to_file():
        return None

    path = get_log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler._drag_events_file_handler = True
    handler._drag_events_file_path = str(path)
    return handler


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(getattr(handler, "_drag_events_handler", False) for handler in logger.handlers):
        logger.addHandler(_HANDLER)

    file_path = str(get_log_file_path())
    has_file_handler = any(
        getattr(handler, "_drag_events_file_handler", False)
        and getattr(handler, "_drag_events_file_path", None) == file_path
        for handler in logger.handlers
    )
    if should_log_to_file() and not has_file_handler:
        file_handler = _get_file_handler()
        if file_handler is not None:
            logger.addHandler(file_handler)

    logger.setLevel(get_log_level())
    logger.propagate = False
    return logger
