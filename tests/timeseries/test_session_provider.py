# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_ssl_context_adapter.py

import ssl
from unittest.mock import MagicMock, patch

from finance.timeseries.config import InfluxConfig
from finance.timeseries.influx import InfluxBackend
from finance.timeseries.ssl_context_adapter import make_legacy_ssl_context


def test_backend_legacy_mounts_adapter():
    session = MagicMock()
    cfg = InfluxConfig(
        ssl_verify=True,
        ssl_use_legacy=True,
        version=1,
        base_url="http://x",
        max_batch_size=1,
        max_batch_age_seconds=0,
    )

    with patch("finance.timeseries.ssl_context_adapter.make_legacy_ssl_context") as m:
        ctx = MagicMock()
        m.return_value = ctx

        InfluxBackend(session, cfg)

        session.mount.assert_called_once()


@patch("finance.timeseries.influx.make_legacy_ssl_context")
def test_backend_legacy_passes_cafile(mock_ctx):
    session = MagicMock()
    ctx = MagicMock()
    mock_ctx.return_value = ctx

    cfg = InfluxConfig(
        ssl_verify="/tmp/custom-ca.pem",
        ssl_use_legacy=True,
        version=1,
        base_url="http://example",
        max_batch_size=1,
        max_batch_age_seconds=0.0,
        db="x",
        auth=None,
    )

    InfluxBackend(session, cfg)

    mock_ctx.assert_called_once_with("/tmp/custom-ca.pem")


def test_make_legacy_ssl_context_with_cafile():
    with patch("finance.timeseries.ssl_context_adapter.ssl.SSLContext") as mock_ssl_context:
        mock_ctx = MagicMock()
        mock_ssl_context.return_value = mock_ctx

        result = make_legacy_ssl_context("/path/ca.pem")

        mock_ssl_context.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
        mock_ctx.load_verify_locations.assert_called_once_with("/path/ca.pem")
        mock_ctx.set_ciphers.assert_called_once_with("DEFAULT:@SECLEVEL=1")
        assert result is mock_ctx
