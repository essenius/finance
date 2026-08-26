# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_ecb.py

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from finance.common.candle_identity import CandleIdentity
from finance.common.time_utils import UTC
from finance.fetch.ecb import EcbProvider
from tests.support.fakes import fake_session


def make_identity(label: datetime) -> CandleIdentity:
    return CandleIdentity(label, is_daily=True, interval=timedelta(days=1))



def test_ecb_fetch_real_fixture(ecb_provider, assert_ok, make_asset, make_series):
    with open("tests/data/ecb_eurusd.json") as f:
        fake_json = json.load(f)

    provider:EcbProvider = ecb_provider()
    fake_session(provider).queue(200, fake_json)

    asset = make_asset(provider_code="USD_EUR")
    series = make_series(asset)
    start = make_identity(datetime(2026, 5, 8, tzinfo=ZoneInfo("Europe/Berlin")))
    end = make_identity(datetime(2026, 5, 8, 23, 59, 59, tzinfo=ZoneInfo("Europe/Berlin")))
    result = provider.fetch(series, asset, start=start, end=end, is_incremental=False)
    session = fake_session(provider)
    assert session.url == "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    assert session.params == {
        "format": "jsondata",
        "startPeriod": "2026-05-08",
        "endPeriod": "2026-05-08",
        "detail": "dataonly",
    }

    assert_ok(result, time=datetime(2026, 5, 8, 0, 0, 0, tzinfo=UTC), close=1.1761)


def test_ecb_fetch_ok(ecb_provider, assert_ok, make_asset, make_series):
    fake_json = {
        "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.1761]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"id": "2026-05-08"}]}]}},
    }

    provider = ecb_provider()
    provider.session.queue(200, fake_json)
    asset = make_asset(provider_code="USD_EUR")
    series = make_series(asset)

    start = make_identity(datetime(2026, 5, 8, tzinfo=ZoneInfo("Europe/Berlin")))
    end = make_identity(datetime(2026, 5, 8, 23, 59, 59, tzinfo=ZoneInfo("Europe/Berlin")))
    result = provider.fetch(series, asset, start=start, end=end, is_incremental=True)
    assert_ok(result, time=datetime(2026, 5, 8, 0, 0, 0, tzinfo=UTC), close=1.1761)
    assert provider.session.url == "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    assert provider.session.params == {"format": "jsondata", "updatedAfter": "2026-05-08", "detail": "dataonly"}


@pytest.mark.parametrize(
    "provider_code",
    [
        "EUR",
        "EUR_USD_GBP",
        "_",
    ],
)
def test_ecb_fetch_wrong_provider_code(ecb_provider, make_series, make_asset, provider_code, assert_error):
    provider: EcbProvider = ecb_provider()
    fake_session(provider).queue(200, {})

    asset = make_asset(provider_code=provider_code)
    series = make_series(asset)

    start = make_identity(datetime(2026, 5, 8, tzinfo=ZoneInfo("Europe/Berlin")))
    end = make_identity(datetime(2026, 5, 8, 23, 59, 59, tzinfo=ZoneInfo("Europe/Berlin")))
    result = provider.fetch(series, asset, start=start, end=end, is_incremental=True)
    assert result.ok is False
    assert f"Could not split provider code '{provider_code}' into base_quote" in result.reason


def test_ecb_fetch_non_200(ecb_provider, assert_error, make_asset, make_series, fixed_now):
    now = make_identity(fixed_now())
    provider: EcbProvider = ecb_provider()
    fake_session(provider).queue(500, "", "Internal Server Error")

    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)
    result = provider.fetch(series, asset, now, now, False)
    assert_error(result, reason="Exception during ECB fetch of eur_usd:dummy", error="Internal Server Error")


MALFORMED_CASES = [
    ({}, "['dataSets', 0, 'series']: Missing required key `dataSets`", "series"),
    ({"dataSets": []}, "['dataSets', 0, 'series']: index `0` out of range (level: 1)", "series"),
    ({"dataSets": [{"series": {}}]}, "['dataSets', 0, 'series']: expected at least one object value", "series"),
    (
        {"dataSets": [{"series": {"0:0:0:0:0": {}}}]},
        "['observations']: Missing required key `observations`",
        "observations",
    ),
    (
        {
            "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.234]}}}}],
            "structure": {"dimensions": {"observation": []}},
        },
        "['structure', 'dimensions', 'observation', 0, 'values']: index `0` out of range (level: 3)",
        "date metadata",
    ),
]


@pytest.mark.parametrize("json_data, expected, context", MALFORMED_CASES)
def test_ecb_malformed_json(
    ecb_provider, make_asset, make_series, json_data, expected, context, assert_error, fixed_now
):
    now = make_identity(fixed_now())
    provider: EcbProvider = ecb_provider()
    fake_session(provider).queue(200, json_data)

    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)
    result = provider.fetch(series, asset, now, now, False)
    assert_error(result, reason=f"Could not find ECB {context}", error=expected)


def test_ecb_fetch_multiple_points_skip_invalid(unwrap, ecb_provider, make_series, make_asset, fixed_now):
    fake_json = {
        "dataSets": [
            {
                "series": {
                    "0:0:0:0": {
                        "observations": {
                            "0": [1.10],
                            "1": [],
                            "2": "a",  # not a number
                            "3": [None],
                            "4": [0],
                            "5": [1.12],
                        }
                    }
                }
            }
        ],
        "structure": {
            "dimensions": {
                "observation": [
                    {
                        "values": [
                            {"id": "2024-01-01"},
                            {"id": "2024-01-02"},
                            {"id": "2024-01-03"},
                            {"id": "2024-01-04"},
                            {"id": "bogus"},
                            {"id": "2024-01-05"},
                        ]
                    }
                ]
            }
        },
    }

    now = make_identity(fixed_now())
    provider: EcbProvider = ecb_provider()
    fake_session(provider).queue(200, fake_json, make_series)
    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)
    result = provider.fetch(series, asset, now, now, True)
    fetch_result = unwrap(result)
    points = fetch_result.points
    assert len(points) == 2
    assert points[0].close == 1.10
    assert points[1].close == 1.12
