# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/freshness.py


def is_recent(entry: dict | None, now: int, interval: int) -> bool:
    if entry is None:
        return False
    last_try = entry.get("last_try")
    if last_try is None:
        return False

    age_seconds = now - last_try
    return age_seconds < interval
