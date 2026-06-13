# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_config_factory.py

# test_config_factory.py

from finance.timeseries.config import ConfigFactory, InfluxConfig

# -----------------------------
# Helpers
# -----------------------------


class DummySession:
    """Minimal session stub for configure_verify() calls."""

    pass


def factory(config=None, secrets=None):
    return ConfigFactory(config or {}, secrets or {})


# -----------------------------
# Tests
# -----------------------------


def test_missing_url_fails(assert_error):
    f = factory()
    result = f.create(DummySession())
    assert_error(result, "Missing INFLUX_URL", None)


def test_missing_db_and_org(assert_error):
    f = factory(config={"url": "http://localhost:8086"})
    result = f.create(DummySession())
    assert not result.ok
    assert "One of INFLUX_ORG/INFLUX_DB is required" in result.reason


def test_v2_minimal_config(unwrap):
    f = factory(
        config={"url": "http://localhost:8086", "org": "my-org"},
        secrets={"token": "abc123"},
    )
    cfg = unwrap(f.create(DummySession()))

    assert isinstance(cfg, InfluxConfig)
    assert cfg.version == 2
    assert cfg.org == "my-org"
    assert cfg.write_token == "abc123"
    assert cfg.read_token == "abc123"
    assert cfg.base_url == "http://localhost:8086/api/v2/"


def test_v2_missing_token_fails(assert_error):
    f = factory(
        config={"url": "http://localhost:8086", "org": "my-org"},
        secrets={},  # no token
    )
    result = f.create(DummySession())
    assert_error(result, "requires INFLUX_WRITE_TOKEN", None)


def test_v1_minimal_config(unwrap):
    f = factory(
        config={"url": "http://localhost:8086", "db": "mydb"},
        secrets={},
    )
    cfg = unwrap(f.create(DummySession()))
    assert cfg.version == 1
    assert cfg.db == "mydb"
    assert cfg.base_url == "http://localhost:8086"
    assert cfg.auth is None


def test_v1_with_auth(unwrap):
    f = factory(
        config={"url": "http://localhost:8086", "db": "mydb"},
        secrets={"user": "u", "password": "p"},
    )
    cfg = unwrap(f.create(DummySession()))
    assert cfg.auth == ("u", "p")


def test_v2_warning_on_org_and_db(assert_warning):
    f = factory(
        config={"url": "http://localhost:8086", "org": "my-org", "db": "ignored"},
        secrets={"token": "abc"},
    )
    result = f.create(DummySession())
    assert_warning(result, "ignoring db")


def test_batch_policy_defaults(unwrap):
    f = factory(
        config={"url": "http://localhost:8086", "org": "x"},
        secrets={"token": "abc"},
    )
    cfg = unwrap(f.create(DummySession()))

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
    cfg = unwrap(f.create(DummySession()))

    assert cfg.max_batch_size == 50
    assert cfg.max_batch_age_seconds == 0.5


def test_ssl_verify_false(unwrap):
    f = factory(
        config={"url": "http://localhost", "org": "x", "ssl_verify": "false"},
        secrets={"token": "abc"},
    )
    cfg = unwrap(f.create(DummySession()))

    # configure_verify() returns a boolean or path; we only check that it didn't default to True
    assert cfg.ssl_verify is not True


def test_ssl_verify_default_true(unwrap):
    f = factory(
        config={"url": "http://localhost", "org": "x"},
        secrets={"token": "abc"},
    )
    cfg = unwrap(f.create(DummySession()))

    assert cfg.ssl_verify is True
