# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_controller.py

from collections.abc import Callable
from datetime import datetime
from unittest.mock import Mock

from finance.common.model import MeasurementResult
from finance.common.time_utils import parse_duration
from finance.fetch.controller import PROVIDER_REGISTRY, FetchController, create_providers
from finance.fetch.ecb import EcbProvider
from finance.fetch.fred import FredProvider
from finance.fetch.yahoo import YahooProvider
from finance.state.state import State


def make_asset(
    instrument="eur_usd",
    provider="yahoo",
    symbol="EURUSD=X",
    interval="10m",
    history_limit="5d",
    fields=None,
    timeseries="intraday",
):
    fields = ["close"] if fields is None else list(fields)
    series = f"{instrument}_{timeseries}"
    return {
        series: {
            "asset": instrument,
            "provider": provider,
            "symbol": symbol,
            "interval": interval,
            "interval_seconds": parse_duration(interval),
            "history_limit": history_limit,
            "history_limit_seconds": parse_duration(history_limit),
            "fields": fields,
            "timeseries": timeseries,
        }
    }


def single_result(fc: FetchController, state: State):
    results = list(fc.fetch_incrementally(state))
    assert len(results) == 1
    return results[0]


def make_fetch_controller(assets: dict, now_provider: Callable[[], datetime]):
    # Default fake provider
    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.ok_payload("eur_usd_intraday", [])

    # Build provider registry based on assets
    providers = {name: fake_provider for name in PROVIDER_REGISTRY}

    return FetchController(assets, providers, now_provider=now_provider)


# ----------------------------------------------------------------------
# create_providers
# ----------------------------------------------------------------------


def test_create_providers():
    providers_config = {
        "yahoo": {"timezone": "UTC"},
        "ecb": {"timezone": "Europe/Berlin"},
        "fred": {"timezone": "America/Chicago"},
    }
    p = create_providers(providers_config, {})
    assert isinstance(p["yahoo"], YahooProvider)
    assert isinstance(p["ecb"], EcbProvider)
    assert isinstance(p["fred"], FredProvider)


# ----------------------------------------------------------------------
# Freshness skipping
# ----------------------------------------------------------------------


def test_controller_skips_fresh(state, fixed_now):

    assets = make_asset(interval="1h")
    fc = make_fetch_controller(assets, fixed_now)

    now = fixed_now().timestamp()
    state.data.clear()
    state.data["eur_usd_intraday"] = {
        "last_try": now - 100,
        "first_timestamp": now - 10000,
        "last_timestamp": now - 1000,
    }

    results = list(fc.fetch_incrementally(state))
    assert results == []
    fc.providers["yahoo"].fetch.assert_not_called()


# ----------------------------------------------------------------------
# Stale → fetch
# ----------------------------------------------------------------------


def test_controller_fetches_when_stale(state, fixed_now):

    assets = make_asset(interval="1h")

    fc = make_fetch_controller(assets, fixed_now)
    now = fixed_now().timestamp()
    state.data.clear()
    state.data["eur_usd_intraday"] = {
        "last_try": now - 7200,
        "first_timestamp": now - 36000,
        "last_timestamp": now - 7200,  # stale vs 1h
    }

    result = single_result(fc, state)
    assert result.ok
    assert result.measurement == "eur_usd_intraday"

    fc.providers["yahoo"].fetch.assert_called_once()
    assert state.data["eur_usd_intraday"]["last_try"] == now


# ----------------------------------------------------------------------
# Unknown provider
# ----------------------------------------------------------------------


def test_controller_unknown_provider(state, fixed_now):

    assets = make_asset(provider="mystery")
    fc = FetchController(assets, providers={}, now_provider=fixed_now)

    result = single_result(fc, state)
    assert not result.ok
    assert "no provider" in result.reason
    assert result.measurement == "eur_usd_intraday"

    assert "eur_usd_intraday" in state.data
    assert state.data["eur_usd_intraday"]["last_try"] == fixed_now().timestamp()


# ----------------------------------------------------------------------
# Malformed provider result
# ----------------------------------------------------------------------


def test_controller_malformed_result(state_env, fixed_now):
    state, influx, _, _ = state_env
    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.fail("eur_usd_intraday", "bad data")

    assets = make_asset()
    fc = FetchController(assets, providers={"yahoo": fake_provider}, now_provider=fixed_now)
    result = single_result(fc, state)
    assert not result.ok
    assert "bad data" in result.reason

    # always updates state, even when failed
    assert state.data["eur_usd_intraday"]["last_try"] == fixed_now().timestamp()


# ----------------------------------------------------------------------
# Multiple assets
# ----------------------------------------------------------------------


def test_controller_multiple_assets(state, fixed_now):

    fake_provider = Mock()
    fake_provider.fetch.side_effect = [
        MeasurementResult.ok_payload("eur_usd_yahoo_intraday", []),
        MeasurementResult.ok_payload("spx_yahoo_intraday", []),
    ]

    assets = {
        **make_asset(instrument="eur_usd_yahoo"),
        **make_asset(instrument="spx_yahoo", symbol="^GSPC"),
    }

    fc = FetchController(assets, providers={}, now_provider=fixed_now)
    fc.providers["yahoo"] = fake_provider

    results = list(fc.fetch_incrementally(state))
    assert len(results) == 2

    assert fake_provider.fetch.call_count == 2
    assert "eur_usd_yahoo_intraday" in state.data
    assert "spx_yahoo_intraday" in state.data


def test_get_window_user_waited_too_long(fixed_now):
    fc = FetchController(assets={}, providers={}, now_provider=fixed_now)
    now = fixed_now().timestamp()
    start, end = fc.get_window(first_saved=now - 1000, last_saved=now - 1000, limit=500)
    assert (start, end) == (now - 500, now)


def test_get_window_normal_incremental(fixed_now):
    fc = FetchController(assets={}, providers={}, now_provider=fixed_now)
    now = fixed_now().timestamp()
    # limit = 500 → window_start = 1500
    start, end = fc.get_window(first_saved=now - 500, last_saved=now - 400, limit=500)
    assert (start, end) == (now - 400, now)
