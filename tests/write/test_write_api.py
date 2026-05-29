# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/write/test_write_api.py

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
def test_write_api_parametrized(monkeypatch, capsys, status, expected_level, expected_msg, stream):
    import finance.write as write_mod

    LogMixin.min_level = LOG_LEVELS["debug"]

    calls = []

    class FakeWriter(LogMixin):
        def __init__(self, influx):
            calls.append(("init", influx))

        def write_metric(self, bucket, measurement, fields, timestamp, state):
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
    result = write_metric("b", "m", {"x": 1}, 123, state, influx_writer=None)

    assert result["status"] == status

    captured = capsys.readouterr()
    output = getattr(captured, stream)

    # Validate logline
    assert expected_level in output
    assert expected_msg in output
    assert "measurement=m" in output
    assert "fields.x=1" in output
    assert "timestamp=123" in output

    # Validate the other stream is empty
    other_stream = "err" if stream == "out" else "out"
    assert getattr(captured, other_stream) == ""
