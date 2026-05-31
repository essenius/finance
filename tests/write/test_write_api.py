# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/write/test_write_api.py

import logging
import pytest

from finance.common.log_mixin import LOG_LEVELS, LogMixin
from finance.write import write_metric


@pytest.mark.parametrize(
    "status,expected_level,expected_msg,stream",
    [
        ("written", "DEBUG", "written", "out"),
        ("skipped", "INFO", "write skipped", "out"),
        ("error", "ERROR", "write failed", "err"),
    ],
)
def test_write_api_parametrized(monkeypatch, caplog, status, expected_level, expected_msg, stream):
    import finance.write as write_mod

    LogMixin.min_level = LOG_LEVELS["debug"]

    calls = []

    class FakeWriter(LogMixin):
        def __init__(self, state):
            calls.append(("init", state))

        def write(self, bucket, measurement, fields, timestamp):
            return {
                "status": status,
                "ok": status == "written",
                "measurement": measurement,
                "fields": fields,
                "timestamp": timestamp,
            }

    # Patch the symbol used by the façade
    monkeypatch.setattr(write_mod, "MetricWriter", FakeWriter)

    state = {}
    with caplog.at_level(logging.DEBUG):
        result = write_metric("b", "m", {"x": 1}, 123, state)

    assert result["status"] == status

    # Validate log output
    text = caplog.text

    # Validate logline
    assert expected_level in text
    assert expected_msg in text
    assert "measurement=m" in text
    assert "fields.x=1" in text
    assert "timestamp=123" in text
