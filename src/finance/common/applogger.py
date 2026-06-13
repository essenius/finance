# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/applogger.py

import inspect
import logging

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


class AppLogger:
    @property
    def logger(self):
        # Each class gets its own logger name
        return logging.getLogger(self.__class__.__name__)

    def log(self, level: str, msg: str = None, **context) -> dict:

        py_level = LOG_LEVELS[level]

        if not self.logger.isEnabledFor(py_level):
            return {}

        # Find the first frame *outside* this class
        frame = inspect.currentframe()
        stacklevel = 1

        while frame:  # pragma: no cover - currentframe() never returns None
            code = frame.f_code
            if code.co_name not in ("log", "error", "warning", "info", "debug"):
                break
            stacklevel += 1
            frame = frame.f_back

        # Remove ok if present
        context.pop("ok", None)
        # remove entries that are None

        # flatten nested dicts one level deep
        flat = {}
        multi = []
        for key, value in context.items():
            if value is None:
                continue
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    flat[f"{key}.{subkey}"] = subval
            # this assumes there is no more than one of those
            elif isinstance(value, list):
                for entry in value:
                    multi.append(f"{key}={entry}")
            else:
                flat[key] = value

        # build final message
        parts = [level.upper()]
        if msg:
            parts.append(msg)
        parts += [f"{k}={v}" for k, v in flat.items()]

        line = " | ".join(parts)

        log_lines = self._get_lines(line, multi)

        for log_line in log_lines:
            self.logger.log(py_level, log_line, stacklevel=stacklevel)

        return {"level": level, "logline": line, **context}

    def _get_lines(self, line_part, multi):
        lines = []
        if multi:
            for entry in multi:
                line = f"{line_part} | {entry}"
                lines.append(line)
        else:
            lines.append(line_part)
        return lines

    def error(self, msg=None, **context):
        return self.log("error", msg, **context)

    def warning(self, msg=None, **context):
        return self.log("warning", msg, **context)

    def info(self, msg=None, **context):
        return self.log("info", msg, **context)

    def debug(self, msg=None, **context):
        return self.log("debug", msg, **context)
