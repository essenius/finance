# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fetch.py

import json
from datetime import date, datetime, time, timedelta

import pytest

from finance.common.asset_metadata import AssetMetadata
from finance.common.candle_identity import CandleIdentity
from finance.common.json_utils import JsonObject
from finance.common.model import Asset, FetchData, Series, SeriesPoint
from finance.common.string_enums import Retention, SeriesType
from finance.common.time_utils import UTC
from finance.common.types import Unwrap
from tests.fetch.yahoo.test_candles import YahooFakeSession
from tests.support.types import AssertError, Creator, Factory

# ----------------------------------------------------------------------
# _fetch_impl()
# ----------------------------------------------------------------------


def test_fetch_impl_success(unwrap: Unwrap[JsonObject], yahoo_provider: Factory[YahooFakeSession]):
    fake = yahoo_provider()
    fake.session.queue(200, {"chart": {"result": [{"foo": "bar"}], "error": None}})
    result = fake.provider._fetch_impl(url="http://x", params={})
    payload = unwrap(result)
    assert payload == {"foo": "bar"}


def test_fetch_impl_missing_chart(assert_error: AssertError, yahoo_provider: Factory[YahooFakeSession]):
    fake = yahoo_provider()
    fake.session.queue(200, {})

    result = fake.provider._fetch_impl(url="http://x", params={})

    assert_error(result, "Could not interpret fetch response", "no 'chart' in response")


def test_fetch_impl_empty_result(assert_error: AssertError, yahoo_provider: Factory[YahooFakeSession]):
    fake = yahoo_provider()
    fake.session.queue(200, {"chart": {"result": []}})
    result = fake.provider._fetch_impl(url="http://x", params={})
    assert_error(result, "Could not interpret fetch response", "['result', 0]: index `0` out of range (level: 1)")


def test_fetch_impl_yahoo_error_object(assert_error: AssertError, yahoo_provider: Factory[YahooFakeSession]):
    fake = yahoo_provider()
    fake.session.queue(
        200,
        {
            "chart": {
                "result": [{"foo": "bar"}],
                "error": {"code": "BadSymbol", "description": "Symbol not found"},
            }
        },
    )

    result = fake.provider._fetch_impl(url="http://x", params={})

    assert_error(
        result, "Could not interpret fetch response", "{'code': 'BadSymbol', 'description': 'Symbol not found'}"
    )


# ----------------------------------------------------------------------
# fetch()
# ----------------------------------------------------------------------


def make_identity(label: datetime):
    return CandleIdentity(label, False, timedelta(0))


def test_fetch_success(
    make_asset: Creator[Asset],
    make_series: Creator[Series],
    unwrap: Unwrap[FetchData],
    yahoo_provider: Creator[YahooFakeSession],
):

    def fake_now():
        return datetime(2026, 7, 23, 15, 00, tzinfo=UTC)

    fake = yahoo_provider(now_provider=fake_now)

    now = make_identity(fake_now())
    fake.session.queue(
        200,
        {
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
        },
    )
    asset = make_asset(provider_code="AAPL")
    series = make_series(
        asset, interval="1h", retention=Retention.SHORT_LIVED.value, series_type=SeriesType.VALUE.value
    )

    result = fake.provider.fetch(series, asset, now, now, False)

    payload = unwrap(result)
    points = payload.points
    assert len(points) == 1, "one result"
    assert points[0].time == datetime(2026, 7, 23, 15, 00, tzinfo=UTC), "datetime is instant"
    assert points[0].close == 10.0, "Close is 10"


def test_impl_http_error(
    assert_error: AssertError,
    fixed_now: Factory[datetime],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
    yahoo_provider: Factory[YahooFakeSession],
):
    now = make_identity(fixed_now())
    asset = make_asset()
    series = make_series(asset)
    fake = yahoo_provider()
    fake.session.queue_error(Exception("boom"))

    result = fake.provider.fetch(series, asset, now, now, False)

    assert_error(result, "Exception during Yahoo fetch", "boom")


@pytest.mark.parametrize(
    ("meta", "reason"),
    [
        ({}, "missing exchangeTimezoneName in meta"),
        ({"exchangeTimezoneName": "Not/A_Timezone"}, "invalid exchange timezone 'Not/A_Timezone'"),
    ],
)
def test_fetch_missing_exchange_timezone(
    assert_error: AssertError,
    fixed_now: Factory[datetime],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
    yahoo_provider: Factory[YahooFakeSession],
    meta: dict,
    reason: str,
):
    fake = yahoo_provider()
    now = make_identity(fixed_now())
    fake.session.queue(
        200,
        {
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
        },
    )
    asset = make_asset(name="AAPL")
    series = make_series(
        asset, interval="1h", retention=Retention.SHORT_LIVED.value, series_type=SeriesType.VALUE.value
    )
    result = fake.provider.fetch(series, asset, now, now, False)

    assert_error(result, "Could not parse series 'AAPL:dummy' in Yahoo fetch result", reason)


def test_fetch_missing_quote(
    assert_error: AssertError,
    fixed_now: Factory[datetime],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
    yahoo_provider: Factory[YahooFakeSession],
):
    now = make_identity(fixed_now())
    fake = yahoo_provider()
    fake.session.queue(
        200,
        {
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
        },
    )
    asset = make_asset(name="AAPL")
    series = make_series(
        asset, interval="1h", retention=Retention.SHORT_LIVED.value, series_type=SeriesType.VALUE.value
    )
    result = fake.provider.fetch(series, asset, now, now, False)

    assert_error(
        result,
        "Could not parse series 'AAPL:dummy' in Yahoo fetch result",
        "['indicators', 'quote', 0]: Missing required key `quote` (level: 1)",
    )


def test_fetch_real_fixture_5m_eliminates_last_and_fills_metadata(
    make_asset: Creator[Asset],
    make_series: Creator[Series],
    unwrap: Unwrap[FetchData],
    yahoo_provider: Creator[YahooFakeSession],
):
    with open("tests/data/yahoo_gold_intraday.json") as f:
        fake_json = json.load(f)

    # This is the time that data stored in the test file was fetched. Note that yahoo chart is 10-15 mins delayed.
    # The timestamp of the last candle is 11:47:55 UTC
    fake = yahoo_provider(now_provider=lambda: datetime(2026, 8, 11, 12, tzinfo=UTC))
    fake.session.queue(200, fake_json)

    asset = make_asset(provider_code="gold")
    series = make_series(asset, interval="5m")
    start = make_identity(datetime(2026, 8, 11, 10, 30, tzinfo=UTC))
    end = make_identity(datetime(2026, 8, 11, 12, tzinfo=UTC))

    result = fake.provider.fetch(series, asset, start=start, end=end, is_incremental=False)

    fetch_result = unwrap(result)
    points = fetch_result.points
    assert len(points) == 16, "last point eliminated (not aligned)"
    last_point: SeriesPoint = points[-1]
    assert last_point.time == datetime(2026, 8, 11, 11, 45, tzinfo=UTC)
    assert fetch_result.metadata is not None
    metadata: AssetMetadata = fetch_result.metadata
    assert metadata.short_name == "Gold Dec 26"
    assert metadata.long_name is None
    assert metadata.instrument == "FUTURE"
    assert metadata.region is None
    assert metadata.exchange == "CMX"
    assert metadata.currency == "USD"
    assert metadata.unit is None
    assert metadata.first_available_date == date(year=2000, month=8, day=30)
    assert metadata.timezone is not None
    assert metadata.timezone.key == "America/New_York"
    assert metadata.market_open == time(hour=0)
    assert metadata.market_close == time(hour=23, minute=59)
    assert metadata.week_start is None
    assert metadata.week_end is None
