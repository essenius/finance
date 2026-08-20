# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fetch.py

import json
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import Mock, patch

import pytest

from finance.common.candle_identity import CandleIdentity
from finance.common.model import AssetMetadata, SeriesPoint
from finance.common.string_enums import Retention, SeriesType
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
        result = provider._fetch_impl("http://x", "m", {})

    payload = unwrap(result)
    assert payload == {"foo": "bar"}


def test_fetch_impl_missing_chart(yahoo_provider, assert_error):
    provider = yahoo_provider()

    response = Mock()
    response.json.return_value = {}
    response.raise_for_status.return_value = None

    with patch.object(provider.session, "get", return_value=response):
        result = provider._fetch_impl("http://x", "m", {})

    assert_error(result, "Could not interpret fetch response", "no 'chart' in response")


def test_fetch_impl_empty_result(yahoo_provider, assert_error):
    provider = yahoo_provider()
    response = Mock()
    response.json.return_value = {"chart": {"result": []}}
    response.raise_for_status.return_value = None

    with patch.object(provider.session, "get", return_value=response):
        result = provider._fetch_impl("http://x", "m", {})

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
        result = provider._fetch_impl("http://x", "m", {})

    assert_error(
        result, "Could not interpret fetch response", "{'code': 'BadSymbol', 'description': 'Symbol not found'}"
    )


# ----------------------------------------------------------------------
# fetch()
# ----------------------------------------------------------------------


def make_identity(label: datetime):
    return CandleIdentity(label, False, timedelta(0))


def test_fetch_success(yahoo_provider, unwrap, make_asset, make_series):

    def fake_now():
        return datetime(2026, 7, 23, 15, 00, tzinfo=UTC)

    response = Mock()
    now = make_identity(fake_now())
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "meta": {"exchangeTimezoneName": "UTC"},
                    "timestamp": [now.start_timestamp()],
                    "indicators": {"quote": [{"close": [10.0]}]},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None
    asset = make_asset(provider_code="AAPL")
    series = make_series(asset, interval="1h", retention=Retention.SHORT_LIVED, series_type=SeriesType.VALUE)
    provider: YahooProvider = yahoo_provider(now_provider=fake_now)
    with patch.object(provider.session, "get", return_value=response):
        result = provider.fetch(series, asset, now, now, False)

    payload = unwrap(result)
    points = payload.points
    assert len(points) == 1, "one result"
    assert points[0].time == datetime(2026, 7, 23, 15, 00, tzinfo=UTC), "datetime is instant"
    assert points[0].close == 10.0, "Close is 10"


def test_impl_http_error(yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    now = make_identity(fixed_now())
    response = Mock()
    response.raise_for_status.side_effect = Exception("boom")
    asset = make_asset()
    series = make_series(asset)
    provider = yahoo_provider()
    with patch.object(provider.session, "get", return_value=response):
        result = provider.fetch(series, asset, now, now, False)

    assert_error(result, "Exception during Yahoo fetch", "boom")


@pytest.mark.parametrize(
    ("meta", "reason"),
    [
        ({}, "missing exchangeTimezoneName in meta"),
        ({"exchangeTimezoneName": "Not/A_Timezone"}, "invalid exchange timezone 'Not/A_Timezone'"),
    ],
)


def test_fetch_missing_exchange_timezone(
    yahoo_provider, assert_error, make_asset, make_series, fixed_now, meta, reason
):
    now = make_identity(fixed_now())
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "meta": meta,
                    "timestamp": [now.start_timestamp()],
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
        result = provider.fetch(series, asset, now, now, False)

    assert_error(result, "Could not parse series 'AAPL:dummy' in Yahoo fetch result", reason)


def test_fetch_missing_quote(
    yahoo_provider, assert_error, make_asset, make_series, fixed_now):
    now = make_identity(fixed_now())
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "meta": {"exchangeTimezoneName": "UTC"},
                    "timestamp": [now.start_timestamp()],
                    "indicators": {},
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
        result = provider.fetch(series, asset, now, now, False)

    assert_error(result, "Could not parse series 'AAPL:dummy' in Yahoo fetch result", "missing key 'quote' at ['indicators']")
def test_fetch_real_fixture_5m_eliminates_last_and_fills_metadata(yahoo_provider, unwrap, make_asset, make_series):
    with open("tests/data/yahoo_gold_intraday.json") as f:
        fake_json = json.load(f)

    # This is the time that data stored in the test file was fetched. Note that yahoo chart is 10-15 mins delayed.
    # The timestamp of the last candle is 11:47:55 UTC
    provider: YahooProvider = yahoo_provider(now_provider=lambda: datetime(2026, 8, 11, 12, tzinfo=UTC))
    provider.session.queue(200, fake_json)

    asset = make_asset(provider_code="gold")
    series = make_series(asset, interval="5m")
    start = make_identity(datetime(2026, 8, 11, 10, 30, tzinfo=UTC))
    end = make_identity(datetime(2026, 8, 11, 12, tzinfo=UTC))
    result = provider.fetch(series, asset, start=start, end=end, is_incremental=False)
    fetch_result = unwrap(result)
    points = fetch_result.points
    assert len(points) == 16, "last point eliminated (not aligned)"
    last_point: SeriesPoint = points[-1]
    assert last_point.time == datetime(2026, 8, 11, 11, 45, tzinfo=UTC)

    metadata: AssetMetadata = fetch_result.metadata
    assert metadata.short_name == "Gold Dec 26"
    assert metadata.long_name is None
    assert metadata.instrument == "FUTURE"
    assert metadata.region is None
    assert metadata.exchange == "CMX"
    assert metadata.currency == "USD"
    assert metadata.unit is None
    assert metadata.first_trade_date == date(year=2000, month=8, day=30)
    assert metadata.timezone.key == "America/New_York"
    assert metadata.market_open == time(hour=0)
    assert metadata.market_close == time(hour=23, minute=59)
    assert metadata.week_start is None
    assert metadata.week_end is None
