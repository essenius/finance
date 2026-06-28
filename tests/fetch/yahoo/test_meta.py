# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_meta.py


from datetime import timedelta

from finance.common.model import DAILY, CandlePoint, DailyValuePoint, SeriesType


def test_get_from_meta_full_success(yahoo_provider, unwrap, make_asset, make_series, fixed_now):
    now = fixed_now()
    min = now - timedelta(seconds=100)
    max = now + timedelta(seconds=100)
    meta = {
        "regularMarketTime": int(now.timestamp()),
        "regularMarketPrice": 10.0,
        "regularMarketDayHigh": 12.0,
        "regularMarketDayLow": 8.0,
        "regularMarketVolume": 999,
    }

    asset = make_asset()
    series = make_series(asset, resolution=DAILY, series_type=SeriesType.CANDLE)
    result = yahoo_provider._get_from_meta(series, meta, min, max)
    payload = unwrap(result)

    assert len(payload) == 1
    assert isinstance(payload[0], CandlePoint)
    assert payload[0] == CandlePoint(
        series_id=series.id, time=now, open=None, high=12.0, low=8.0, close=10.0, volume=999
    )


def test_get_from_meta_partial_success(yahoo_provider, unwrap, make_asset, make_series, fixed_now):
    now = fixed_now()
    now_timestamp = int(now.timestamp())
    meta = {
        "regularMarketTime": now_timestamp,
        "regularMarketPrice": 10.0,
        "regularMarketDayHigh": None,
        "regularMarketDayLow": 8.0,
        "regularMarketVolume": None,
    }

    asset = make_asset()
    series = make_series(asset, resolution=DAILY, series_type=SeriesType.CANDLE)

    result = yahoo_provider._get_from_meta(series, meta, now, now)
    payload = unwrap(result)

    assert len(payload) == 1
    assert payload[0] == CandlePoint(
        series_id=series.id, time=now, open=None, high=None, low=8.0, close=10.0, volume=None
    )
    assert result.warnings == ["Missing value for 'high'", "Missing value for 'volume'"]


def test_get_from_meta_all_missing(yahoo_provider, assert_error, make_asset, make_series, fixed_now):

    now = fixed_now()
    now_timestamp = int(now.timestamp())

    meta = {
        "regularMarketTime": now_timestamp,
        "regularMarketPrice": None,
        "regularMarketDayHigh": None,
        "regularMarketDayLow": None,
        "regularMarketVolume": None,
    }

    asset = make_asset()
    series = make_series(asset, resolution=DAILY, series_type=SeriesType.CANDLE)

    result = yahoo_provider._get_from_meta(series, meta, now, now)
    assert_error(result, "Cannot synthesize from metadata", "No fields synthesized")


def test_get_from_meta_no_timestamp(yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    meta = {"regularMarketPrice": 10.0}
    now = fixed_now()
    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.VALUE)
    result = yahoo_provider._get_from_meta(series, meta, now, now)
    assert_error(result, "Cannot synthesize from metadata", "timestamp missing")


def test_get_from_meta_timestamp_outside_range(yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    now = fixed_now()
    retrieved = now - timedelta(seconds=100)
    meta = {"regularMarketTime": int(retrieved.timestamp()), "regularMarketPrice": 10.0}
    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.VALUE)
    result = yahoo_provider._get_from_meta(series, meta, now, now)
    assert_error(result, "Cannot synthesize from metadata", "metadata timestamp outside requested range")


def test_get_from_meta_daily_value(yahoo_provider, unwrap, make_asset, make_series, fixed_now):
    now = fixed_now()
    now_timestamp = int(now.timestamp())
    meta = {"regularMarketTime": now_timestamp, "regularMarketPrice": 42.0}
    asset = make_asset()
    series = make_series(asset, resolution=DAILY, series_type=SeriesType.VALUE)
    result = yahoo_provider._get_from_meta(series, meta, now, now)
    payload = unwrap(result)
    assert isinstance(payload[0], DailyValuePoint)
    assert payload[0] == DailyValuePoint(series_id=series.id, time=now, value=42.0)
