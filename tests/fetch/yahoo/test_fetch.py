# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fetch.py

import json
from datetime import UTC, date, datetime
from unittest.mock import Mock, patch

from finance.common.model import Retention, SeriesPoint, SeriesType
from finance.fetch.yahoo import YahooProvider

# ----------------------------------------------------------------------
# _fetch_impl()
# ----------------------------------------------------------------------


def test_fetch_impl_success(yahoo_provider, unwrap):
    provider = yahoo_provider()
    response = Mock()
    response.json.return_value = {"chart": {"result": [{"foo": "bar"}], "error": None}}
    response.raise_for_status.return_value = None

    with patch.object(provider.session, "get", return_value=response):
        result = provider._fetch_impl("http://x", "m")

    payload = unwrap(result)
    assert payload == {"foo": "bar"}


def test_fetch_impl_missing_chart(yahoo_provider, assert_error):
    provider = yahoo_provider()

    response = Mock()
    response.json.return_value = {}
    response.raise_for_status.return_value = None

    with patch.object(provider.session, "get", return_value=response):
        result = provider._fetch_impl("http://x", "m")

    assert_error(result, "Could not interpret fetch response", "no 'chart' in response")


def test_fetch_impl_empty_result(yahoo_provider, assert_error):
    provider = yahoo_provider()
    response = Mock()
    response.json.return_value = {"chart": {"result": []}}
    response.raise_for_status.return_value = None

    with patch.object(provider.session, "get", return_value=response):
        result = provider._fetch_impl("http://x", "m")

    assert_error(result, "Could not interpret fetch response", "result empty")


def test_fetch_impl_yahoo_error_object(yahoo_provider, assert_error):
    provider = yahoo_provider()
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [{"foo": "bar"}],
            "error": {"code": "BadSymbol", "description": "Symbol not found"},
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(provider.session, "get", return_value=response):
        result = provider._fetch_impl("http://x", "m")

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
                    "meta": {"exchangeTimezoneName": "UTC"},
                    "timestamp": [now.timestamp()],
                    "indicators": {"quote": [{"close": [10.0]}]},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None
    asset = make_asset(provider_code="AAPL")
    series = make_series(asset, interval="1h", retention=Retention.SHORT_LIVED, series_type=SeriesType.VALUE)
    provider = yahoo_provider()
    with patch.object(provider.session, "get", return_value=response):
        result = provider.fetch(series, asset, now, now)

    payload = unwrap(result)
    assert len(payload) == 1, "one result"
    assert payload[0].time == datetime(2025, 6, 15, 15, 6, 40, tzinfo=UTC), "datetime is instant"
    assert payload[0].close == 10.0, "Close is 10"


def test_impl_http_error(yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    now = fixed_now()
    response = Mock()
    response.raise_for_status.side_effect = Exception("boom")
    asset = make_asset()
    series = make_series(asset)
    provider = yahoo_provider()
    with patch.object(provider.session, "get", return_value=response):
        result = provider.fetch(series, asset, now, now)

    assert_error(result, "Exception during Yahoo fetch", "boom")


def test_fetch_missing_exchange_timezone(yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    now = fixed_now()
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "meta": {},
                    "timestamp": [now.timestamp()],
                    "indicators": {"quote": [{"close": [10.0]}]},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None
    asset = make_asset(name="AAPL")
    series = make_series(asset, interval="1h", retention=Retention.SHORT_LIVED, series_type=SeriesType.VALUE)
    provider = yahoo_provider()
    with patch.object(provider.session, "get", return_value=response):
        result = provider.fetch(series, asset, now, now)

    assert_error(
        result, "Could not parse series 'AAPL:dummy' in Yahoo fetch result", "missing exchangeTimeZoneName in meta"
    )


"""
TODO delete
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
"""


def test_fetch_real_fixture_1d_eliminates_today(yahoo_provider, unwrap, make_asset, make_series):
    with open("tests/data/yahoo_gold_5d.json") as f:
        fake_json = json.load(f)

    # now is the last day of the data, which should be eliminated as the day is not complete
    provider: YahooProvider = yahoo_provider(now_provider=lambda: datetime(2026, 5, 22, 15, 6, 40, tzinfo=UTC))
    provider.session.queue(200, fake_json)

    asset = make_asset(provider_code="gold")
    series = make_series(asset, interval="1d")
    start_time = datetime(2026, 5, 19, tzinfo=UTC)
    end_time = datetime(2026, 5, 22, 23, 59, 59, tzinfo=UTC)
    result = provider.fetch(series, asset, start_time=start_time, end_time=end_time)
    points = unwrap(result)
    assert len(points) == 3, "last day eliminated (today)"
    last_point: SeriesPoint = points[-1]
    assert last_point.time.date() == date(2026, 5, 21)
