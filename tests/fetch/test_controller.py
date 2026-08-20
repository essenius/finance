# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_controller.py

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from finance.common.candle_identity import CandleIdentity
from finance.common.model import Asset, FetchResult, ProviderConfig, Series, SeriesState, SweepConfig
from finance.common.result import Result
from finance.common.series_calendar import SeriesCalendar
from finance.common.string_enums import Retention, SupportedProviders
from finance.common.time_utils import snap_to
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


def fetch_with_single_result(fc: FetchController, state: State) -> FetchResult:
    results = list(fc.fetch_incrementally(state))
    assert len(results) == 1
    return results[0]


def make_fake_provider(fetch_result=None):
    if fetch_result is None:
        fetch_result = Result.ok_payload([])
    fake_provider = Mock()
    fake_provider.fetch.return_value = fetch_result
    fake_provider.provider_config = Mock()
    fake_provider.provider_config.get_history_limit.return_value = timedelta(days=60)
    fake_provider.provider_config.get_sweep.return_value = SweepConfig(timedelta(0), timedelta(0))

    return fake_provider


def make_fetch_controller(
    series: Iterable[Series], get_asset: Callable[[int], Asset], now_provider: Callable[[], datetime], fetch_result=None
):
    fake_provider = make_fake_provider(fetch_result)

    # Build provider registry based on assets
    providers = dict.fromkeys(PROVIDER_REGISTRY, fake_provider)

    return FetchController(series, get_asset, providers.get, now_provider=now_provider)


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_create_providers():
    providers_config = {
        SupportedProviders.YAHOO: ProviderConfig(name=SupportedProviders.YAHOO),
        SupportedProviders.ECB: ProviderConfig(name=SupportedProviders.ECB),
        SupportedProviders.FRED: ProviderConfig(name=SupportedProviders.FRED),
    }
    p = create_providers(providers_config, {})
    assert isinstance(p[SupportedProviders.YAHOO], YahooProvider)
    assert isinstance(p[SupportedProviders.ECB], EcbProvider)
    assert isinstance(p[SupportedProviders.FRED], FredProvider)


def test_controller_skips_fresh(state, make_asset, make_series):
    asset = make_asset()
    assets = make_assets([asset])
    series = [
        make_series(
            asset,
            interval="1h",
        )
    ]

    def fake_now():
        # this is a Wednesday
        return datetime(2025, 6, 11, 15, 6, 40, tzinfo=UTC)

    fc = make_fetch_controller(series, assets.get, fake_now)

    now = fake_now()
    last = snap_to(now, timedelta(hours=1))
    first = last - timedelta(days=6)  # we want 5 days, we have 6
    state.series.clear()
    state.series[1] = SeriesState(first_point=first, last_point=last)

    results = list(fc.fetch_incrementally(state))
    assert results == []
    fc.get_provider("yahoo").fetch.assert_not_called()


def test_controller_fetch_when_oldest_too_new(state, make_asset, make_series):
    asset = make_asset()
    assets = make_assets([asset])
    series = [
        make_series(
            asset,
            interval="1h",
        )
    ]

    def fake_now():
        # this is a Wednesday
        return datetime(2025, 6, 11, 15, 6, 40, tzinfo=UTC)

    fc = make_fetch_controller(series, assets.get, fake_now)

    now = fake_now()

    last = snap_to(now, timedelta(hours=1))
    first = last - timedelta(days=1)  # we want 5 days, we have 1

    state.series.clear()
    state.series[1] = SeriesState(last_point=last, first_point=first)

    result = fetch_with_single_result(fc, state)
    assert result.ok


def test_controller_fetches_when_stale(state, fixed_now, make_asset, make_series):

    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset, interval="1h")]

    fc = make_fetch_controller(series, assets.get, fixed_now)
    now = fixed_now()
    state.series.clear()

    # stale vs 1h
    state.series[1] = SeriesState(first_point=now - timedelta(weeks=1), last_point=now - timedelta(days=2))

    result = fetch_with_single_result(fc, state)
    assert result.ok

    fc.get_provider("yahoo").fetch.assert_called_once()


def test_controller_skips_fetch_with_offset(state, make_asset, make_metadata, make_series):

    fake_hour = 12

    def fake_now():
        return datetime(2026, 7, 23, fake_hour, 40, tzinfo=UTC)

    meta = make_metadata(timezone=ZoneInfo("Europe/Berlin"))
    asset = make_asset(effective_metadata=meta)
    assets = make_assets([asset])
    series = [make_series(asset, interval="1d", publication_offset="16h")]

    fc = make_fetch_controller(series, assets.get, fake_now)
    now = fake_now()
    today = datetime.combine(now.date(), time.min, UTC)
    state.series.clear()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(weeks=1)
    # should not retrieve as publication time not passed yet
    state.series[1] = SeriesState(first_point=last_week, last_point=yesterday)
    results = list(fc.fetch_incrementally(state))
    assert len(results) == 0, "no result as publication time not passed"
    fc.get_provider("yahoo").fetch.assert_not_called()

    # should retrieve as publication time passed passed
    fake_hour = 15
    results = list(fc.fetch_incrementally(state))
    assert len(results) == 1, "result as publication time passed"


def test_controller_unknown_provider(assert_error, state, fixed_now, make_asset, make_series):

    asset = make_asset(provider="mystery")
    assets = make_assets([asset])
    series = [make_series(asset)]
    providers = {}
    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)

    result = fetch_with_single_result(fc, state)
    assert_error(result, "no provider 'mystery'", "Skipped series 'eur_usd:dummy'")

    assert 1 in state.series


def test_controller_unknown_asset(assert_error, state, fixed_now, make_asset, make_series):

    asset = make_asset()
    series = [make_series(asset)]
    assets = {}
    providers = {}
    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)

    result = fetch_with_single_result(fc, state)
    assert_error(result, "Could not find asset 1 (eur_usd)", "Skipped series 'eur_usd:dummy'")


def test_controller_malformed_result(assert_error, state, fixed_now, make_asset, make_series):
    fake_provider = make_fake_provider(fetch_result=Result.fail(reason="bad data"))

    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset)]
    providers = {"yahoo": fake_provider}

    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)
    result = fetch_with_single_result(fc, state)
    assert_error(result, "bad data", None)


def test_controller_none_limit(unwrap, state, fixed_now, make_asset, make_series):
    fake_provider = make_fake_provider()
    fake_provider.provider_config.get_history_limit.return_value = None
    asset = make_asset()
    assets = make_assets([asset])
    series = [make_series(asset)]
    providers = {"yahoo": fake_provider}

    fc = FetchController(series, assets.get, providers.get, now_provider=fixed_now)
    unwrap(fetch_with_single_result(fc, state))


def test_controller_multiple_assets(state, fixed_now, make_asset, make_series):

    fake_provider = make_fake_provider()

    fake_provider.fetch.side_effect = [
        Result.ok_payload([]),
        Result.ok_payload([]),
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


def test_compute_fetch_range_intraday(make_series, make_asset):
    fake_provider = make_fake_provider(fetch_result=Result.fail(reason="bad data"))

    asset = make_asset()
    calendar = SeriesCalendar.from_asset_metadata(asset.effective_metadata)
    assets = make_assets([asset])
    series_list = [make_series(asset)]  # 10m interval
    providers = {"yahoo": fake_provider}

    def mock_now():
        return datetime(2026, 7, 15, 15, 30, tzinfo=UTC)

    fc = FetchController(series_list, assets.get, providers.get, now_provider=mock_now)

    series = series_list[0]

    # Plain incremental (one new point)
    state_entry_1 = SeriesState(
        first_point=datetime(2026, 6, 15, tzinfo=UTC), last_point=datetime(2026, 7, 15, 15, 10, tzinfo=UTC)
    )

    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_1, calendar=calendar)
    assert result is not None, "1st: intraday publication expected"
    first, last, is_incremental = result
    assert is_incremental, "1st: is incremental"
    assert first.store_label() == datetime(2026, 7, 15, 15, 20, tzinfo=UTC)
    assert last.store_label() == datetime(2026, 7, 15, 15, 20, tzinfo=UTC)

    # No new points
    state_entry_2 = SeriesState(
        first_point=datetime(2026, 6, 15, tzinfo=UTC), last_point=datetime(2026, 7, 15, 15, 20, tzinfo=UTC)
    )
    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_2, calendar=calendar)
    assert result is None, "2nd: intraday publication not expected"

    # older history to fetch
    state_entry_3 = SeriesState(
        first_point=datetime(2026, 7, 13, tzinfo=UTC), last_point=datetime(2026, 7, 15, 15, 20, tzinfo=UTC)
    )

    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_3, calendar=calendar)
    assert result is not None, "3rd: intraday publication expected"
    first, last, is_incremental = result
    assert not is_incremental, "3rd: not incremental"
    assert first.store_label() == datetime(2026, 7, 10, 15, 30, tzinfo=UTC), "3rd: first is before saved range"
    assert last.store_label() == datetime(2026, 7, 10, 23, 50, tzinfo=UTC), "3rd: last is before saved range"

    long_lived_series = replace(series, retention=Retention.LONG_LIVED)
    result = fc.get_fetch_range(
        series=long_lived_series, provider=fake_provider, state=state_entry_3, calendar=calendar
    )
    assert result is not None, "3rd: intraday insufficient history"

    # start with the point that didn't expect publication and enable sweeps
    fake_provider.provider_config.get_sweep.return_value = SweepConfig(
        window=timedelta(days=1), cadence=timedelta(hours=1)
    )
    state_entry_2.next_sweep = state_entry_2.last_point
    state_entry_2.sweep_start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)  # a Saturday
    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_2, calendar=calendar)

    assert result is not None, "sweep: publication expected"
    first, last, is_incremental = result
    assert not is_incremental, "sweep: not incremental"
    assert first.store_label() == datetime(2026, 7, 13, 15, 30, tzinfo=UTC), "sweep: first == sweep start"
    assert last.store_label() == datetime(2026, 7, 15, 15, 20, tzinfo=UTC), "sweep: last == last_req"
    assert state_entry_2.next_sweep == datetime(2026, 7, 15, 16, 20, tzinfo=UTC), "sweep: next == last + cadence"
    assert state_entry_2.sweep_start == datetime(2026, 7, 14, 15, 20, tzinfo=UTC), "sweep: start == last - window"
    assert state_entry_2.needs_save, "sweep: needs save"


def test_compute_fetch_range_daily(make_series, make_asset, make_metadata):
    fake_provider = make_fake_provider(fetch_result=Result.fail(reason="bad data"))

    meta = make_metadata(first_trade_date=date(2021, 10, 1))
    asset = make_asset(effective_metadata=meta)
    calendar = SeriesCalendar.from_asset_metadata(asset.effective_metadata)
    assets = make_assets([asset])

    # Daily series. Set first trade date less than 5 years ago to test it is respected.
    series_list = [
        make_series(asset, interval="1d", bootstrap_history="5y", retention=Retention.LONG_LIVED, retention_period=None)
    ]
    providers = {"yahoo": fake_provider}

    def mock_now():
        return datetime(2026, 7, 15, 13, 30, tzinfo=UTC)

    fc = FetchController(series_list, assets.get, providers.get, now_provider=mock_now)
    series = series_list[0]

    # --- Publication expected (last_point behind)
    state_entry_1 = SeriesState(
        first_point=datetime(2021, 10, 1, tzinfo=UTC), last_point=datetime(2026, 7, 13, tzinfo=UTC)
    )
    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_1, calendar=calendar)

    assert result is not None, "1st: daily publication expected"
    first, last, is_incremental = result
    assert is_incremental, "1 is incremental"
    assert first.store_label() == datetime(2026, 7, 14, tzinfo=UTC), "1st: 14th is first"
    assert last.store_label() == datetime(2026, 7, 14, tzinfo=UTC), "1st: 15th not yet, as not finished"
    assert not state_entry_1.needs_save, "needs save"

    # --- Publication NOT expected (last_point == today)
    state_entry_2 = SeriesState(
        first_point=datetime(2021, 10, 1, tzinfo=UTC), last_point=datetime(2026, 7, 14, tzinfo=UTC)
    )
    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_2, calendar=calendar)
    assert result is None, "2nd: daily publication not expected"

    # Insufficient history (first_point too recent)
    state_entry_3 = SeriesState(
        first_point=datetime(2021, 10, 5, tzinfo=UTC), last_point=datetime(2026, 7, 14, tzinfo=UTC)
    )
    # first_req is Fri 2021-10-01 < last_not_fetched, so there is prepend history
    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_3, calendar=calendar)

    assert result is not None, "3rd: daily insufficient history"
    first, last, is_incremental = result
    assert not is_incremental, "3rd: not incremental"
    assert first.store_label() == datetime(2021, 10, 1, tzinfo=UTC), "3rd: first is before range"
    assert last.store_label() == datetime(2021, 10, 4, tzinfo=UTC), "3rd: last is before range"

    # start with the point that didn't expect publication and enable sweeps
    fake_provider.provider_config.get_sweep.return_value = SweepConfig(
        window=timedelta(days=7), cadence=timedelta(days=1)
    )
    state_entry_2.next_sweep = state_entry_2.last_point
    state_entry_2.sweep_start = datetime(2026, 7, 11, tzinfo=UTC)  # a Saturday
    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry_2, calendar=calendar)

    assert result is not None, "sweep publication expected"
    first, last, is_incremental = result
    assert not is_incremental, "sweep is not incremental"
    assert first.store_label() == datetime(2026, 7, 13, tzinfo=UTC), "first is Monday after sweep start"
    assert last.store_label() == datetime(2026, 7, 14, tzinfo=UTC), "last is last_req"
    assert state_entry_2.next_sweep == datetime(2026, 7, 15, tzinfo=UTC)  # last + cadence
    assert state_entry_2.sweep_start == datetime(2026, 7, 7, tzinfo=UTC)  # last - window
    assert state_entry_2.needs_save


def test_compute_fetch_range_first_after_last(make_asset, make_series):
    fake_provider = make_fake_provider(fetch_result=Result.fail(reason="bad data"))

    asset = make_asset()
    calendar = SeriesCalendar.from_asset_metadata(asset.effective_metadata)
    assets = make_assets([asset])

    # Daily series
    series_list = [
        make_series(
            asset, interval="15m", bootstrap_history="2d", retention=Retention.LONG_LIVED, publication_offset="14m"
        )
    ]
    providers = {"yahoo": fake_provider}

    # Sunday evening, so with 2 day history we can't move back from the weekend. Next for range start is Monday after, previous for range end is Friday before
    def mock_now():
        return datetime(2026, 7, 12, 23, 50, tzinfo=UTC)

    fc = FetchController(series_list, assets.get, providers.get, now_provider=mock_now)
    series = series_list[0]

    state_entry = SeriesState()
    result = fc.get_fetch_range(series=series, provider=fake_provider, state=state_entry, calendar=calendar)

    assert result is None, "no points found (last before first)"


def test_get_sweep_start(make_asset, make_series, fixed_now):
    asset = make_asset()
    assets = make_assets([asset])
    series = [
        make_series(
            asset,
            interval="1h",
        )
    ]

    fc = make_fetch_controller(series, assets.get, fixed_now)
    state = SeriesState()
    sweep = SweepConfig.from_config(config={})
    last = CandleIdentity(value=datetime.min, is_daily=False, interval=timedelta(0))
    assert fc.get_sweep_start(state=state, sweep=sweep, last=last) is None
    now = fixed_now()
    yesterday = now - timedelta(days=1)
    state.next_sweep = now
    state.sweep_start = yesterday
    sweep.window = timedelta(days=2)
    assert fc.get_sweep_start(state=state, sweep=sweep, last=replace(last, value=now - timedelta(days=1))) is None
    assert (
        fc.get_sweep_start(state=state, sweep=sweep, last=replace(last, value=now + timedelta(days=1)))
        is state.sweep_start
    )
