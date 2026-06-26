# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/ssl_context_adapter.py

import ssl

from requests.adapters import HTTPAdapter


class SSLContextAdapter(HTTPAdapter):
    def __init__(self, ssl_context, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        return super().init_poolmanager(*args, **kwargs)


def make_legacy_ssl_context(cafile: str | None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    if cafile:
        ctx.load_verify_locations(cafile)

    # The key line: restore OpenSSL 1.1‑style permissiveness
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")

    return ctx
