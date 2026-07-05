# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_model_result.py

from datetime import timedelta

import pytest

from finance.common.model import (
    Asset,
    Candle,
    MeasurementResult,
    ProviderConfig,
    Result,
    Retention,
    Series,
    SeriesPoint,
    SeriesState,
    SeriesType,
)


def test_stringenum_validate():
    with pytest.raises(ValueError) as exc_info:
        Retention.validate("bogus")
        assert "Invalid Retention: 'bogus'. Allowed: short_lived, long_lived" in exc_info


def test_stringenum_contains():
    assert Candle.contains("close")
    assert not Candle.contains("value")


def test_stringenum_values():
    assert SeriesType.values() == ["candle", "value"]


def test_candle_ordered():
    assert Candle.ordered() == ["open", "high", "low", "close", "volume"]


def test_seriespoint_from_to_dict(fixed_now):
    now = fixed_now()
    # omitted volume on purpose
    point = SeriesPoint(1, now, open=10, high=14, low=8, close=12)
    dict1 = point.to_dict()
    result1 = SeriesPoint.from_dict(dict1)
    assert result1 == point
    assert f"{result1}" == "SeriesPoint(id=1, time=2025-06-15T15:06:40+00:00, open=10, high=14, low=8, close=12)"


def test_asset_create_with_id_differs():
    config = {"symbol": "SPX", "provider": {"name": "yahoo", "code": "^SPX"}}
    tags = {"instrument": "forex"}
    asset = Asset.create(name="spx", config=config, tags=tags)
    assert asset.id is None
    assert asset.name == "spx"
    assert asset.symbol == "SPX"
    assert asset.provider == "yahoo"
    assert asset.provider_code == "^SPX"
    assert asset.display_name == "spx"
    assert asset.instrument == "forex"
    assert asset.exchange is None
    assert asset.region is None
    assert asset.currency is None
    assert asset.unit is None
    assert f"{asset}" == "Asset(id=None, name=spx, symbol=SPX, provider_code=^SPX, region=None)"

    asset2 = asset.with_id(1)
    assert asset2.id == 1
    assert asset2.name == "spx"

    # differs from only looks at metadata, not at id, name
    assert not asset.differs_from(asset2)

    tags = tags | {"region": "Europe"}
    asset3 = Asset.create(name="spx", config=config, tags=tags)
    assert asset.differs_from(asset3)


def test_series_create_with_id_differs(make_asset):
    asset = make_asset(name="spx", id=3)
    config = {
        "symbol": "SPX",
        "series_type": "candle",
        "interval": "1d",
        "bootstrap_history": "10y",
        "retention": "long_lived",
    }
    series = Series.create(asset=asset, code="dummy", config=config)
    assert series.id is None
    assert series.code == "dummy"
    assert series.name == "spx:dummy"
    assert series.asset_name == "spx"
    assert series.asset_id == 3
    assert series.retention == Retention.LONG_LIVED
    assert series.series_type == SeriesType.CANDLE
    assert series.interval == "1d"
    assert series.interval_delta() == timedelta(days=1)
    assert series.bootstrap_history == "10y"
    assert series.bootstrap_history_delta() == timedelta(days=3652.5)

    series2 = series.with_id(10)
    assert (
        f"{series2}"
        == "Series(id=10, name=spx:dummy, asset_id=3, retention=long_lived, series_type=candle, interval=1d)"
    )

    # differs from only looks at metadata, not at id, name
    assert not series.differs_from(series2)

    config = config | {"bootstrap_history": "5y"}
    series3 = Series.create(asset, code="dummy", config=config)
    assert series.differs_from(series3)
    assert series3.bootstrap_history == "5y"


def test_result_success_payload():
    result = MeasurementResult.ok_payload("spx", payload=[1, 2, 3])

    assert result.ok is True
    assert result.series_name == "spx"
    assert result.payload == [1, 2, 3]
    assert result.warnings is None
    assert result.error is None
    assert result.reason is None
    assert result.meta is None


def test_result_success_no_payload():
    result = MeasurementResult.ok_payload("spx", None)

    assert result.ok is True
    assert result.series_name == "spx"
    assert result.payload is None
    assert result.warnings is None
    assert result.error is None
    assert result.reason is None
    assert result.meta is None


def test_result_success_with_warnings():
    result = MeasurementResult.ok_payload("spx", [1], ["slow response", "rate limited"])

    assert result.ok is True
    assert result.series_name == "spx"
    assert result.payload == [1]
    assert result.warnings == ["slow response", "rate limited"]
    assert result.error is None
    assert result.reason is None
    assert result.meta is None


def test_result_success_with_empty_warnings():
    result = MeasurementResult.ok_payload("spx", payload=[1], warnings=[])

    assert result.ok is True
    assert result.series_name == "spx"
    assert result.payload == [1]
    assert result.warnings is None
    assert result.error is None
    assert result.reason is None


def test_result_error_reason_only():
    result = MeasurementResult.fail("spx", "timeout")

    assert result.ok is False
    assert result.series_name == "spx"
    assert result.payload is None
    assert result.reason == "timeout"
    assert result.warnings is None
    assert result.error is None


def test_result_error_with_exception_and_meta():
    exc = ValueError("boom")
    result = MeasurementResult.fail("spx", "bad data", exc, meta={"other": 1})

    assert result.ok is False
    assert result.payload is None
    assert result.reason == "bad data"
    assert result.warnings is None
    assert isinstance(result.error, str)
    assert "boom" in result.error
    assert result.meta == {"other": 1}


def test_result_with_meta():
    result = Result.ok_payload(1).with_meta({"test": "ok"})
    assert result.meta == {"test": "ok"}
    assert result.payload == 1


def test_provider_config_defaults():
    config = ProviderConfig.create({"name": "x", "timezone": "UTC"})
    assert config.name == "x"
    assert config.timezone == "UTC"
    assert config.timeout == "10s"
    assert config.history_limits == {}
    assert config.timeout_delta() == timedelta(seconds=10)


def test_provider_config_history_limits():
    config = ProviderConfig.create(
        {
            "name": "x",
            "timezone": "UTC",
            "timeout": "20s",
            "constraints": {"history_limits": {"default": "5d", "1h": "60d", "1d": None}},
        }
    )
    assert config.name == "x"
    assert config.timezone == "UTC"
    assert config.timeout == "20s"
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


def test_provider_config_empty_history_limits():
    config = ProviderConfig.create(
        {
            "name": "x",
        }
    )
    assert config.name == "x"
    assert config.history_limits == {}

    assert config.get_history_limit(timedelta(minutes=0)) is None
    assert config.get_history_limit(timedelta(weeks=1)) is None


def test_series_state(fixed_now):

    state = SeriesState(first_time=fixed_now(), last_time=fixed_now())
    state_dict = state.to_dict()
    assert state_dict["last_try"] is None
    assert state_dict["first_time"] == "2025-06-15T15:06:40+00:00"
    assert state_dict["last_time"] == "2025-06-15T15:06:40+00:00"
    state_roundtrip = SeriesState.from_dict(state_dict)
    assert state == state_roundtrip
