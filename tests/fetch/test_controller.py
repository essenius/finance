# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_controller.py

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from finance.common.asset_metadata import AssetMetadata
from finance.common.guards import require
from finance.common.model import Asset, FetchData, Series, SeriesState, SweepConfig
from finance.common.string_enums import Retention
from finance.common.time_utils import UTC, snap_to
from finance.common.types import Success, Unwrap
from finance.fetch.controller import FetchController
from finance.state.state import State
from tests.support.types import AssertError, Creator, Factory

# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_controller_skips_fresh(
    make_asset: Creator[Asset], make_provider: Creator[Mock], make_series: Creator[Series], state: State
):
    provider = make_provider()
    asset = make_asset(provider=provider)
    series = make_series(asset, interval="1h")

    def fake_now():
        # this is a Wednesday
        return datetime(2025, 6, 11, 15, 6, 40, tzinfo=UTC)

    fc = FetchController(now_provider=fake_now)

    now = fake_now()
    last = snap_to(now, timedelta(hours=1))
    first = last - timedelta(days=6)  # we want 5 days, we have 6
    state.series_state.clear()
    state.series_state[1] = SeriesState(first_point=first, last_point=last)

    results = list(fc.fetch_incrementally([series], state))
    assert results == []
    provider.fetch.assert_not_called()


def test_controller_fetch_when_oldest_too_new(
    make_asset: Creator[Asset], make_provider: Creator[Mock], make_series: Creator[Series], state: State
):
    provider = make_provider()
    asset = make_asset(provider=provider)
    series = make_series(asset, interval="1h")
    provider.fetch.return_value = Success(FetchData(require(series.id), series, points=[]))

    def fake_now():
        # this is a Wednesday
        return datetime(2025, 6, 11, 15, 6, 40, tzinfo=UTC)

    fc = FetchController(now_provider=fake_now)

    now = fake_now()

    last = snap_to(now, timedelta(hours=1))
    first = last - timedelta(days=1)  # we want 5 days, we have 1

    state.series_state.clear()
    state.series_state[1] = SeriesState(last_point=last, first_point=first)
    results = list(fc.fetch_incrementally([series], state))
    assert provider.fetch.call_count == 1
    assert len(results) == 1
    assert results[0].ok is True


def test_controller_fetches_when_stale(
    fixed_now: Factory[datetime],
    make_asset: Creator[Asset],
    make_provider: Creator[Mock],
    make_series: Creator[Series],
    state: State,
):
    provider = make_provider()
    asset = make_asset(provider=provider)
    series = make_series(asset, interval="1h")
    provider.fetch.return_value = Success(FetchData(require(series.id), series, points=[]))

    fc = FetchController(now_provider=fixed_now)
    now = fixed_now()
    state.series_state.clear()

    # stale vs 1h
    state.series_state[1] = SeriesState(first_point=now - timedelta(weeks=1), last_point=now - timedelta(days=2))

    results = list(fc.fetch_incrementally([series], state))
    assert provider.fetch.call_count == 1
    assert len(results) == 1
    assert results[0].ok is True


def test_controller_skips_fetch_with_offset(
    make_asset: Creator[Asset],
    make_metadata: Creator[AssetMetadata],
    make_provider: Creator[Mock],
    make_series: Creator[Series],
    state: State,
):
    fake_hour = 12

    def fake_now():
        return datetime(2026, 7, 23, fake_hour, 40, tzinfo=UTC)

    provider = make_provider()
    meta = make_metadata(timezone=ZoneInfo("Europe/Berlin"))
    asset = make_asset(provider=provider, effective_metadata=meta)
    series = make_series(asset, interval="1d", publication_offset="16h")

    fc = FetchController(now_provider=fake_now)
    now = fake_now()
    today = datetime.combine(now.date(), time.min, UTC)
    state.series_state.clear()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(weeks=1)
    # should not retrieve as publication time not passed yet
    state.series_state[1] = SeriesState(first_point=last_week, last_point=yesterday)
    results = list(fc.fetch_incrementally([series], state))
    assert provider.fetch.call_count == 0
    assert len(results) == 0, "no result as publication time not passed"

    # should retrieve as publication time passed passed
    fake_hour = 15
    results = list(fc.fetch_incrementally([series], state))
    assert len(results) == 1, "result as publication time passed"


def test_controller_malformed_result(
    assert_error: AssertError,
    fixed_now: Factory[datetime],
    make_asset: Creator[Asset],
    make_provider: Creator[Mock],
    make_series: Creator[Series],
    state: State,
):
    provider = make_provider()
    asset = make_asset(provider=provider)
    series = [make_series(asset)]

    fc = FetchController(now_provider=fixed_now)

    results = list(fc.fetch_incrementally(series, state))
    assert len(results) == 1
    assert_error(results[0], "default failure", None)


def test_controller_none_limit(
    fixed_now: Factory[datetime],
    make_asset: Creator[Asset],
    make_provider: Creator[Mock],
    make_series: Creator[Series],
    state: State,
    unwrap: Unwrap[FetchData],
):
    provider = make_provider()
    asset = make_asset(provider=provider)
    series = make_series(asset)
    provider.provider_config._get_history_limit.return_value = None

    fc = FetchController(now_provider=fixed_now)
    results = list(fc.fetch_incrementally([series], state))
    assert provider.fetch.call_count == 1
    assert len(results) == 1
    assert results[0].ok is False


def test_controller_multiple_assets(
    fixed_now: Factory[datetime],
    make_asset: Creator[Asset],
    make_provider: Creator[Mock],
    make_series: Creator[Series],
    state: State,
):
    provider = make_provider()
    asset1 = make_asset(name="eur_usd_yahoo", provider=provider)
    series1 = make_series(asset1)

    provider.fetch.side_effect = [
        Success([]),
        Success([]),
    ]

    asset2 = make_asset(id=2, name="spx_yahoo", provider=provider, provider_code="^GSPC")
    series = [series1, make_series(asset2)]

    fc = FetchController(now_provider=fixed_now)

    results = list(fc.fetch_incrementally(series, state))
    assert len(results) == 2

    assert provider.fetch.call_count == 2
    assert 1 in state.series_state
    assert 2 in state.series_state


def test_compute_fetch_range_intraday(
    make_asset: Creator[Asset], make_provider: Creator[Mock], make_series: Creator[Series]
):
    provider = make_provider()
    asset = make_asset(provider=provider)
    series = make_series(asset)  # 10m interval
    assert asset.effective_metadata is not None

    def mock_now():
        return datetime(2026, 7, 15, 15, 30, tzinfo=UTC)

    fc = FetchController(now_provider=mock_now)

    # Plain incremental (one new point)

    state_entry_1 = SeriesState(
        first_point=datetime(2026, 6, 15, tzinfo=UTC), last_point=datetime(2026, 7, 15, 15, 10, tzinfo=UTC)
    )

    result = fc._get_fetch_range(series=series, state=state_entry_1)
    assert result is not None, "1st: intraday publication expected"
    first, last, is_incremental = result
    assert is_incremental, "1st: is incremental"
    assert first.store_label() == datetime(2026, 7, 15, 15, 20, tzinfo=UTC)
    assert last.store_label() == datetime(2026, 7, 15, 15, 20, tzinfo=UTC)

    assert state_entry_1.needs_save is True
    assert state_entry_1.sweep_start == datetime(2026, 7, 8, 15, 20, tzinfo=UTC)  # 1 week back (config is 7d, 1d)
    assert state_entry_1.next_sweep == datetime(2026, 7, 16, 15, 20, tzinfo=UTC)  # next day

    # No new points

    state_entry_2 = SeriesState(
        first_point=datetime(2026, 6, 15, tzinfo=UTC), last_point=datetime(2026, 7, 15, 15, 20, tzinfo=UTC)
    )
    result = fc._get_fetch_range(series=series, state=state_entry_2)
    assert result is None, "2nd: intraday publication not expected"

    # older history to fetch

    state_entry_3 = SeriesState(
        first_point=datetime(2026, 7, 13, tzinfo=UTC), last_point=datetime(2026, 7, 15, 15, 20, tzinfo=UTC)
    )

    result = fc._get_fetch_range(series=series, state=state_entry_3)
    assert result is not None, "3rd: intraday publication expected"
    first, last, is_incremental = result
    assert not is_incremental, "3rd: not incremental"
    assert first.store_label() == datetime(2026, 7, 10, 15, 30, tzinfo=UTC), "3rd: first is before saved range"
    assert last.store_label() == datetime(2026, 7, 10, 23, 50, tzinfo=UTC), "3rd: last is before saved range"

    long_lived_series = replace(series, retention=Retention.LONG_LIVED)
    result = fc._get_fetch_range(series=long_lived_series, state=state_entry_3)
    assert result is not None, "3rd: intraday insufficient history"

    # start with the point that didn't expect publication and enable sweeps
    provider.sweep_config.return_value = SweepConfig(window=timedelta(days=1), cadence=timedelta(hours=1))
    state_entry_2.next_sweep = state_entry_2.last_point
    state_entry_2.sweep_start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)  # a Saturday
    result = fc._get_fetch_range(series=series, state=state_entry_2)

    assert result is not None, "sweep: publication expected"
    first, last, is_incremental = result
    assert is_incremental, "sweep: incremental"
    assert first.store_label() == datetime(2026, 7, 13, 15, 30, tzinfo=UTC), "sweep: first == sweep start"
    assert last.store_label() == datetime(2026, 7, 15, 15, 20, tzinfo=UTC), "sweep: last == last_req"
    assert state_entry_2.next_sweep == datetime(2026, 7, 15, 16, 20, tzinfo=UTC), "sweep: next == last + cadence"
    assert state_entry_2.sweep_start == datetime(2026, 7, 14, 15, 20, tzinfo=UTC), "sweep: start == last - window"
    assert state_entry_2.needs_save, "sweep: needs save"


def test_compute_fetch_range_daily(
    make_asset: Creator[Asset],
    make_metadata: Creator[AssetMetadata],
    make_provider: Creator[Mock],
    make_series: Creator[Series],
):
    provider = make_provider()
    meta = make_metadata(first_available_date=date(2021, 10, 1))
    asset = make_asset(provider=provider, effective_metadata=meta)
    series = make_series(
        asset, interval="1d", bootstrap_history="5y", retention=Retention.LONG_LIVED.value, retention_period=None
    )

    assert asset.effective_metadata is not None

    # Daily series. Set first available date less than 5 years ago to test it is respected.
    def mock_now():
        return datetime(2026, 7, 15, 13, 30, tzinfo=UTC)

    fc = FetchController(now_provider=mock_now)

    # --- Publication expected (last_point behind)
    state_entry_1 = SeriesState(
        first_point=datetime(2021, 10, 1, tzinfo=UTC), last_point=datetime(2026, 7, 13, tzinfo=UTC)
    )
    result = fc._get_fetch_range(series=series, state=state_entry_1)

    assert result is not None, "1st: daily publication expected"
    first, last, is_incremental = result
    assert is_incremental, "1 is incremental"
    assert first.store_label() == datetime(2026, 7, 14, tzinfo=UTC), "1st: 14th is first"
    assert last.store_label() == datetime(2026, 7, 14, tzinfo=UTC), "1st: 15th not yet, as not finished"
    assert state_entry_1.needs_save, "needs save as sweep updated"

    # --- Publication NOT expected (last_point == today)
    state_entry_2 = SeriesState(
        first_point=datetime(2021, 10, 1, tzinfo=UTC), last_point=datetime(2026, 7, 14, tzinfo=UTC)
    )
    result = fc._get_fetch_range(series=series, state=state_entry_2)
    assert result is None, "2nd: daily publication not expected"

    # Insufficient history (first_point too recent)
    state_entry_3 = SeriesState(
        first_point=datetime(2021, 10, 5, tzinfo=UTC), last_point=datetime(2026, 7, 14, tzinfo=UTC)
    )
    # first_req is Fri 2021-10-01 < last_not_fetched, so there is prepend history
    result = fc._get_fetch_range(series=series, state=state_entry_3)

    assert result is not None, "3rd: daily insufficient history"
    first, last, is_incremental = result
    assert not is_incremental, "3rd: not incremental"
    assert first.store_label() == datetime(2021, 10, 1, tzinfo=UTC), "3rd: first is before range"
    assert last.store_label() == datetime(2021, 10, 4, tzinfo=UTC), "3rd: last is before range"

    state_entry_2.next_sweep = state_entry_2.last_point
    state_entry_2.sweep_start = datetime(2026, 7, 11, tzinfo=UTC)  # a Saturday
    result = fc._get_fetch_range(series=series, state=state_entry_2)

    assert result is not None, "sweep publication expected"
    first, last, is_incremental = result
    assert is_incremental, "sweep is incremental"
    assert first.store_label() == datetime(2026, 7, 13, tzinfo=UTC), "first is Monday after sweep start"
    assert last.store_label() == datetime(2026, 7, 14, tzinfo=UTC), "last is last_req"
    assert state_entry_2.next_sweep == datetime(2026, 7, 15, tzinfo=UTC)  # last + cadence
    assert state_entry_2.sweep_start == datetime(2026, 7, 7, tzinfo=UTC)  # last - window
    assert state_entry_2.needs_save


def test_compute_fetch_range_first_after_last(
    make_asset: Creator[Asset], make_provider: Creator[Mock], make_series: Creator[Series]
):
    provider = make_provider()
    asset = make_asset(provider=provider)
    # Daily series
    series = make_series(
        asset, interval="15m", bootstrap_history="2d", retention=Retention.LONG_LIVED.value, publication_offset="14m"
    )
    assert asset.effective_metadata is not None

    # Sunday evening, so with 2 day history we can't move back from the weekend. Next for range start is Monday after, previous for range end is Friday before
    def mock_now():
        return datetime(2026, 7, 12, 23, 50, tzinfo=UTC)

    fc = FetchController(now_provider=mock_now)

    state_entry = SeriesState()
    result = fc._get_fetch_range(series=series, state=state_entry)

    assert result is None, "no points found (last before first)"
