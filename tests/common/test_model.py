# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_model.py

from datetime import datetime, timedelta

import pytest

from finance.common.configuration import ProviderConfig
from finance.common.model import Asset, AssetMetadata, Series, SeriesPoint, SeriesState, SweepConfig
from finance.common.string_enums import Retention, SeriesType


def test_seriespoint_from_to_dict(fixed_now):
    now = fixed_now()
    # omitted volume on purpose
    point = SeriesPoint(1, now, open=10, high=14, low=8, close=12)
    dict1 = point.to_dict()
    result1 = SeriesPoint.from_dict(dict1)
    assert result1 == point
    assert f"{result1}" == "SeriesPoint(id=1, time=2025-06-15T15:06:40+00:00, open=10, high=14, low=8, close=12)"


def test_asset_create_with_id_differs():
    config = {"symbol": "SPX", "provider": {"name": "yahoo", "code": "^SPX"}, "short_name": "spx"}
    asset = Asset.from_config(name="spx", config=config)
    assert asset.id is None
    assert asset.name == "spx"
    assert asset.symbol == "SPX"
    assert asset.provider == "yahoo"
    assert asset.provider_code == "^SPX"

    meta = AssetMetadata(
        long_name=None,
        short_name="spx",
        instrument=None,
        exchange=None,
        region=None,
        currency=None,
        unit=None,
        timezone=None,
        first_trade_date=None,
        week_start=None,
        week_end=None,
        market_open=None,
        market_close=None,
    )
    assert asset.config_metadata == meta

    assert f"{asset}" == "Asset(id=None, name=spx, symbol=SPX, provider_code=^SPX, metadata=None)"

    asset.effective_metadata = asset.config_metadata

    assert (
        f"{asset}"
        == "Asset(id=None, name=spx, symbol=SPX, provider_code=^SPX, metadata=AssetMetadata(short=spx, currency=None, timezone=None))"
    )

    asset2 = asset.with_id(1)
    assert asset2.id == 1
    assert asset2.name == "spx"

    # differs from only looks at metadata, not at id, name
    assert not asset.differs_from(asset2)

    config |= {"region": "Europe"}
    asset3 = Asset.from_config(name="spx", config=config)
    assert asset.differs_from(asset3)


def test_asset_create_with_wrong_timezone():

    config = {"symbol": "SPX", "provider": {"name": "yahoo", "code": "^SPX"}, "timezone": "bogus"}
    with pytest.raises(ValueError) as ve:
        Asset.from_config(name="spx", config=config)
    assert "Cannot understand timezone 'bogus'" in str(ve.value)


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
    assert series.is_daily()
    assert series.interval_delta() == timedelta(days=1)
    assert series.retention_delta() is None
    assert series.bootstrap_history == "10y"
    assert series.bootstrap_history_delta() == timedelta(days=3652.5)
    assert series.publication_offset is None

    series2 = series.with_id(10)
    assert (
        f"{series2}"
        == "Series(id=10, name=spx:dummy, asset_id=3, retention=long_lived, series_type=candle, interval=1d)"
    )

    # differs from only looks at metadata, not at id, name
    assert not series.differs_from(series2)

    config |= {"bootstrap_history": "5y", "publication_offset": "16h"}
    series3 = Series.create(asset, code="dummy", config=config)
    assert series.differs_from(series3)
    assert series3.bootstrap_history == "5y"
    assert series3.publication_offset == "16h"


def test_series_create_with_defaults_daily(make_asset):
    asset = make_asset(name="spx", id=3)
    config = {
        "symbol": "SPX",
        "interval": "1d",
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
    assert series.is_daily()
    assert series.interval_delta() == timedelta(days=1)
    assert series.retention_delta() is None
    assert series.bootstrap_history == "10y"
    assert series.bootstrap_history_delta() == timedelta(days=3652.5)
    assert series.publication_offset is None


def test_provider_config_defaults():
    config = ProviderConfig.create({"name": "x"})
    assert config.name == "x"
    assert config.timeout == "10s"
    assert config.history_limits == {}
    assert config.timeout_delta() == timedelta(seconds=10)


def test_provider_config_history_limits_and_overlap():
    config = ProviderConfig.create(
        {
            "name": "x",
            "timeout": "20s",
            "constraints": {"history_limits": {"default": "5d", "1h": "60d", "1d": None}},
            "sweep": {"default": {"window": "2h", "cadence": "30m"}, "1d": {"window": "7d", "cadence": "1d"}},
        }
    )
    assert config.name == "x"
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

    intraday_sweep = SweepConfig(timedelta(hours=2), timedelta(minutes=30))
    daily_sweep = SweepConfig(timedelta(days=7), timedelta(days=1))
    assert config.sweep == {timedelta(0): intraday_sweep, timedelta(days=1): daily_sweep}
    assert config.get_sweep(timedelta(hours=8)) == intraday_sweep
    assert config.get_sweep(timedelta(days=1)) == daily_sweep


def test_provider_config_empty_history_limits_and_overlaps():
    config = ProviderConfig.create(
        {
            "name": "x",
        }
    )
    assert config.name == "x"
    assert config.history_limits == {}

    assert config.get_history_limit(timedelta(minutes=0)) is None
    assert config.get_history_limit(timedelta(weeks=1)) is None
    assert config.get_sweep(timedelta(weeks=1)) == SweepConfig(window=timedelta(0), cadence=timedelta(0))


def test_update_point_range():
    state = SeriesState()
    first = datetime.min
    current = first + timedelta(days=10)
    state.update_point_range(first=first, last=current)
    assert state.first_point, state.last_point == (first, current)
    overlap = current - timedelta(days=1)
    state.update_point_range(first=overlap, last=current)
    assert state.first_point, state.last_point == (first, current)
