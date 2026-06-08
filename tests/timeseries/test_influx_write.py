# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx_write.py

from unittest.mock import Mock

from finance.common.model import TimeseriesWrite
from finance.timeseries.influx import InfluxBackend, InfluxConfig


def test_write_v1_success():
    session = Mock()
    session.post.return_value = Mock(raise_for_status=lambda: None)

    cfg = InfluxConfig(
        ssl_verify=True,
        version=1,
        base_url="http://x/write",
        db="finance",
        auth=("u", "p"),
    )

    backend = InfluxBackend(session, cfg)

    entry = TimeseriesWrite(
        measurement="spx",
        fields={"value": 1},
        tags={"a": "b"},
        timestamp=100,
        bucket="bucket",
    )

    result = backend.write(entry)
    assert result.ok

    session.post.assert_called_once()
    sent = session.post.call_args.kwargs["data"]
    assert sent == "spx,a=b value=1 100"


def test_write_v2_success():
    session = Mock()
    session.post.return_value = Mock(raise_for_status=lambda: None)

    cfg = InfluxConfig(
        ssl_verify=True,
        version=2,
        base_url="https://example/api/v2/write",
        org="rik",
        write_token="abc",
    )

    backend = InfluxBackend(session, cfg)

    entry = TimeseriesWrite(
        measurement="gold",
        fields={"price": 123},
        tags={},
        timestamp=1000,
        bucket="finance_daily",
    )

    result = backend.write(entry)
    assert result.ok

    url = session.post.call_args.args[0]
    assert "bucket=finance_daily" in url
    assert "org=rik" in url

    headers = session.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Token abc"


def test_write_failure():
    session = Mock()
    session.post.side_effect = Exception("boom")

    cfg = InfluxConfig(
        ssl_verify=True,
        version=1,
        base_url="http://x/write",
        db="finance",
        auth=None,
    )

    backend = InfluxBackend(session, cfg)

    entry = TimeseriesWrite("m", {"v": 1}, {}, 10, "bucket")

    result = backend.write(entry)
    assert not result.ok
    assert "Influx write failed" in result.reason


def test_write_no_tags():
    session = Mock()
    session.post.return_value = Mock(raise_for_status=lambda: None)

    cfg = InfluxConfig(True, 1, "http://x/write", db="d")
    backend = InfluxBackend(session, cfg)

    entry = TimeseriesWrite("m", {"v": 1}, {}, 10, "bucket")
    backend.write(entry)

    sent = session.post.call_args.kwargs["data"]
    assert sent == "m v=1 10"
