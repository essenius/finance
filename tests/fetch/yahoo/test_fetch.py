# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fetch.py

from unittest.mock import Mock, patch

from finance.common.model import DAILY, CandlePoint, DailyValuePoint, SeriesType

# ----------------------------------------------------------------------
# _fetch_impl()
# ----------------------------------------------------------------------


def test_fetch_impl_success(yahoo_provider, unwrap):
    response = Mock()
    response.json.return_value = {"chart": {"result": [{"foo": "bar"}], "error": None}}
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    payload = unwrap(result)
    assert payload == {"foo": "bar"}


def test_fetch_impl_missing_chart(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {}
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    assert_error(result, "Could not interpret fetch response", "no 'chart' in response")


def test_fetch_impl_empty_result(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {"chart": {"result": []}}
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    assert_error(result, "Could not interpret fetch response", "result empty")


def test_fetch_impl_yahoo_error_object(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [{"foo": "bar"}],
            "error": {"code": "BadSymbol", "description": "Symbol not found"},
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    assert_error(
        result, "Could not interpret fetch response", "{'code': 'BadSymbol', 'description': 'Symbol not found'}"
    )


# ----------------------------------------------------------------------
# fetch()
# ----------------------------------------------------------------------


def test_fetch_success(yahoo_provider, unwrap, make_asset, make_series, fixed_now):
    response = Mock()
    now = fixed_now()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "timestamp": [now.timestamp()],
                    "indicators": {"quote": [{"close": [10.0]}]},
                    "meta": {},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None
    asset = make_asset(provider_code="AAPL")
    series = make_series(asset, interval="1d", resolution=DAILY, series_type=SeriesType.VALUE)
    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider.fetch(series, asset, now, now)

    payload = unwrap(result)
    assert isinstance(payload[0], DailyValuePoint), "result is DailyValuePoint"
    assert len(payload) == 1, "one result"
    assert payload[0].value == 10.0, "Value is 10"


def test_impl_http_error(yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    now = fixed_now()
    response = Mock()
    response.raise_for_status.side_effect = Exception("boom")
    asset = make_asset()
    series = make_series(asset)
    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider.fetch(series, asset, now, now)

    assert_error(result, "Exception during Yahoo fetch", "boom")


def test_fetch_fallback_to_meta(yahoo_provider, unwrap, make_asset, make_series, fixed_now):
    now = fixed_now()
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "timestamp": [],
                    "indicators": {"quote": [{}]},
                    "meta": {"regularMarketTime": now.timestamp(), "regularMarketPrice": 42.0},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        asset = make_asset(provider_code="AAPL")
        series = make_series(asset, interval="1d", resolution=DAILY, series_type=SeriesType.CANDLE)
        result = yahoo_provider.fetch(series, asset, now, now)

    payload = unwrap(result)
    assert len(payload) == 1
    assert isinstance(payload[0], CandlePoint)
    assert payload[0].close == 42.0
    assert result.warnings == ["Missing value for 'high'", "Missing value for 'low'", "Missing value for 'volume'"]


def test_fetch_propagates_extract_candles_error(yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "timestamp": None,
                    "indicators": {"quote": [{}]},
                    "meta": {},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None
    now = fixed_now()
    with patch.object(yahoo_provider.session, "get", return_value=response):
        asset = make_asset(provider_code="AAPL")
        series = make_series(asset, interval="1d", resolution=DAILY, series_type=SeriesType.VALUE)
        result = yahoo_provider.fetch(series, asset, now, now)

    assert_error(result, "Cannot synthesize from metadata", "timestamp missing")
