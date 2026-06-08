# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx_read.py

from unittest.mock import Mock

from finance.timeseries.influx import InfluxBackend, InfluxConfig


def test_read_v1():
    session = Mock()
    session.get.return_value = Mock(
        raise_for_status=lambda: None,
        json=lambda: {
            "results": [
                {
                    "series": [
                        {
                            "columns": ["time", "value"],
                            "values": [["2024-01-01T00:00:00Z", 10]],
                        }
                    ]
                }
            ]
        },
    )

    cfg = InfluxConfig(True, 1, "http://x/write", db="d")
    backend = InfluxBackend(session, cfg)

    result = backend.read("bucket", "m")
    assert result.ok
    assert result.payload.fields == {"value": 10}


def test_read_v2_exception():
    session = Mock()
    session.post.side_effect = Exception("fail")

    cfg = InfluxConfig(True, 2, "https://x/api/v2/write", org="o", read_token="t")
    backend = InfluxBackend(session, cfg)

    result = backend.read("bucket", "m")
    assert not result.ok
    assert "Influx read failed" in result.reason


def test_read_v1_exception():
    session = Mock()
    session.get.side_effect = Exception("fail")

    cfg = InfluxConfig(True, 1, "http://x/write", db="d")
    backend = InfluxBackend(session, cfg)

    result = backend.read("bucket", "m")
    assert not result.ok
    assert "Influx read failed" in result.reason


def test_read_v2_url_and_headers():
    session = Mock()
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"tables": []}
    session.post.return_value = fake_response

    cfg = InfluxConfig(True, 2, "https://example/api/v2/write", org="rik", read_token="abc")
    backend = InfluxBackend(session, cfg)

    backend.read("bucket", "m")

    url = session.post.call_args.args[0]
    assert url.endswith("/query")
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Token abc"
