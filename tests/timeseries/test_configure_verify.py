# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_configure_verify.py

from unittest.mock import Mock

import pytest

from finance.timeseries.config import configure_verify
from finance.timeseries.ssl_context_adapter import SSLContextAdapter


def test_configure_verify_true_mode():
    session = Mock()
    result = configure_verify(session, "true", None)
    assert result is True


def test_configure_verify_false_mode():
    session = Mock()
    result = configure_verify(session, "false", None)
    assert result is False


def test_configure_verify_pinned_requires_cert():
    session = Mock()
    with pytest.raises(ValueError):
        configure_verify(session, "pinned", None)


def test_configure_verify_pinned_uses_cert():
    session = Mock()
    result = configure_verify(session, "pinned", "/tmp/cert.pem")
    assert result == "/tmp/cert.pem"


def test_configure_verify_legacy_with_cert(monkeypatch):
    session = Mock()
    fake_ctx = Mock()
    monkeypatch.setattr(
        "finance.timeseries.config.make_legacy_ssl_context",
        lambda c: fake_ctx,
    )

    result = configure_verify(session, "legacy", "/tmp/cert.pem")
    assert result is True
    session.mount.assert_called_once()


def test_configure_verify_invalid_mode():
    session = Mock()
    with pytest.raises(ValueError):
        configure_verify(session, "weird", None)


def test_configure_verify_legacy_uses_default_cert(monkeypatch):
    session = Mock()

    # Capture the cert path passed to make_legacy_ssl_context
    captured = {}

    def fake_make_legacy_ssl_context(cert_path):
        captured["cert"] = cert_path
        return Mock()

    monkeypatch.setattr(
        "finance.timeseries.config.make_legacy_ssl_context",
        fake_make_legacy_ssl_context,
    )

    result = configure_verify(session, "legacy", None)

    # Returned value must be True
    assert result is True

    # It must call make_legacy_ssl_context with the default CA bundle
    assert captured["cert"] == "/etc/ssl/certs/ca-certificates.crt"

    # And mount must be called with an SSLContextAdapter
    session.mount.assert_called_once()
    args, kwargs = session.mount.call_args
    assert args[0] == "https://"
    assert isinstance(args[1], SSLContextAdapter)
