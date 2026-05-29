# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_controller.py

from typing import Any
from unittest.mock import Mock

import pytest

from finance.fetch.controller import FetchController


def make_asset(
    name="eurusd_intraday", provider="yahoo", symbol="EURUSD=X", interval="10m", fields=None, timeseries="intraday"
):
    # doing this to avoid mutable data structures in argument defaults, with risk of cross-contamination

    fields = ["close"] if fields is None else list(fields)
    return {
        "name": name,
        "provider": provider,
        "symbol": symbol,
        "interval": interval,
        "fields": fields,
        "timeseries": timeseries,
    }


# ----------------------------------------------------------------------
# Freshness skipping
# ----------------------------------------------------------------------


def test_controller_skips_fresh():
    fake_provider = Mock()
    fake_provider.fetch.return_value = {"timestamp": 999, "fields": {"close": 1.23}}

    now = 1_000_000_000
    asset = make_asset(interval="1h")

    fc = FetchController([asset], api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state = {
        "eurusd_intraday": {
            "last_try": now - 100,  # fresh vs 1h interval
            "last_timestamp": 123456,
        }
    }

    results = fc.fetch_all(state)
    assert results == {}
    fake_provider.fetch.assert_not_called()


# ----------------------------------------------------------------------
# Stale → fetch
# ----------------------------------------------------------------------


def test_controller_fetches_when_stale():
    fake_provider = Mock()
    fake_provider.fetch.return_value = {"timestamp": 777, "fields": {"close": 4.321}}

    now = 1_000_000_000
    asset = make_asset(interval="1h")

    fc = FetchController([asset], api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state = {
        "eurusd_intraday": {
            "last_try": now - 7200,  # stale vs 1h
            "last_timestamp": 123456,
        }
    }

    results = fc.fetch_all(state)

    fake_provider.fetch.assert_called_once_with(asset, 123456)

    assert results == {
        "eurusd_intraday": {
            "timestamp": 777,
            "fields": {"close": 4.321},
        }
    }

    assert state["eurusd_intraday"]["last_try"] == now


# ----------------------------------------------------------------------
# Unknown provider
# ----------------------------------------------------------------------


def test_controller_unknown_provider(capsys):
    asset = make_asset(provider="mystery")

    fc = FetchController([asset], api_keys={}, now_provider=lambda: 0)
    state = {}

    results = fc.fetch_all(state)

    assert results == {}
    assert state == {}

    err = capsys.readouterr().err
    assert "no provider" in err


@pytest.mark.parametrize(
    "side_effect, expected_err",
    [
        (None, ""),
        (RuntimeError("boom"), "Fetcher for eurusd_intraday failed: boom"),
    ],
)
def test_controller_provider_failure(capsys, side_effect, expected_err):
    fake = Mock()
    fake.fetch.side_effect = side_effect

    now = 1_000_000_000
    asset = make_asset()

    fc = FetchController([asset], api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake

    state = {"eurusd_intraday": {}}

    results = fc.fetch_all(state)

    assert results == {}
    assert state["eurusd_intraday"]["last_try"] == now

    err = capsys.readouterr().err
    if expected_err:
        assert expected_err in err
    else:
        assert err == ""


# ----------------------------------------------------------------------
# Malformed provider result
# ----------------------------------------------------------------------


def test_controller_malformed_result():
    fake_provider = Mock()
    fake_provider.fetch.return_value = {"foo": 1}

    now = 1_000_000_000
    asset = make_asset()

    fc = FetchController([asset], api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state = {"eurusd_intraday": {}}

    results = fc.fetch_all(state)

    fake_provider.fetch.assert_called_once()
    assert results == {}
    assert state["eurusd_intraday"]["last_try"] == now


# ----------------------------------------------------------------------
# Multiple assets
# ----------------------------------------------------------------------


def test_controller_multiple_assets():
    fake_provider = Mock()
    fake_provider.fetch.return_value = {"timestamp": 333, "fields": {"close": 3.3}}

    now = 1_000_000_000
    a1 = make_asset(name="eurusd_intraday")
    a2 = make_asset(name="spx_intraday", symbol="^GSPC")

    fc = FetchController([a1, a2], api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state = {}

    results = fc.fetch_all(state)

    assert fake_provider.fetch.call_count == 2
    assert "eurusd_intraday" in results
    assert "spx_intraday" in results


# ----------------------------------------------------------------------
# Interval respect
# ----------------------------------------------------------------------


def test_controller_respects_interval():
    fake_provider = Mock()
    fake_provider.fetch.return_value = {"timestamp": 444, "fields": {"close": 4.4}}

    asset = make_asset(interval="10s")

    now = 1_000_000_000
    fc = FetchController([asset], api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state = {"eurusd_intraday": {"last_try": now - 5}}

    fc.fetch_all(state)

    fake_provider.fetch.assert_not_called()


# ----------------------------------------------------------------------
# _validate_result tests
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "result",
    [
        None,
        ["not", "a", "dict"],
        {"timestamp": "not-int", "fields": {}},
        {"timestamp": 123, "fields": ["not-dict"]},
    ],
)
def test_validate_result_invalid(
    result: None | list[str] | dict[str, str | dict[Any, Any]] | dict[str, int | list[str]],
):
    fc = FetchController([], api_keys={}, now_provider=lambda: 0)
    assert fc._validate_result(result) is None


@pytest.mark.parametrize(
    "bad_asset",
    [
        # Missing provider
        {
            "name": "eurusd_intraday",
            "symbol": "EURUSD=X",
            "interval": "10m",
            "fields": ["close"],
            "timeseries": "intraday",
        },
        # Missing symbol
        {
            "name": "eurusd_intraday",
            "provider": "yahoo",
            "interval": "10m",
            "fields": ["close"],
            "timeseries": "intraday",
        },
        # Missing interval
        {
            "name": "eurusd_intraday",
            "provider": "yahoo",
            "symbol": "EURUSD=X",
            "fields": ["close"],
            "timeseries": "intraday",
        },
        # Missing fields
        {
            "name": "eurusd_intraday",
            "provider": "yahoo",
            "symbol": "EURUSD=X",
            "interval": "10m",
            "timeseries": "intraday",
        },
        # Missing timeseries
        {
            "name": "eurusd_intraday",
            "provider": "yahoo",
            "symbol": "EURUSD=X",
            "interval": "10m",
            "fields": ["close"],
        },
    ],
)
def test_controller_missing_asset_properties(bad_asset, capsys):
    now = 1_000_000_000

    fc = FetchController([bad_asset], api_keys={}, now_provider=lambda: now)

    state = {}

    results = fc.fetch_all(state)

    # No results produced
    assert results == {}

    # No state entry created
    assert state == {}

    # Error printed
    err = capsys.readouterr().err
    assert "missing keys" in err
    assert "eurusd_intraday" in err
