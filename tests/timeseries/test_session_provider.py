# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_session_provider.py

"""
TODO delete
from ssl import CERT_REQUIRED, PROTOCOL_TLS_CLIENT

from requests.adapters import BaseAdapter

from finance.timeseries.config import InfluxConfig
from finance.timeseries.session_provider import SessionProvider, SSLContextAdapter


class MockSession:
    def __init__(self):
        self.protocol = None
        self.adapter = None

    def mount(self, protocol: str, adapter: BaseAdapter) -> None:
        self.protocol = protocol
        self.adapter = adapter


class MockContext(BaseAdapter):
    def __init__(self, protocol: int):
        self.protocol = protocol
        self.calls = []

    def load_verify_locations(self, cafile: str | None):
        self.calls.append(cafile)

    def set_ciphers(self, cipherlist: str) -> None:
        self.cipherlist = cipherlist


def test_session_provider_uses_default():
    cfg = InfluxConfig(
        ssl_verify=True,
        ssl_use_legacy=False,
        version=1,
        base_url="http://example",
        max_batch_size=1,
        max_batch_age_seconds=0.0,
    )
    provider = SessionProvider(session_factory=MockSession, ssl_context_factory=MockContext)
    session = provider.get(cfg=cfg)
    assert isinstance(session, MockSession)
    assert session.verify is True
    assert session.timeout == 5
    # not using legacy so not setting context or adapter
    assert session.protocol is None
    assert session.adapter is None


def test_session_provider_sets_ssl_adapter_with_ca():
    cfg = InfluxConfig(
        ssl_verify="/tmp/custom-ca.pem",
        ssl_use_legacy=True,
        version=1,
        base_url="http://example",
        max_batch_size=1,
        max_batch_age_seconds=0.0,
    )
    provider = SessionProvider(session_factory=MockSession, ssl_context_factory=MockContext)
    session = provider.get(cfg=cfg)
    assert isinstance(session, MockSession)
    assert session.verify == "/tmp/custom-ca.pem"
    assert session.timeout == 5
    # using legacy, so setting protocol and context
    assert session.protocol == "https://"
    assert isinstance(session.adapter, SSLContextAdapter)
    context = session.adapter.ssl_context
    assert isinstance(context, MockContext)
    assert context.protocol == PROTOCOL_TLS_CLIENT
    assert context.verify_mode == CERT_REQUIRED
    assert context.check_hostname is True
    assert context.calls[0] == "/tmp/custom-ca.pem"
    assert context.cipherlist == "DEFAULT:@SECLEVEL=1"


def test_session_provider_sets_ssl_adapter_without_ca():
    cfg = InfluxConfig(
        ssl_verify=True,
        ssl_use_legacy=True,
        version=1,
        base_url="http://example",
        max_batch_size=1,
        max_batch_age_seconds=0.0,
    )
    provider = SessionProvider(session_factory=MockSession, ssl_context_factory=MockContext)
    session = provider.get(cfg=cfg)
    assert isinstance(session, MockSession)
    assert session.verify is True
    assert session.timeout == 5
    # using legacy, so setting protocol and context, but no ca file
    assert session.protocol == "https://"
    context = session.adapter.ssl_context
    assert context.calls == []
    assert context.cipherlist == "DEFAULT:@SECLEVEL=1"
"""
