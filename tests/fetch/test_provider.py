# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_provider.py

from datetime import datetime, timedelta

import requests

from finance.common.candle_identity import CandleIdentity
from finance.common.configuration import ProviderConfig
from finance.common.model import Series
from finance.common.time_utils import UTC
from finance.common.types import Result, Success
from finance.fetch.provider import MarketDataProvider
from tests.support.types import Creator


def provider() -> MarketDataProvider:
    return MarketDataProvider(provider_config=ProviderConfig.from_config({"name": "dummy"}))


def test_init_defaults():
    p = provider()

    assert isinstance(p.session, requests.Session)

    now = p.now()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_safe_call_success():
    p = provider()

    def good() -> Result[list[int]]:
        return Success([1, 2, 3])

    result = p._safe_call(good, "context")
    # is True is required here to narrow the Result union
    assert result.ok is True
    assert result.payload == [1, 2, 3]


def test_safe_call_exception():
    p = provider()

    def bad() -> Result[int]:
        raise ValueError("kaboom")

    result = p._safe_call(bad, "context")
    assert result.ok is False
    assert "Exception during context" in result.reason
    assert "kaboom" in str(result.error)


# -----------
# Fetch test
# -----------


def test_fetch_not_implemented(make_series: Creator[Series], make_asset_dict, fixed_now):
    assets = make_asset_dict()
    now = CandleIdentity(fixed_now(), False, timedelta(0))
    result = provider().fetch(make_series(assets["eur_usd"]), assets, start=now, end=now, is_incremental=False)
    assert result.ok is False
    assert result.reason == "fetch not implemented"
