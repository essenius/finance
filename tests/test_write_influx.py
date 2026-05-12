# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_write_influx.py

from unittest.mock import Mock, patch

from finance.write.influx import InfluxWriter


def test_influx_writer_success():
    secrets = {
        "url": "http://example.com:8086",
        "db": "finance",
        "user": "u",
        "password": "p",
        "ca_cert": None,
    }

    writer = InfluxWriter(secrets)

    with patch("finance.write.influx.requests.post") as mock_post:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        writer.write("spx", {"value": 123}, 100)

        mock_post.assert_called_once_with(
            "http://example.com:8086/write?db=finance&precision=s",
            data="spx value=123 100",
            auth=("u", "p"),
            timeout=5,
            verify=False,
        )

def test_influx_writer_failure():
    secrets = {"url": "http://x", "db": "y"}

    writer = InfluxWriter(secrets)

    with patch("finance.write.influx.requests.post") as mock_post:
        mock_post.side_effect = Exception("boom")

        # Should not raise
        writer.write("spx", {"value": 1}, 100)
