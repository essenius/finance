# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_controller.py

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from unittest.mock import Mock

from finance.common.model import (
    INTRADAY,
    Asset,
    MeasurementResult,
    ProviderConfig,
    Series,
    SeriesState,
    SeriesType,
    SupportedProviders,
)
from finance.fetch.controller import PROVIDER_REGISTRY, FetchController, create_providers
from finance.fetch.ecb import EcbProvider
from finance.fetch.fred import FredProvider
from finance.fetch.yahoo import YahooProvider
from finance.state.state import State

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def always_none(*args, **kwargs):
    return None


def make_assets(assets: list[Asset]):
    result = {}
    for asset in assets:
        result[asset.id] = asset
    return result


def make_series_list(asset, interval="10m", history_limit="5d", resolution=INTRADAY, id=None):
    series = f"{asset.name}_{resolution}"
    if id is None:
        id = asset.id
    return [
        Series(
            id=id,
            name=series,
            resolution=resolution,
            asset_id=asset.id,
            asset_name=asset.name,
            series_type=SeriesType.VALUE,
            interval=interval,
            # interval_delta=parse_duration(interval),
            history_limit=history_limit,
            # history_limit_delta=parse_duration(history_limit),
        )
    ]


def single_result(fc: FetchController, state: State):
    results = list(fc.fetch_incrementally(state))
    assert len(results) == 1
    return results[0]


def make_fetch_controller(
    series: Iterable[Series], get_asset: Callable[[int], Asset], now_provider: Callable[[], datetime]
):
    # Default fake provider
    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.ok_payload("eur_usd_intraday", [])

    # Build provider registry based on assets
    providers = {name: fake_provider for name in PROVIDER_REGISTRY}

    return FetchController(series, get_asset, providers.get, now_provider=now_provider)


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_create_providers():
    providers_config = {
        SupportedProviders.YAHOO: ProviderConfig(name=SupportedProviders.YAHOO, timezone="UTC"),
        SupportedProviders.ECB: ProviderConfig(name=SupportedProviders.ECB, timezone="Europe/Berlin"),
        SupportedProviders.FRED: ProviderConfig(name=SupportedProviders.FRED, timezone="America/Chicago"),
    }
    p = create_providers(providers_config, {})
    assert isinstance(p[SupportedProviders.YAHOO], YahooProvider)
    assert isinstance(p[SupportedProviders.ECB], EcbProvider)
    assert isinstance(p[SupportedProviders.FRED], FredProvider)


def test_controller_skips_fresh(state, fixed_now, make_asset):
    asset = make_asset()
    assets = make_assets([asset])
    series = make_series_list(asset, interval="1h")
    fc = make_fetch_controller(series, assets.get, fixed_now)

    now = fixed_now()
    first = now - timedelta(seconds=10000)
    last = now - timedelta(seconds=1000)
    last_try = now - timedelta(seconds=100)
    state.series.clear()
    state.series[1] = SeriesState(last_try=last_try, first_time=first, last_time=last)

    results = list(fc.fetch_incrementally(state))
    assert results == []
    fc.get_providers("yahoo").fetch.assert_not_called()


def test_controller_fetches_when_stale(state, fixed_now, make_asset):

    asset = make_asset()
    assets = make_assets([asset])
    series = make_series_list(asset, interval="1h")

    fc = make_fetch_controller(series, assets.get, fixed_now)
    now = fixed_now()
    state.series.clear()

    # stale vs 1h
    state.series[1] = SeriesState(
        last_try=now - timedelta(hours=2), first_time=now - timedelta(hours=10), last_time=now - timedelta(hours=2)
    )

    result = single_result(fc, state)
    assert result.ok
    assert result.series_name == "eur_usd_intraday"

    fc.get_providers("yahoo").fetch.assert_called_once()
    assert state.series[1].last_try == now


def test_controller_unknown_provider(assert_error, state, fixed_now, make_asset):

    asset = make_asset(provider="mystery")
    assets = make_assets([asset])
    series = make_series_list(asset)
    providers = {}
    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)

    result = single_result(fc, state)
    assert_error(result, "no provider 'mystery'", "Skipped series 'eur_usd_intraday'")

    assert result.series_name == "eur_usd_intraday"

    assert 1 in state.series
    assert state.series[1].last_try == fixed_now()


def test_controller_unknown_asset(assert_error, state, fixed_now, make_asset):

    asset = make_asset()
    series = make_series_list(asset)
    assets = {}
    providers = {}
    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)

    result = single_result(fc, state)
    assert_error(result, "Could not find asset 1 (eur_usd)", "Skipped series 'eur_usd_intraday'")


def test_controller_malformed_result(assert_error, state, fixed_now, make_asset):
    fake_provider = Mock()
    fake_provider.fetch.return_value = MeasurementResult.fail("eur_usd_intraday", "bad data")

    asset = make_asset()
    assets = make_assets([asset])
    series = make_series_list(asset)
    providers = {"yahoo": fake_provider}

    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)
    result = single_result(fc, state)
    assert_error(result, "bad data", None)

    # always updates state, even when failed
    assert state.series[1].last_try == fixed_now()


def test_controller_multiple_assets(state, fixed_now, make_asset):

    fake_provider = Mock()
    fake_provider.fetch.side_effect = [
        MeasurementResult.ok_payload("eur_usd_yahoo_intraday", []),
        MeasurementResult.ok_payload("spx_yahoo_intraday", []),
    ]

    asset1 = make_asset(name="eur_usd_yahoo")
    asset2 = make_asset(id=2, name="spx_yahoo", provider_code="^GSPC")
    assets = make_assets([asset1, asset2])
    series = make_series_list(asset1) + make_series_list(asset2)

    def get_providers(name: str):
        return fake_provider

    fc = FetchController(series, assets.get, get_providers, now_provider=fixed_now)

    results = list(fc.fetch_incrementally(state))
    assert len(results) == 2

    assert fake_provider.fetch.call_count == 2
    assert 1 in state.series
    assert 2 in state.series


def test_get_window_user_waited_too_long(fixed_now):
    fc = FetchController([], always_none, always_none, now_provider=fixed_now)
    now = fixed_now()
    last = now - timedelta(seconds=1000)
    limit = timedelta(seconds=500)
    start, end = fc.get_window(first_saved=last, last_saved=last, limit=limit)
    assert (start, end) == (now - limit, now)


def test_get_window_normal_incremental(fixed_now):
    fc = FetchController([], always_none, always_none, now_provider=fixed_now)
    now = fixed_now()
    limit = timedelta(seconds=500)
    first = now - limit
    last = now - timedelta(seconds=400)
    start, end = fc.get_window(first_saved=first, last_saved=last, limit=limit)
    assert (start, end) == (last, now)
