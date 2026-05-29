# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/write/test_influx.py

import ssl
from unittest.mock import MagicMock, Mock, patch

import pytest

from finance.write.influx import InfluxWriter, configure_verify
from finance.write.ssl_context_adapter import SSLContextAdapter, make_legacy_ssl_context

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


@patch("finance.write.influx.make_legacy_ssl_context")
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


@patch("finance.write.influx.make_legacy_ssl_context")
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
    with patch("finance.write.ssl_context_adapter.ssl.SSLContext") as mock_ssl_context:
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


# --- InfluxWriter tests ------------------------------------------------------


def test_influx_writer_failure():
    secrets = {"url": "http://x", "db": "y"}

    writer = InfluxWriter(secrets)

    with patch("requests.sessions.Session.post") as mock_post:
        mock_post.side_effect = Exception("boom")

        # Should not raise
        result = writer.write("bucket", "spx", {"value": 1}, 100)

        assert result["ok"] is False
        assert "boom" in result["error"]


@pytest.mark.parametrize("verify_mode", ["true", "false", "pinned", "legacy"])
def test_influx_writer_uses_session(verify_mode):
    secrets = {
        "url": "https://example:8086",
        "db": "test",
        "user": "u",
        "password": "p",
        "ssl_verify": verify_mode,
        "cert": "/home/pi/certs/ca-both.crt",
    }
    # Prevent legacy mode from touching the filesystem
    with patch("finance.write.influx.make_legacy_ssl_context") as mock_ctx_factory:
        mock_ctx = Mock()
        mock_ctx_factory.return_value = mock_ctx

        writer = InfluxWriter(secrets)

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None

        with patch("requests.sessions.Session.send", return_value=mock_response) as mock_send:
            writer.write("bucket", "m", {"value": 1}, 123)
            mock_send.assert_called_once()


def test_influx_writer_v2_mode(capsys):
    secrets = {
        "url": "https://example:8086",
        "org": "rik",
        "token": "abc123",
        # set db to see if it is ignored
        "db": "rik",
    }

    writer = InfluxWriter(secrets)

    assert writer.is_v2 is True
    assert writer.is_v1 is True
    assert writer.org == "rik"
    assert writer.token == "abc123"
    assert writer.base_url.endswith("/api/v2/write")
    assert not hasattr(writer, "db")
    assert (
        "WARNING | secrets contain both 'org' (InfluxDb 2.x) and 'db' (InfluxDB 1.x), ignoring 'db'"
        in capsys.readouterr().out
    )


def test_influx_writer_missing_db_and_org():
    secrets = {"url": "https://example:8086"}

    with pytest.raises(ValueError):
        InfluxWriter(secrets)


def test_influx_writer_tags_included():
    secrets = {"url": "http://x", "db": "y"}

    writer = InfluxWriter(secrets)

    with patch("requests.sessions.Session.post") as mock_post:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = writer.write("bucket", "m", {"value": 1}, 123, tags={"a": "b", "c": "d"})

        assert result["ok"]
        assert result.get("error") is None

        args, kwargs = mock_post.call_args
        sent_line = kwargs["data"]

        assert "m,a=b,c=d" in sent_line
        assert "value=1" in sent_line
        assert sent_line.endswith("123")


def test_influx_writer_v2_write():
    secrets = {
        "url": "https://example:8086",
        "org": "rik",
        "token": "abc123",
    }

    writer = InfluxWriter(secrets)

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None

    with patch("requests.sessions.Session.post", return_value=mock_response) as mock_post:
        writer.write("finance_daily", "gold", {"price": 123}, 1000)

        args, kwargs = mock_post.call_args

        # URL correctness
        assert "bucket=finance_daily" in args[0]
        assert "org=rik" in args[0]

        # Token header
        assert kwargs["headers"]["Authorization"] == "Token abc123"

        # No basic auth
        assert "auth" not in kwargs or kwargs["auth"] is None


def test_influx_writer_multifield_line_protocol():
    secrets = {"url": "http://x", "db": "y"}
    writer = InfluxWriter(secrets)

    with patch("requests.sessions.Session.post") as mock_post:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        fields = {"open": 1, "close": 2, "volume": 3}
        writer.write("bucket", "m", fields, 123)

        args, kwargs = mock_post.call_args
        sent_line = kwargs["data"]

        # Correct measurement
        assert sent_line.startswith("m ")

        # All fields present
        assert "open=1" in sent_line
        assert "close=2" in sent_line
        assert "volume=3" in sent_line

        # Correct timestamp
        assert sent_line.endswith("123")


def test_influx_writer_multifield_with_tags():
    secrets = {"url": "http://x", "db": "y"}
    writer = InfluxWriter(secrets)

    with patch("requests.sessions.Session.post") as mock_post:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        fields = {"open": 1, "close": 2}
        tags = {"source": "test", "env": "dev"}

        writer.write("bucket", "m", fields, 999, tags=tags)

        args, kwargs = mock_post.call_args
        sent_line = kwargs["data"]

        # Tags must appear after measurement, comma‑separated
        assert sent_line.startswith("m,source=test,env=dev ")

        # Fields must appear after a space
        assert " open=1" in sent_line or " close=2" in sent_line

        # Timestamp must be last
        assert sent_line.endswith("999")


def test_influx_writer_field_order_is_stable():
    secrets = {"url": "http://x", "db": "y"}
    writer = InfluxWriter(secrets)

    with patch("requests.sessions.Session.post") as mock_post:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        fields = {"b": 2, "a": 1}
        writer.write("bucket", "m", fields, 10)

        sent_line = mock_post.call_args[1]["data"]

        # Python 3.7+ preserves dict insertion order
        assert "b=2,a=1" in sent_line
