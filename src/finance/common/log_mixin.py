# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/common/log_mixin.py

import sys

LOG_LEVELS = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}


class LogMixin:
    min_level = LOG_LEVELS["info"]

    def log(self, level, msg=None, **context):

        if LOG_LEVELS[level] < self.min_level:
            return {"level": level, "skipped": True, **context}

        # Remove ok and status if present
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

        stream = sys.stderr if level == "error" else sys.stdout
        print(line, file=stream)
        return {"level": level, "logline": line, **context}

    def error(self, msg=None, **context):
        return self.log("error", msg, **context)

    def warning(self, msg=None, **context):
        return self.log("warning", msg, **context)

    def info(self, msg=None, **context):
        return self.log("info", msg, **context)

    def debug(self, msg=None, **context):
        return self.log("debug", msg, **context)
