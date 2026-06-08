# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_ssl_context_adapter.py

import ssl
from unittest.mock import MagicMock, patch

import pytest

from finance.timeseries.influx import configure_verify
from finance.timeseries.ssl_context_adapter import SSLContextAdapter, make_legacy_ssl_context

# --- configure_verify tests ---------------------------------------------------

# --- Strict mode -------------------------------------------------------------


def test_strict_no_cert():
    session = MagicMock()
    result = configure_verify(session, "true", None)
    assert result is True
    session.mount.assert_not_called()


def test_strict_with_cert():
    session = MagicMock()
    result = configure_verify(session, "true", "/path/ca.pem")
    assert result == "/path/ca.pem"
    session.mount.assert_not_called()


# --- Insecure mode -----------------------------------------------------------


def test_insecure_mode():
    session = MagicMock()
    result = configure_verify(session, "false", None)
    assert result is False
    session.mount.assert_not_called()


# --- Pinned mode -------------------------------------------------------------


def test_pinned_requires_cert():
    session = MagicMock()
    with pytest.raises(ValueError):
        configure_verify(session, "pinned", None)


def test_pinned_with_cert():
    session = MagicMock()
    result = configure_verify(session, "pinned", "/path/server.pem")
    assert result == "/path/server.pem"
    session.mount.assert_not_called()


# --- Legacy mode -------------------------------------------------------------


@patch("finance.timeseries.influx.make_legacy_ssl_context")
def test_legacy_with_cert(mock_ctx):
    session = MagicMock()
    ctx = MagicMock()
    mock_ctx.return_value = ctx

    result = configure_verify(session, "legacy", "/path/ca.pem")

    assert result is True
    mock_ctx.assert_called_once_with("/path/ca.pem")
    session.mount.assert_called_once()
    args, kwargs = session.mount.call_args
    assert args[0] == "https://"
    assert isinstance(args[1], SSLContextAdapter)


@patch("finance.timeseries.influx.make_legacy_ssl_context")
def test_legacy_without_cert(mock_ctx):
    session = MagicMock()
    ctx = MagicMock()
    mock_ctx.return_value = ctx

    result = configure_verify(session, "legacy", None)

    assert result is True
    mock_ctx.assert_called_once_with("/etc/ssl/certs/ca-certificates.crt")
    session.mount.assert_called_once()


# --- Unknown mode ------------------------------------------------------------


def test_unknown_mode():
    session = MagicMock()
    with pytest.raises(ValueError):
        configure_verify(session, "weird", None)


# --- make_legacy_ssl_context tests -------------------------------------------


def test_make_legacy_ssl_context():
    # Patch SSLContext constructor inside ssl_context_adapter
    with patch("finance.timeseries.ssl_context_adapter.ssl.SSLContext") as mock_ssl_context:
        mock_ctx = MagicMock()
        mock_ssl_context.return_value = mock_ctx

        result = make_legacy_ssl_context("/path/ca.pem")

        # SSLContext created with correct protocol
        mock_ssl_context.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)

        # verify_mode and check_hostname set correctly
        assert mock_ctx.verify_mode == ssl.CERT_REQUIRED
        assert mock_ctx.check_hostname is True

        # set_ciphers called with correct argument
        mock_ctx.set_ciphers.assert_called_once_with("DEFAULT:@SECLEVEL=1")

        # load_verify_locations called with correct path
        mock_ctx.load_verify_locations.assert_called_once_with("/path/ca.pem")

        # function returns the mocked context
        assert result is mock_ctx
