# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/log_mixin.py

import logging

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


class LogMixin:

    @property
    def logger(self):
        # Each class gets its own logger name
        return logging.getLogger(self.__class__.__name__)

    def log(self, level, msg=None, **context):

        py_level = LOG_LEVELS[level]

        # Remove ok if present
        context.pop("ok", None)

        # flatten nested dicts one level deep
        flat = {}
        for key, value in context.items():
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    flat[f"{key}.{subkey}"] = subval
            else:
                flat[key] = value

        # build final message
        parts = [level.upper()]
        if msg:
            parts.append(msg)
        parts += [f"{k}={v}" for k, v in flat.items()]
        line = " | ".join(parts)

        # Send to Python logging
        self.logger.log(py_level, line)
        return {"level": level, "logline": line, **context}

    def error(self, msg=None, **context):
        return self.log("error", msg, **context)

    def warning(self, msg=None, **context):
        return self.log("warning", msg, **context)

    def info(self, msg=None, **context):
        return self.log("info", msg, **context)

    def debug(self, msg=None, **context):
        return self.log("debug", msg, **context)
