# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx_config.py

from requests import Session

from finance.common.model import Result
from finance.timeseries.config import InfluxConfig
from finance.timeseries.influx import InfluxBackend


class DummyFactory:
    """Override create() to simulate different outcomes."""

    def __init__(self, result: Result):
        self._result = result

    def create(self, *args, **kwargs):
        return self._result


def test_from_config_factory_failure(monkeypatch, assert_error):
    fail_result = Result.fail("boom")

    monkeypatch.setattr(
        "finance.timeseries.influx.ConfigFactory",
        lambda cfg, sec: DummyFactory(fail_result),
    )

    result = InfluxBackend.from_config({"influx": {}}, {"influx": {}})
    assert_error(result, "boom", None)


def test_from_config_success(monkeypatch, unwrap):
    dummy_cfg = InfluxConfig(
        ssl_verify=True,
        ssl_use_legacy=False,
        version=2,
        base_url="http://x/api/v2/",
        org="o",
        write_token="w",
        read_token="r",
        max_batch_size=20,
        max_batch_age_seconds=2.0,
    )

    ok_result = Result.ok_payload(dummy_cfg)

    monkeypatch.setattr(
        "finance.timeseries.influx.ConfigFactory",
        lambda cfg, sec: DummyFactory(ok_result),
    )

    result = InfluxBackend.from_config({}, {})
    backend = unwrap(result)

    assert isinstance(backend, InfluxBackend)
    assert isinstance(backend.session, Session)
    assert backend.cfg is dummy_cfg


def test_from_config_propagates_warnings(monkeypatch, assert_warning):
    dummy_cfg = InfluxConfig(
        ssl_verify=True,
        ssl_use_legacy=False,
        version=2,
        base_url="http://x/api/v2/",
        org="o",
        write_token="w",
        read_token="r",
        max_batch_size=20,
        max_batch_age_seconds=2.0,
    )

    ok_result = Result.ok_payload(dummy_cfg, warnings=["test-warning"])

    monkeypatch.setattr(
        "finance.timeseries.influx.ConfigFactory",
        lambda cfg, sec: DummyFactory(ok_result),
    )

    result = InfluxBackend.from_config({}, {})
    assert_warning(result, "test-warning")


def test_from_config_exception(monkeypatch, assert_error):
    def boom(*args, **kwargs):
        raise RuntimeError("session init failed")

    monkeypatch.setattr("finance.timeseries.influx.Session", boom)

    config = {"url": "http://example", "org": "x", "token": "y"}
    secrets = {}

    result = InfluxBackend.from_config(config, secrets)

    assert_error(result, "Influx backend initialization failed", "session init failed")
