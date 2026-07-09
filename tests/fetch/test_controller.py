# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_controller.py

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, time, timedelta
from unittest.mock import Mock

from finance.common.model import (
    Asset,
    CompletionPolicy,
    MeasurementResult,
    ProviderConfig,
    Series,
    SeriesState,
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


def single_result(fc: FetchController, state: State):
    results = list(fc.fetch_incrementally(state))
    assert len(results) == 1
    return results[0]


def make_fake_provider(fetch_result=None):
    if fetch_result is None:
        fetch_result = MeasurementResult.ok_payload("eur_usd:dummy", [])
    fake_provider = Mock()
    fake_provider.fetch.return_value = fetch_result
    fake_provider.provider_config = Mock()
    fake_provider.provider_config.get_history_limit.return_value = timedelta(days=60)
    return fake_provider


def make_fetch_controller(
    series: Iterable[Series], get_asset: Callable[[int], Asset], now_provider: Callable[[], datetime], fetch_result=None
):
    fake_provider = make_fake_provider(fetch_result)

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


def test_controller_skips_fresh(state, fixed_now, make_asset, make_series):
    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset, interval="1h")]
    fc = make_fetch_controller(series, assets.get, fixed_now)

    now = fixed_now()
    first = now - timedelta(seconds=10000)
    last = now - timedelta(seconds=1000)
    last_try = now - timedelta(seconds=100)
    state.series.clear()
    state.series[1] = SeriesState(last_try=last_try, first_time=first, last_time=last)

    results = list(fc.fetch_incrementally(state))
    assert results == []
    fc.get_provider("yahoo").fetch.assert_not_called()


def test_controller_fetches_when_stale(state, fixed_now, make_asset, make_series):

    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset, interval="1h")]

    fc = make_fetch_controller(series, assets.get, fixed_now)
    now = fixed_now()
    state.series.clear()

    # stale vs 1h
    state.series[1] = SeriesState(
        last_try=now - timedelta(hours=2), first_time=now - timedelta(hours=10), last_time=now - timedelta(hours=2)
    )

    result = single_result(fc, state)
    assert result.ok
    assert result.series_name == "eur_usd:dummy"

    fc.get_provider("yahoo").fetch.assert_called_once()
    assert state.series[1].last_try == now


def test_controller_skips_fetch_with_next_day(state, fixed_now, make_asset, make_series):

    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset, interval="1h", completion_policy=CompletionPolicy.NEXT_DAY)]

    fc = make_fetch_controller(series, assets.get, fixed_now)
    now = fixed_now()
    today = datetime.combine(now, time.min, UTC)
    state.series.clear()
    yesterday = today - timedelta(days=1)
    # should not retrieve
    state.series[1] = SeriesState(first_time=yesterday, last_time=yesterday, last_try=yesterday)

    results = list(fc.fetch_incrementally(state))
    assert len(results) == 0
    fc.get_provider("yahoo").fetch.assert_not_called()
    assert state.series[1].last_try == yesterday


def test_controller_unknown_provider(assert_error, state, fixed_now, make_asset, make_series):

    asset = make_asset(provider="mystery")
    assets = make_assets([asset])
    series = [make_series(asset)]
    providers = {}
    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)

    result = single_result(fc, state)
    assert_error(result, "no provider 'mystery'", "Skipped series 'eur_usd:dummy'")

    assert result.series_name == "eur_usd:dummy"

    assert 1 in state.series
    assert state.series[1].last_try == fixed_now()


def test_controller_unknown_asset(assert_error, state, fixed_now, make_asset, make_series):

    asset = make_asset()
    series = [make_series(asset)]
    assets = {}
    providers = {}
    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)

    result = single_result(fc, state)
    assert_error(result, "Could not find asset 1 (eur_usd)", "Skipped series 'eur_usd:dummy'")


def test_controller_malformed_result(assert_error, state, fixed_now, make_asset, make_series):
    fake_provider = make_fake_provider(fetch_result=MeasurementResult.fail("eur_usd_dummy", "bad data"))

    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset)]
    providers = {"yahoo": fake_provider}

    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)
    result = single_result(fc, state)
    assert_error(result, "bad data", None)

    # always updates state, even when failed
    assert state.series[1].last_try == fixed_now()


def test_controller_none_limit(unwrap, state, fixed_now, make_asset, make_series):
    fake_provider = make_fake_provider()
    fake_provider.provider_config.get_history_limit.return_value = None
    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset)]
    providers = {"yahoo": fake_provider}

    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)
    unwrap(single_result(fc, state))
    assert state.series[1].last_try == fixed_now()


def test_controller_multiple_assets(state, fixed_now, make_asset, make_series):

    fake_provider = make_fake_provider()

    fake_provider.fetch.side_effect = [
        MeasurementResult.ok_payload("eur_usd_yahoo_intraday", []),
        MeasurementResult.ok_payload("spx_yahoo_intraday", []),
    ]

    asset1 = make_asset(name="eur_usd_yahoo")
    asset2 = make_asset(id=2, name="spx_yahoo", provider_code="^GSPC")
    assets = make_assets([asset1, asset2])
    series = [make_series(asset1), make_series(asset2)]

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
    start, end, is_incremental = fc.get_window(first_saved=last, last_saved=last, limit=limit, overlap=timedelta(0))
    assert (start, end, is_incremental) == (now - limit, now, False)


def test_get_window_normal_incremental(fixed_now):
    fc = FetchController([], always_none, always_none, now_provider=fixed_now)
    now = fixed_now()
    limit = timedelta(seconds=500)
    first = now - limit
    last = now - timedelta(seconds=400)
    result = fc.get_window(first_saved=first, last_saved=last, limit=limit, overlap=timedelta(0))
    # the start must be right after the last saved time, not on it
    assert result == (last, now, True)


def test_get_window_normal_includes_overlap(fixed_now):
    fc = FetchController([], always_none, always_none, now_provider=fixed_now)
    now = fixed_now()
    limit = timedelta(seconds=500)
    first = now - limit
    last = now - timedelta(seconds=400)
    overlap = timedelta(seconds=100)
    window_start = last - overlap
    result = fc.get_window(first_saved=first, last_saved=last, limit=limit, overlap=overlap)
    # the start must be right after the last saved time, not on it
    assert result == (window_start, now, True)
