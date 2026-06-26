# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_model_result.py

import pytest

from finance.common.model import (
    Asset,
    Candle,
    CandlePoint,
    DailyValuePoint,
    IntradayPoint,
    MeasurementResult,
    Resolution,
    Series,
    SeriesPoint,
    SeriesType,
)


def test_stringenum_validate():
    with pytest.raises(ValueError) as exc_info:
        Resolution.validate("bogus")
        assert "Invalid Resolution: 'bogus'. Allowed: intraday, daily" in exc_info


def test_stringenum_contains():
    assert Candle.contains("close")
    assert not Candle.contains("value")


def test_stringenum_values():
    assert SeriesType.values() == ["candle", "value"]


def test_candle_ordered():
    assert Candle.ordered() == ["open", "high", "low", "close", "volume"]


def test_seriespoint_fields():
    assert DailyValuePoint.fields() == ["close"]
    assert IntradayPoint.fields() == ["close"]
    assert CandlePoint.fields() == ["open", "high", "low", "close", "volume"]


def test_seriespoint_map():
    raw_fields = {"open": 10, "high": 15, "low": 9, "close": 13, "volume": 100}
    assert DailyValuePoint.map(raw_fields) == {"value": 13}
    assert IntradayPoint.map(raw_fields) == {"value": 13}
    assert CandlePoint.map(raw_fields) == raw_fields


def test_seriespoint_factory(make_series):
    series1 = make_series(asset=None, resolution=Resolution.INTRADAY)
    intraday_factory = SeriesPoint.factory(series1)
    assert intraday_factory.func is IntradayPoint

    series2 = make_series(asset=None, resolution=Resolution.DAILY, series_type=SeriesType.CANDLE)
    candle_factory = SeriesPoint.factory(series2)
    assert candle_factory.func is CandlePoint

    series3 = make_series(asset=None, resolution=Resolution.DAILY, series_type=SeriesType.VALUE)
    daily_factory = SeriesPoint.factory(series3)
    assert daily_factory.func is DailyValuePoint


def test_seriespoint_from_to_dict():
    intraday_point = IntradayPoint(1, 2, 3)
    dict1 = intraday_point.to_dict()
    result1 = SeriesPoint.from_dict(dict1)
    assert isinstance(result1, IntradayPoint), "intraday"
    assert result1 == intraday_point

    daily_value_point = DailyValuePoint(4, 5, 6)
    dict2 = daily_value_point.to_dict()
    result2 = SeriesPoint.from_dict(dict2)
    assert isinstance(result2, DailyValuePoint), "daily"
    assert result2 == daily_value_point

    candle_point = CandlePoint(1, 2, open=10, high=14, low=8, close=12, volume=100)
    dict3 = candle_point.to_dict()
    result3 = SeriesPoint.from_dict(dict3)
    assert isinstance(result3, CandlePoint), "candle"
    assert result3 == candle_point

    dict4 = {"type": "bogus"}
    with pytest.raises(ValueError) as exc_info:
        SeriesPoint.from_dict(dict4)
        assert "Unknown point type: bogus" in exc_info


def test_asset_create_with_id_differs():
    config = {"provider": "yahoo", "provider_code": "^SPX"}
    tags = {"instrument": "forex"}
    asset = Asset.create(name="spx", symbol="SPX", config=config, tags=tags)
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

    asset2 = asset.with_id(1)
    assert asset2.id == 1
    assert asset2.name == "spx"

    # differs from only looks at metadata, not at id, name
    assert not asset.differs_from(asset2)

    tags = tags | {"region": "Europe"}
    asset3 = Asset.create(name="spx", symbol="SPX", config=config, tags=tags)
    assert asset.differs_from(asset3)


def test_series_create_with_id_differs(make_asset):
    asset = make_asset(name="spx", symbol="SPX", id=3)
    config = {"daily_series_type": "candle", "interval": "1d", "daily_history_limit": "10y"}
    series = Series.create(asset=asset, resolution="daily", config=config)
    assert series.id is None
    assert series.name == "spx_daily"
    assert series.symbol == "SPX"
    assert series.asset_id == 3
    assert series.resolution == Resolution.DAILY
    assert series.series_type == SeriesType.CANDLE
    assert series.interval == "1d"
    assert series.interval_seconds == 86400
    assert series.history_limit == "10y"
    assert series.history_limit_seconds == 315576000

    series2 = series.with_id(10)
    assert series2.id == 10
    assert series2.name == "spx_daily"

    # differs from only looks at metadata, not at id, name
    assert not series.differs_from(series2)

    config = config | {"history_limit": "5y"}
    series3 = Series.create(asset, resolution="daily", config=config)
    assert series.differs_from(series3)
    assert series3.history_limit == "5y"

    series4 = Series.create(asset, resolution="intraday")
    assert series4.name == "spx_intraday"
    assert series4.series_type == SeriesType.VALUE

    series5 = Series.create(asset, resolution="intraday", config=config)
    assert series5.name == "spx_intraday"
    assert series5.series_type == SeriesType.VALUE


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
