# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_config_factory.py

"""
TODO delete
from finance.timeseries.config import ConfigBuilder, InfluxConfig


def factory(config=None, secrets=None):
    return ConfigBuilder(config or {}, secrets or {})


def test_missing_url_fails(assert_error):
    f = factory()
    result = f.create()
    assert_error(result, "Missing TIMESCALEDB_URL", None)



def test_minimal_config(unwrap):
    f = factory(
        config={"url": "http://localhost:5432", "db": "mydb"},
        secrets={},
    )
    cfg = unwrap(f.create())
    assert cfg.db == "mydb"
    assert cfg.base_url == "http://localhost:5432"
    assert cfg.auth is None


def test_with_auth(unwrap):
    f = factory(
        config={"url": "http://localhost:5432", "db": "mydb"},
        secrets={"user": "u", "password": "p"},
    )
    cfg = unwrap(f.create())
    assert cfg.auth == ("u", "p")


def test_v2_warning_on_org_and_db(assert_warning):
    f = factory(
        config={"url": "http://localhost:8086", "org": "my-org", "db": "ignored"},
        secrets={"token": "abc"},
    )
    result = f.create()
    assert_warning(result, "ignoring db")


def test_batch_policy_defaults(unwrap):
    f = factory(
        config={"url": "http://localhost:8086", "org": "x"},
        secrets={"token": "abc"},
    )
    cfg = unwrap(f.create())

    assert cfg.max_batch_size == 20
    assert cfg.max_batch_age_seconds == 2.0


def test_batch_policy_overrides(unwrap):
    f = factory(
        config={
            "url": "http://localhost:8086",
            "org": "x",
            "max_batch_size": 50,
            "max_batch_age_seconds": 0.5,
        },
        secrets={"token": "abc"},
    )
    cfg = unwrap(f.create())

    assert cfg.max_batch_size == 50
    assert cfg.max_batch_age_seconds == 0.5


def test_ssl_verify_false(unwrap):
    f = factory(
        config={"url": "http://localhost", "org": "x", "ssl_verify": "false"},
        secrets={"token": "abc"},
    )
    cfg = unwrap(f.create())
    assert cfg.ssl_verify is False


def test_ssl_verify_default_true(unwrap):
    f = factory(
        config={"url": "http://localhost", "org": "x"},
        secrets={"token": "abc"},
    )
    cfg = unwrap(f.create())
    assert cfg.ssl_verify is True


def test_config_factory_verify_failure(assert_error):
    f = ConfigBuilder(
        config={"url": "http://x", "ssl_verify": "pinned"},
        secrets={},  # no ssl_cert → pinned must fail
    )

    result = f.create()

    assert_error(result, "Pinned mode requires a certificate path", None)
"""
