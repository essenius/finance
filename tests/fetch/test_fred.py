# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_fred.py

from datetime import datetime, timedelta

import pytest

from finance.common.candle_identity import CandleIdentity
from finance.common.json_utils import JsonLike
from finance.common.model import Asset, Series
from finance.common.time_utils import UTC
from finance.fetch.fred import FredProvider
from tests.support.fakes import FakeProvider
from tests.support.types import AssertError, AssertFetchOk, Creator, Factory

type FredFakeSession = FakeProvider[FredProvider]

# The tests don't use the identity, but it is required by the API
NOW = CandleIdentity(datetime(1, 1, 1), is_daily=True, interval=timedelta(0))


def test_fred_fetch_normal_with_skipped(
    fred_provider: Factory[FredFakeSession],
    assert_fetch_ok: AssertFetchOk,
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):

    fake = fred_provider()
    fake.session.queue(
        status=200,
        json_data={
            "observations": [
                {"value": "2.34", "date": "2024-05-09"},
                {"value": "", "date": "2024-05-10"},
                {"value": ".", "date": "2024-05-11"},
                {"value": None, "date": "2024-05-12"},
                {"value": "2.55", "date": "bogus"},
            ]
        },
    )
    asset = make_asset(provider_code="T10YIE")
    # now is ignored
    result = fake.provider.fetch(make_series(asset), start=NOW, end=NOW, is_incremental=True)
    # no change in date as the date is a label, not a timestamp
    assert_fetch_ok(result, datetime(2024, 5, 9, 0, 0, 0, tzinfo=UTC), 2.34)
    assert result.ok is True
    assert len(result.payload.points) == 1, "Ignored invalid values"


# -------------------------------
# PARAMETRIZED MALFORMED CASES
# -------------------------------

MALFORMED_CASES = [
    # Missing API key (provider-level behavior)
    (
        None,  # api_key
        {"observations": [{"value": "2.34", "date": "2024-05-09"}]},
        "FRED requires an API key",
    ),
    # Observations missing
    (
        "TESTKEY",
        {"foo": "bar"},
        "['observations']: Missing required key `observations`",
    ),
]


@pytest.mark.parametrize("api_key, json_data, expected_error", MALFORMED_CASES)
def test_fred_malformed_cases(
    assert_error: AssertError,
    fred_provider: Creator[FredFakeSession],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
    api_key: str,
    json_data: JsonLike,
    expected_error: str,
):
    fake = fred_provider(api_key)
    # Missing API key → no HTTP call
    if api_key is not None:
        fake.session.queue(200, json_data)

    asset = make_asset(provider_code="T10YIE")
    result = fake.provider.fetch(make_series(asset), start=NOW, end=NOW, is_incremental=True)
    assert_error(result, expected_error, None)


def test_fred_fetch_network_error(
    assert_error: AssertError,
    fred_provider: Factory[FredFakeSession],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):
    fake = fred_provider()
    fake.session.queue_error(Exception("Boom!"))

    asset = make_asset(provider_code="T10YIE")
    result = fake.provider.fetch(make_series(asset), start=NOW, end=NOW, is_incremental=True)

    assert_error(result, "Exception during fred fetch", "Boom!")


def test_fred_status_code_not_200(
    assert_error: AssertError,
    fred_provider: Factory[FredFakeSession],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):
    fake = fred_provider()
    fake.session.queue(500, {}, "status 500")
    asset = make_asset(provider_code="T10YIE")
    result = fake.provider.fetch(make_series(asset), start=NOW, end=NOW, is_incremental=True)
    assert_error(result, "Exception during fred fetch", "status 500")
