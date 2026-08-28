# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/applogger.py

import inspect
import json
import logging
import sys
import traceback
from typing import Any

from finance.common.configuration import LogConfig

RESERVED_LOG_KEYS = (
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
)

# ---------------
# Helper classes
# ---------------


class AppHandler(logging.StreamHandler):
    pass


class FallbackHandler(logging.StreamHandler):
    pass


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
        }
        message = record.getMessage()
        if message != "None":
            payload["message"] = message
        # Merge extra fields (record.__dict__ contains them)
        for key, value in record.__dict__.items():
            if key not in RESERVED_LOG_KEYS:
                payload[key] = value

        return json.dumps(payload)


class LogConfigurator:
    """Configures the logging infrastructure. Provides a minimal bootstrap logger for when the configuration hasn't
    been loaded yet, and replaces that by the final logger once loaded."""

    LOG_LEVELS = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }

    DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

    def __init__(self):
        self.root = logging.getLogger()

    def bootstrap(self) -> None:
        # If loader or orchestrator logs early, logging must not fail (optional).
        if not self.root.handlers:
            handler = FallbackHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.root.addHandler(handler)

        # Safe default level before config is loaded
        self.root.setLevel(logging.INFO)

    def setup(self, config: LogConfig) -> None:
        root = logging.getLogger()
        handler = AppHandler()
        formatter = JsonFormatter(datefmt=config.date_format)
        handler.setFormatter(formatter)

        root.addHandler(handler)

        # remove fallback handler
        for h in list(root.handlers):
            if isinstance(h, FallbackHandler):
                root.removeHandler(h)

        # Set level
        level_name = config.level
        root.setLevel(self.LOG_LEVELS.get(level_name, logging.INFO))


def _is_json_active() -> bool:
    root = logging.getLogger()
    return any(isinstance(h, AppHandler) for h in root.handlers)


# -----------
# Main class
# -----------


class AppLogger:
    def __init__(self, module_name: str | None = None):
        postfix = f".{module_name}" if module_name else ""
        self.name = f"finance{postfix}"

    @property
    def logger(self):
        return logging.getLogger(self.name)

    def log(self, level: str, msg: str | None = None, **context: Any) -> None:
        py_level = LogConfigurator.LOG_LEVELS[level]

        # Determine correct stacklevel (skip wrapper frames)
        frame = inspect.currentframe()
        stacklevel = 1

        while frame:  # pragma: no cover - currentframe() never returns None
            code = frame.f_code
            if code.co_name not in ("log", "error", "warning", "info", "debug"):
                break
            stacklevel += 1
            frame = frame.f_back

        # Clean context (remove None values)
        context.pop("ok", None)
        clean_context = {k: v for k, v in context.items() if v is not None}

        if not _is_json_active():
            # Fallback: safe text logging
            line = f"{level.upper()} | {msg or ''}"
            for k, v in context.items():
                line += f" | {k}={v}"
            self.logger.log(py_level, line)
            return

        # Emit JSON log (formatter handles serialization)
        self.logger.log(py_level, msg, extra=clean_context, stacklevel=stacklevel)

    def debug(self, msg=None, **context: Any):
        self.log("debug", msg, **context)

    def error(self, msg=None, **context: Any):
        self.log("error", msg, **context)

    def exception(self, msg=None, **context: Any):
        # Add structured fields
        exc_type, exc_value, exc_tb = sys.exc_info()
        assert exc_type is not None
        context["exception.message"] = str(exc_value)
        context["exception.type"] = exc_type.__name__
        context["exception.trace"] = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        self.log("error", msg, **context)

    def info(self, msg=None, **context: Any):
        self.log("info", msg, **context)

    def warning(self, msg=None, **context: Any):
        self.log("warning", msg, **context)
