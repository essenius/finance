# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_configuration.py

from datetime import timedelta

from finance.common.configuration import LogConfig, ProviderConfig, SweepConfig, TimescaleConfig
from tests.support.types import AssertError


def test_provider_config_defaults():
    config = ProviderConfig.from_config({"name": "x", "api_key": "secret"})
    assert config.name == "x"
    assert config.timeout == "10s"
    assert config.history_limits == {}
    assert config.timeout_delta() == timedelta(seconds=10)
    assert config.api_key == "secret"


def test_provider_config_history_limits_and_overlap():
    config = ProviderConfig.from_config(
        {
            "name": "x",
            "timeout": "20s",
            "constraints": {"history_limits": {"default": "5d", "1h": "60d", "1d": None}},
            "sweep": {"default": {"window": "2h", "cadence": "30m"}, "1d": {"window": "7d", "cadence": "1d"}},
        }
    )
    assert config.name == "x"
    assert config.timeout == "20s"
    assert config.api_key is None
    assert config.history_limits == {
        timedelta(0): timedelta(days=5),
        timedelta(hours=1): timedelta(days=60),
        timedelta(days=1): None,
    }
    assert config.timeout_delta() == timedelta(seconds=20)

    assert config._get_history_limit(timedelta(minutes=0)) == timedelta(days=5)
    assert config._get_history_limit(timedelta(minutes=5)) == timedelta(days=5)
    assert config._get_history_limit(timedelta(hours=1)) == timedelta(days=60)
    assert config._get_history_limit(timedelta(hours=6)) == timedelta(days=60)
    assert config._get_history_limit(timedelta(days=1)) is None
    assert config._get_history_limit(timedelta(weeks=1)) is None

    intraday_sweep = SweepConfig(timedelta(hours=2), timedelta(minutes=30))
    daily_sweep = SweepConfig(timedelta(days=7), timedelta(days=1))
    assert config.sweep == {timedelta(0): intraday_sweep, timedelta(days=1): daily_sweep}
    assert config.get_sweep(timedelta(hours=8)) == intraday_sweep
    assert config.get_sweep(timedelta(days=1)) == daily_sweep


def test_provider_config_empty_history_limits_and_overlaps():
    config = ProviderConfig.from_config(
        {
            "name": "x",
        }
    )
    assert config.name == "x"
    assert config.api_key is None
    assert config.history_limits == {}

    assert config._get_history_limit(timedelta(minutes=0)) is None
    assert config._get_history_limit(timedelta(weeks=1)) is None
    assert config.get_sweep(timedelta(weeks=1)) == SweepConfig(window=timedelta(0), cadence=timedelta(0))


def test_timescaledb_config_failure(assert_error: AssertError):

    result = TimescaleConfig.validate({})
    assert_error(
        result,
        reason="TimescaleDB configuration incomplete",
        error="Missing mandatory fields: ['host', 'db', 'user', 'password']",
    )


def test_timescaledb_config_success_no_defaults():
    config = {
        "host": "myhost",
        "port": 1234,
        "user": "finuser",
        "password": "secret",
        "db": "fin1",
        "ssl_mode": "verify-full",
        "max_batch_size": 500,
        "max_batch_age_seconds": 2.5,
    }

    timescale_config = TimescaleConfig.from_config(config)

    assert timescale_config.host == "myhost"
    assert timescale_config.port == 1234
    assert timescale_config.user == "finuser"
    assert timescale_config.password == "secret"
    assert timescale_config.dbname == "fin1"
    assert timescale_config.sslmode == "verify-full"
    assert timescale_config.sslrootcert == "system"
    assert timescale_config.max_batch_size == 500
    assert timescale_config.max_batch_age == timedelta(seconds=2.5)

    assert timescale_config.connect_config() == {
        "host": "myhost",
        "port": 1234,
        "user": "finuser",
        "password": "secret",
        "dbname": "fin1",
        "sslmode": "verify-full",
        "sslrootcert": "system",
    }


def test_logging_config_ok():
    logging_config = LogConfig.from_config({"level": "debug", "date_format": "aabb"})

    assert logging_config.level == "debug"
    assert logging_config.date_format == "aabb"
