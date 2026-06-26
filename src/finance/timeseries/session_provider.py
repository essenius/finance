# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/session_provider.py

"""
TODO delete
from collections.abc import Callable
from ssl import CERT_REQUIRED, PROTOCOL_TLS_CLIENT, SSLContext

from requests import Session
from requests.adapters import HTTPAdapter

from .config import InfluxConfig


class SSLContextAdapter(HTTPAdapter):
    def __init__(self, ssl_context, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        return super().init_poolmanager(*args, **kwargs)


class SessionProvider:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = Session,
        ssl_context_factory: Callable[[int], SSLContext] = SSLContextAdapter,
    ):
        self.session_factory = session_factory
        self.ssl_context_factory = ssl_context_factory

    def get(self, cfg: InfluxConfig) -> Session:
        session = self.session_factory()
        session.verify = cfg.ssl_verify
        session.timeout = 5

        if cfg.ssl_use_legacy:
            ca_file = cfg.ssl_verify if isinstance(cfg.ssl_verify, str) else None
            ctx = self._make_legacy_ssl_context(ca_file=ca_file)
            adapter = SSLContextAdapter(ctx)
            session.mount("https://", adapter)

        return session

    def _make_legacy_ssl_context(self, ca_file: str | None) -> SSLContext:
        ctx = self.ssl_context_factory(PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = CERT_REQUIRED
        ctx.check_hostname = True
        if ca_file:
            ctx.load_verify_locations(cafile=ca_file)

        # The key line: restore OpenSSL 1.1‑style permissiveness
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")

        return ctx
"""
