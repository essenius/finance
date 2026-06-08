# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx.py

from unittest.mock import Mock, patch

import pytest

from finance.common.model import (
    Result,
    TimeseriesResult,
    TimeseriesWrite,
)
from finance.timeseries.influx import (
    InfluxBackend,
    InfluxConfig,
    configure_verify,
)
from finance.timeseries.ssl_context_adapter import SSLContextAdapter

# -----------------------
# Configure Verify tests
# -----------------------

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
        "finance.timeseries.influx.make_legacy_ssl_context",
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
        "finance.timeseries.influx.make_legacy_ssl_context",
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

# -----------------------
# From Secrets tests
# -----------------------

def test_from_secrets_v2_success(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", lambda: session)

    secrets = {
        "url": "https://example",
        "org": "rik",
        "write-token": "w",
        "read-token": "r",
    }

    result = InfluxBackend.from_secrets(secrets)
    assert result.ok

    backend = result.payload
    assert backend.cfg.version == 2
    assert backend.cfg.org == "rik"
    assert backend.cfg.write_token == "w"

def test_from_secrets_v1_success(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", lambda: session)

    secrets = {
        "url": "https://example",
        "db": "finance",
        "user": "u",
        "password": "p",
    }

    result = InfluxBackend.from_secrets(secrets)
    assert result.ok

    backend = result.payload
    assert backend.cfg.version == 1
    assert backend.cfg.db == "finance"
    assert backend.cfg.auth == ("u", "p")

def test_from_secrets_missing_both():
    result = InfluxBackend.from_secrets({"url": "x"})
    assert not result.ok

def test_from_secrets_org_and_db(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", lambda: session)

    secrets = {
        "url": "https://example",
        "org": "rik",
        "db": "legacy",
        "write-token": "w",
        "read-token": "r",
    }

    result = InfluxBackend.from_secrets(secrets)
    assert result.ok
    backend, warning = result.payload, result.warning
    assert "ignoring 'db'" in warning
    assert backend.cfg.version == 2


def test_from_secrets_config_none(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", lambda: session)

    # No org, no db → config stays None
    secrets = {"url": "https://example"}

    result = InfluxBackend.from_secrets(secrets)
    assert not result.ok
    assert "Secrets must contain either 'org' or 'db'" in result.reason


def test_from_secrets_exception_path(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", lambda: session)

    # Force configure_verify to throw inside the try block
    monkeypatch.setattr(
        "finance.timeseries.influx.configure_verify",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("boom"))
    )

    secrets = {"url": "https://example", "db": "x"}

    result = InfluxBackend.from_secrets(secrets)

    assert not result.ok
    assert result.reason == "Influx backend initialization failed"
    assert "boom" in str(result.error)
