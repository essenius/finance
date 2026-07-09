# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_provider.py

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from finance.common.model import MeasurementResult
from finance.fetch.provider import MarketDataProvider


def test_init_defaults(dummy_provider):
    p = dummy_provider()

    assert p.api_key is None
    assert p.provider_config.timezone is not None
    assert p.timezone == ZoneInfo("UTC")
    assert isinstance(p.session, requests.Session)

    now = p.now()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_safe_call_success(dummy_provider):
    p = dummy_provider()

    def good():
        return MeasurementResult.ok_payload("x", [1, 2, 3])

    result = p._safe_call("ABC", good, "context")
    assert result.ok
    assert result.payload == [1, 2, 3]


def test_safe_call_exception(dummy_provider):
    p = dummy_provider()

    def bad():
        raise ValueError("kaboom")

    result = p._safe_call("ABC", bad, "context")

    assert result.payload is None
    assert "Exception during context" in result.reason
    assert "kaboom" in result.error


# -------------------------
# _safe_get tests
# -------------------------


def test_safe_get_ok(dummy_provider):
    p = dummy_provider()
    data = {"a": [{"b": 123}]}

    result = p._safe_get(data, ["a", 0, "b"])
    assert result.ok
    assert result.payload == 123
    assert result.reason is None
    assert result.error is None


@pytest.mark.parametrize(
    "data, path, expected",
    [
        ({"a": {}}, ["a", "b"], "missing key 'b' at ['a']"),
        ({"a": []}, ["a", 0], "missing index [0] at ['a']"),
        ({"a": 42}, ["a", 0], "cannot index with [0] at ['a']"),
    ],
)
def test_safe_get_errors(dummy_provider, data: any, path, expected):
    p = dummy_provider()
    result = p._safe_get(data, path)
    assert not result.ok
    assert result.payload is None
    assert result.reason == expected


# -----------
# Fetch test
# -----------


def test_fetch_not_implemented(dummy_provider, make_series, make_asset_dict, fixed_now):
    assets = make_asset_dict()
    now = fixed_now()
    result = dummy_provider().fetch(
        make_series(assets["eur_usd"]), assets, start_time=now, end_time=now, is_incremental=False
    )
    assert not result.ok
    assert result.reason == "fetch not implemented"


# -------------------------
# Normalize timestamp test
# -------------------------


def test_normalize_timestamp(fixed_now):
    now = fixed_now()
    timestamp = now.timestamp()
    # for daily or more, we have daily labels.
    # Note the date is different. Tokyo is 9 hours ahead of UTC, so the timestamp in local time is already in the next day.
    assert MarketDataProvider.normalize_timestamp(
        timestamp, is_intraday=False, zone_info=ZoneInfo("Asia/Tokyo")
    ) == datetime(2025, 6, 16, 0, 0, 0, tzinfo=UTC)

    # for intraday, we keep the timestamp in UTC
    assert MarketDataProvider.normalize_timestamp(timestamp, is_intraday=True, zone_info=ZoneInfo("Asia/Tokyo")) == now
