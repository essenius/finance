# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx_config.py

# test_influx_from_config.py
from requests import Session

from finance.common.model import Result
from finance.timeseries.config import ConfigFactory, InfluxConfig
from finance.timeseries.influx import InfluxBackend


class DummyFactory(ConfigFactory):
    """Override create() to simulate different outcomes."""

    def __init__(self, result: Result):
        self._result = result

    def create(self, session):
        return self._result


def test_from_config_factory_failure(monkeypatch, assert_error):
    """If ConfigFactory.create() returns a failure, from_config must return that failure."""
    fail_result = Result.fail("boom")
    monkeypatch.setattr("finance.timeseries.influx.ConfigFactory", lambda cfg, sec: DummyFactory(fail_result))
    assert_error(InfluxBackend.from_config({"influx": {}}, {"influx": {}}), "boom", None)


def test_from_config_success(monkeypatch, unwrap):
    """Successful factory → backend instance returned."""
    dummy_cfg = InfluxConfig(
        ssl_verify=True,
        version=2,
        base_url="http://x/api/v2/",
        org="o",
        write_token="w",
        read_token="r",
        max_batch_size=20,
        max_batch_age_seconds=2.0,
    )

    ok_result = Result.ok_payload(dummy_cfg)

    monkeypatch.setattr("finance.timeseries.influx.ConfigFactory", lambda cfg, sec: DummyFactory(ok_result))
    result = InfluxBackend.from_config({}, {})
    backend = unwrap(result)

    assert isinstance(backend, InfluxBackend)
    assert isinstance(backend.session, Session)
    assert backend.cfg is dummy_cfg


def test_from_config_propagates_warnings(monkeypatch, assert_warning):
    dummy_cfg = InfluxConfig(
        ssl_verify=True,
        version=2,
        base_url="http://x/api/v2/",
        org="o",
        write_token="w",
        read_token="r",
        max_batch_size=20,
        max_batch_age_seconds=2.0,
    )

    ok_result = Result.ok_payload(dummy_cfg, warnings=["test-warning"])

    monkeypatch.setattr("finance.timeseries.influx.ConfigFactory", lambda cfg, sec: DummyFactory(ok_result))

    result = InfluxBackend.from_config({}, {})
    assert_warning(result, "test-warning")


def test_from_config_exception(monkeypatch, assert_error):
    # Make Session() raise an exception
    def boom(*args, **kwargs):
        raise RuntimeError("session init failed")

    monkeypatch.setattr("finance.timeseries.influx.Session", boom)

    config = {"url": "http://example", "org": "x", "token": "y"}
    secrets = {}

    result = InfluxBackend.from_config(config, secrets)

    assert_error(result, "Influx backend initialization failed", "session init failed")


"""
# -----------------------
# From Secrets
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

    result = InfluxBackend.from_config(secrets)
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

    result = InfluxBackend.from_config(secrets)
    assert result.ok

    backend = result.payload
    assert backend.cfg.version == 1
    assert backend.cfg.db == "finance"
    assert backend.cfg.auth == ("u", "p")


def test_from_secrets_missing_both():
    result = InfluxBackend.from_config({"url": "x"})
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

    result = InfluxBackend.from_config(secrets)
    assert result.ok
    backend, warning = result.payload, result.warning
    assert "ignoring 'db'" in warning
    assert backend.cfg.version == 2


def test_from_secrets_config_none(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", lambda: session)

    # No org, no db → config stays None
    secrets = {"url": "https://example"}

    result = InfluxBackend.from_config(secrets)
    assert not result.ok
    assert "Secrets must contain either 'org' or 'db'" in result.reason


def test_from_secrets_exception_path(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", lambda: session)

    # Force configure_verify to throw inside the try block
    monkeypatch.setattr(
        "finance.timeseries.influx.configure_verify", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("boom"))
    )

    secrets = {"url": "https://example", "db": "x"}

    result = InfluxBackend.from_config(secrets)

    assert not result.ok
    assert result.reason == "Influx backend initialization failed"
    assert "boom" in str(result.error)

"""
