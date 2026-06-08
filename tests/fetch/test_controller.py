# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_controller.py

import time
from unittest.mock import Mock

import pytest

from finance.common.model import MeasurementResult
from finance.fetch.controller import FetchController
from finance.state.manager import State


def make_asset(
    instrument="eur_usd",
    provider="yahoo",
    symbol="EURUSD=X",
    interval="10m",
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
            "fields": fields,
            "timeseries": timeseries,
        }
    }


def single_result(fc, state):
    results = list(fc.fetch_incrementally(state))
    assert len(results) == 1
    return results[0]

# ----------------------------------------------------------------------
# Freshness skipping
# ----------------------------------------------------------------------


def test_controller_skips_fresh(state_env, monkeypatch):
    state, ts, wal, path = state_env

    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.ok_payload("eur_usd_intraday", [])

    now = 1_000_000_000
    monkeypatch.setattr(time, "time", lambda: now)

    assets = make_asset(interval="1h")
    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state.data.clear()
    state.data["eur_usd_intraday"] = {
        "last_try": now - 100,  # fresh vs 1h interval
        "last_timestamp": 123456,
    }

    results = list(fc.fetch_incrementally(state))
    assert results == []
    fake_provider.fetch.assert_not_called()


# ----------------------------------------------------------------------
# Stale → fetch
# ----------------------------------------------------------------------


def test_controller_fetches_when_stale(state_env, monkeypatch):
    state, ts, wal, path = state_env

    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.ok_payload("eur_usd_intraday", [])

    now = 1_000_000_000
    monkeypatch.setattr(time, "time", lambda: now)

    assets = make_asset(interval="1h")
    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state.data.clear()
    state.data["eur_usd_intraday"] = {
        "last_try": now - 7200,  # stale vs 1h
        "last_timestamp": 123456,
    }


    result = single_result(fc, state)
    assert result.ok
    assert result.measurement == "eur_usd_intraday"

    fake_provider.fetch.assert_called_once()
    assert state.data["eur_usd_intraday"]["last_try"] == now


# ----------------------------------------------------------------------
# Unknown provider
# ----------------------------------------------------------------------


def test_controller_unknown_provider(state_env, monkeypatch, frozen_time):
    state, ts, wal, path = state_env

    now = frozen_time

    assets = make_asset(provider="mystery")
    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)


    result = single_result(fc, state)
    assert not result.ok
    assert "no provider" in result.reason
    assert result.measurement == "eur_usd_intraday"

    assert "eur_usd_intraday" in state.data
    assert state.data["eur_usd_intraday"]["last_try"] == now


# ----------------------------------------------------------------------
# Malformed provider result
# ----------------------------------------------------------------------


def test_controller_malformed_result(state_env, monkeypatch, frozen_time):
    state, ts, wal, path = state_env

    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.fail("eur_usd_intraday", "bad data")

    now = frozen_time

    assets = make_asset()
    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    result = single_result(fc, state)
    assert not result.ok
    assert "bad data" in result.reason

    assert state.data["eur_usd_intraday"]["last_try"] == now


# ----------------------------------------------------------------------
# Multiple assets
# ----------------------------------------------------------------------


def test_controller_multiple_assets(state_env, monkeypatch, frozen_time):
    state, ts, wal, path = state_env

    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.ok_payload("dummy", [])

    now = frozen_time

    assets = {
        **make_asset(instrument="eur_usd_yahoo"),
        **make_asset(instrument="spx_yahoo", symbol="^GSPC"),
    }

    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    results = list(fc.fetch_incrementally(state))
    assert len(results) == 2

    assert fake_provider.fetch.call_count == 2
    assert "eur_usd_yahoo_intraday" in state.data
    assert "spx_yahoo_intraday" in state.data


# ----------------------------------------------------------------------
# Interval respect
# ----------------------------------------------------------------------


def test_controller_respects_interval(state_env, monkeypatch, frozen_time):
    state, ts, wal, path = state_env

    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.ok_payload("eur_usd_intraday", [])

    now = frozen_time

    assets = make_asset(interval="10s")
    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)
    fc.providers["yahoo"] = fake_provider

    state.data.clear()
    state.data["eur_usd_intraday"] = {"last_try": now - 5}

    results = list(fc.fetch_incrementally(state))
    assert results == []
    fake_provider.fetch.assert_not_called()


# ----------------------------------------------------------------------
# Interval parse failure
# ----------------------------------------------------------------------


def test_controller_interval_parse_failure(state_env, monkeypatch, frozen_time):
    state, ts, wal, path = state_env

    now = frozen_time

    assets = make_asset(interval="nonsense")
    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)

    result = single_result(fc, state)
    assert not result.ok
    assert "could not parse interval" in result.reason
    assert result.measurement == "eur_usd_intraday"

    assert "eur_usd_intraday" in state.data
    assert state.data["eur_usd_intraday"]["last_try"] == now


def test_controller_always_updates_state(state_env, frozen_time):
    state, ts, wal, path = state_env
    now = frozen_time

    assets = make_asset(interval="nonsense")  # guaranteed fail
    fc = FetchController(assets, api_keys={}, now_provider=lambda: now)

    _ = single_result(fc, state)

    assert "eur_usd_intraday" in state.data
    assert state.data["eur_usd_intraday"]["last_try"] == now
