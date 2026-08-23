# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_configuration.py

from datetime import timedelta

import pytest

from finance.common.configuration import (
    ConfigReader,
    JsonObject,
    LoggingConfig,
    ProviderConfig,
    SweepConfig,
    TimescaleConfig,
)


def test_provider_config_defaults():
    config = ProviderConfig.from_config({"name": "x"}, {"x": "secret"})
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
        },
        {},
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

    assert config.get_history_limit(timedelta(minutes=0)) == timedelta(days=5)
    assert config.get_history_limit(timedelta(minutes=5)) == timedelta(days=5)
    assert config.get_history_limit(timedelta(hours=1)) == timedelta(days=60)
    assert config.get_history_limit(timedelta(hours=6)) == timedelta(days=60)
    assert config.get_history_limit(timedelta(days=1)) is None
    assert config.get_history_limit(timedelta(weeks=1)) is None

    intraday_sweep = SweepConfig(timedelta(hours=2), timedelta(minutes=30))
    daily_sweep = SweepConfig(timedelta(days=7), timedelta(days=1))
    assert config.sweep == {timedelta(0): intraday_sweep, timedelta(days=1): daily_sweep}
    assert config.get_sweep(timedelta(hours=8)) == intraday_sweep
    assert config.get_sweep(timedelta(days=1)) == daily_sweep


def test_provider_config_empty_history_limits_and_overlaps():
    config = ProviderConfig.from_config(
        {
            "name": "x",
        },
        {"y": "secret"},
    )
    assert config.name == "x"
    assert config.api_key is None
    assert config.history_limits == {}

    assert config.get_history_limit(timedelta(minutes=0)) is None
    assert config.get_history_limit(timedelta(weeks=1)) is None
    assert config.get_sweep(timedelta(weeks=1)) == SweepConfig(window=timedelta(0), cadence=timedelta(0))


def test_timescaledb_config_failure(assert_error):

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
    config = {
        "level": "debug",
        "use_json": False,
        "date_format": "aabb",
    }

    logging_config = LoggingConfig.from_config(config)

    assert logging_config.level == "debug"
    assert not logging_config.use_json
    assert logging_config.date_format == "aabb"


"""
def test_logging_config_bad_bool():
    config = {
        "use_json": "bogus",
    }

    logging_config = LoggingConfig.from_config(config)

    assert logging_config.level == "info"
    assert logging_config.use_json
    assert logging_config.date_format == "%Y-%m-%dT%H:%M:%S%z"
"""


def test_config_reader():
    config: JsonObject = {"str": "str", "int": 1, "float_int": 2, "float": 2.5, "object": {"bool": True}}
    reader = ConfigReader(config)
    assert reader.get("str", str, "a") == "str", "get(str)"
    assert reader.get("bogus", str, "a") == "a", "get(unknown str)"
    assert reader.get("int", int, 0) == 1, "get(int)"
    assert reader.get("float", float, 0.0) == 2.5, "get(float)"
    assert reader.get("float_int", float, 2) == 2.0, "get(float_int)"

    sub_reader = reader.reader_for("object")
    assert sub_reader.get("bool", bool, False) is True, "get(bool)"

    with pytest.raises(ValueError) as ve:
        sub_reader.get("bool", int, 10)
    assert ve.value.args[0] == "'bool' must be int", "invalid typefor get"

    with pytest.raises(ValueError) as ve:
        reader.get_object("int", {})
    assert ve.value.args[0] == "'int' must be an object", "invalid object for get_object"

    with pytest.raises(ValueError) as ve:
        reader.require("bogus", int)
    assert ve.value.args[0] == "Missing required key 'bogus'"
