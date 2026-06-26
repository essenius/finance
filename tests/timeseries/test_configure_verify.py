# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_configure_verify.py

"""
TODO delete
from finance.timeseries.config import ConfigBuilder, VerifyConfig


def make_factory(cfg=None, secrets=None):
    return ConfigBuilder(cfg or {}, secrets or {})


def test_verify_true():
    f = make_factory()
    r = f.configure_verify("true", None)
    assert r.ok
    assert r.payload == VerifyConfig(ssl_verify=True, ssl_use_legacy=False)


def test_verify_false():
    f = make_factory()
    r = f.configure_verify("false", None)
    assert r.ok
    assert r.payload == VerifyConfig(ssl_verify=False, ssl_use_legacy=False)


def test_verify_pinned_requires_cert():
    f = make_factory()
    r = f.configure_verify("pinned", None)
    assert not r.ok


def test_verify_pinned_uses_cert():
    f = make_factory()
    r = f.configure_verify("pinned", "/tmp/cert.pem")
    assert r.ok
    assert r.payload == VerifyConfig(ssl_verify="/tmp/cert.pem", ssl_use_legacy=False)


def test_verify_legacy_with_cert():
    f = make_factory()
    r = f.configure_verify("legacy", "/tmp/cert.pem")
    assert r.ok
    assert r.payload == VerifyConfig(ssl_verify="/tmp/cert.pem", ssl_use_legacy=True)


def test_verify_legacy_without_cert():
    f = make_factory()
    r = f.configure_verify("legacy", None)
    assert r.ok
    assert r.payload == VerifyConfig(ssl_verify=True, ssl_use_legacy=True)


def test_verify_invalid_mode():
    f = make_factory()
    r = f.configure_verify("weird", None)
    assert not r.ok
"""
