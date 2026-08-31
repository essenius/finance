# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_timescale_assets_series.py

from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg

from finance.common.model import Asset, Series
from finance.common.string_enums import Retention, SeriesType
from finance.common.types import Failure, Success
from tests.support.fakes import FakeBackend
from tests.support.types import AssertError, Creator

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

default_config = {
    "host": "host123",
    "user": "fin_user",
    "password": "s3cr3t",
    "db": "fin2",
}


def make_cursor(fetchone=None, fetchall=None):
    """
    Returns a mock cursor context manager with configurable fetchone/fetchall.
    """
    cursor = MagicMock()
    if fetchone is not None:
        cursor.fetchone.return_value = fetchone
    if fetchall is not None:
        cursor.fetchall.return_value = fetchall

    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    return cm


# ------------------------------------------------------------
# refresh_short_lived_series_ids
# ------------------------------------------------------------


def test_refresh_short_lived_series_ids_loads_ids(make_backend: Creator[FakeBackend]):
    backend, sql = make_backend().with_sql()
    sql.execute_read = MagicMock(return_value=Success({"rows": [(10,), (20,), (30,)]}))

    result = backend.refresh_short_lived_series_ids()

    assert result.ok is True
    assert backend._short_lived_series_ids == {10, 20, 30}
    sql.execute_read.assert_called_once()
    assert "short_lived" in sql.execute_read.call_args[0][0]


def test_refresh_short_lived_series_ids_handles_empty(make_backend: Creator[FakeBackend]):
    backend, sql = make_backend().with_sql()
    sql.execute_read = MagicMock(return_value=Success({"rows": []}))

    backend.refresh_short_lived_series_ids()

    assert backend._short_lived_series_ids == set()


def test_refresh_short_lived_series_ids_handles_disconnected(make_backend: Creator[FakeBackend]):
    # initially connected
    backend, sql = make_backend().with_sql()
    # but execute read fails
    sql.execute_read = MagicMock(return_value=Failure(reason="boom"))

    result = backend.refresh_short_lived_series_ids()

    assert result.ok is False
    assert result.reason == "boom"
    assert backend._short_lived_series_ids == set()


# ------------------------------------------------------------
# store_asset
# ------------------------------------------------------------


def test_store_asset_insert(make_asset: Creator[Asset], make_backend: Creator[FakeBackend]):
    backend, sql = make_backend().with_sql()

    asset: Asset = make_asset(id=None)
    sql.execute_write = MagicMock(return_value=Success(42))

    result = backend.store_asset(asset)

    assert result.ok is True
    stored = result.payload
    assert stored.id == 42

    sql.execute_write.assert_called_once()
    query, params = sql.execute_write.call_args[0]
    assert "INSERT INTO asset" in query
    assert params[0] == "eur_usd"
    assert params[2] == "yahoo"


def test_store_asset_update(make_asset: Creator[Asset], make_backend: Creator[FakeBackend]):
    backend, sql = make_backend().with_sql()

    asset = make_asset(id=99)
    sql.execute_write = MagicMock(return_value=Success(99))
    result = backend.store_asset(asset)

    assert result.ok is True
    assert result.payload is asset  # unchanged object

    sql.execute_write.assert_called_once()
    sql, params = sql.execute_write.call_args[0]
    assert "UPDATE asset" in sql
    assert params[-1] == 99


def test_store_asset_error_propagates(
    assert_error: AssertError, make_asset: Creator[Asset], make_backend: Creator[FakeBackend]
):
    backend, sql = make_backend().with_sql()
    asset = make_asset(id=None)

    sql.execute_write = MagicMock(return_value=Failure(reason="boom"))

    result = backend.store_asset(asset)
    assert_error(result, "boom", None)


# ------------------------------------------------------------
# store_series
# ------------------------------------------------------------


def test_store_series_insert(
    make_asset: Creator[Asset], make_backend: Creator[FakeBackend], make_series: Creator[Series]
):
    backend, sql = make_backend().with_sql()

    asset = make_asset(id=5)
    series = make_series(asset=asset, id=None)
    sql.execute_write = MagicMock(return_value=Success(123))

    result = backend.store_series(series)

    assert result.ok is True
    stored = result.payload
    assert stored.id == 123

    write_mock = sql.execute_write
    write_mock.assert_called_once()
    sql, params = write_mock.call_args[0]
    assert "INSERT INTO series" in sql
    assert params[0] == "dummy"
    assert params[1] == 5
    kwargs = write_mock.call_args.kwargs
    assert kwargs.get("context") == "store series"


def test_store_series_update(
    make_asset: Creator[Asset], make_backend: Creator[FakeBackend], make_series: Creator[Series]
):
    backend, sql = make_backend().with_sql()
    asset = make_asset(id=5)
    series = make_series(asset=asset, id=77)

    sql.execute_write = MagicMock(return_value=Success(77))

    result = backend.store_series(series)

    assert result.ok is True
    assert result.payload is series

    write_mock = sql.execute_write

    write_mock.assert_called_once()
    sql, params = write_mock.call_args[0]
    assert "UPDATE series" in sql
    assert params[-1] == 77
    kwargs = write_mock.call_args.kwargs
    assert kwargs.get("context") == "store series"


def test_store_series_error_execute(
    assert_error: AssertError,
    make_asset: Creator[Asset],
    make_backend: Creator[FakeBackend],
    make_series: Creator[Series],
):
    backend, sql = make_backend().with_sql()
    asset = make_asset(id=5)
    series = make_series(asset=asset, id=None)

    sql.execute_write = MagicMock(return_value=Failure(reason="fail"))

    result = backend.store_series(series)
    assert_error(result, "fail", None)


def test_store_series_error_no_asset_id(
    assert_error: AssertError,
    make_backend: Creator[FakeBackend],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):
    backend = make_backend().only()
    asset = make_asset(id=None)
    series = make_series(asset=asset, id=None)

    result = backend.store_series(series)
    assert_error(result, "Store series failed", "asset_id was not set")


# ------------------------------------------------------------
# get_assets
# ------------------------------------------------------------


def test_get_assets_returns_asset_list(make_backend: Creator[FakeBackend]):
    backend, cursor = make_backend().with_cursor()
    rows = [
        (
            1,
            "AAPL",
            "AAPL",
            "yahoo",
            "AAPL",
            "Apple Inc.",
            "Apple Incorporated",
            "stock",
            "US",
            "NASDAQ",
            "USD",
            "share",
            "America/New_York",
            None,
            "mon",
            "fri",
            "9:30",
            "16:00",
        ),
        (
            2,
            "MSFT",
            "MSFT",
            "yahoo",
            "MSFT",
            "Microsoft",
            "Microsoft Corporation",
            "stock",
            "US",
            "NASDAQ",
            "USD",
            "share",
            "America/New_York",
            None,
            "sun",
            "sat",
            "min",
            "max",
        ),
    ]

    cursor.description = [
        SimpleNamespace(name="id"),
        SimpleNamespace(name="name"),
        SimpleNamespace(name="symbol"),
        SimpleNamespace(name="provider"),
        SimpleNamespace(name="provider_code"),
        SimpleNamespace(name="long_name"),
        SimpleNamespace(name="short_name"),
        SimpleNamespace(name="instrument"),
        SimpleNamespace(name="region"),
        SimpleNamespace(name="exchange"),
        SimpleNamespace(name="currency"),
        SimpleNamespace(name="unit"),
        SimpleNamespace(name="timezone"),
        SimpleNamespace(name="first_available_date"),
        SimpleNamespace(name="week_start"),
        SimpleNamespace(name="week_end"),
        SimpleNamespace(name="market_open"),
        SimpleNamespace(name="market_close"),
    ]
    cursor.fetchall.return_value = rows

    result = backend.get_assets()

    assert result.ok is True
    assets: list[Asset] = result.payload
    assert len(assets) == 2
    assert assets[0].symbol == "AAPL"
    assert assets[1].symbol == "MSFT"
    meta0 = assets[0].effective_metadata
    assert meta0 is not None
    assert meta0.timezone is not None
    assert meta0.timezone.key == "America/New_York"
    meta1 = assets[1].effective_metadata
    assert meta1 is not None
    assert meta1.week_start == "sun"
    assert meta0.market_close == time(hour=16)


def test_get_assets_error(assert_error: AssertError, make_backend: Creator[FakeBackend]):
    backend, connection = make_backend().with_connection()
    connection.cursor.side_effect = psycopg.Error("db error")

    result = backend.get_assets()

    assert_error(result, "get_assets operation failed", "db error")


# ------------------------------------------------------------
# get_series
# ------------------------------------------------------------


def test_get_series_returns_series_list(make_backend: Creator[FakeBackend]):
    backend, connection = make_backend().with_connection()

    rows = [
        (
            10,
            "intraday",
            1,
            "SPX",
            "SPX:intraday",
            "1m",
            "value",
            "short_lived",
            "30d",
            "30d",
            None,
        ),
        (
            11,
            "daily",
            1,
            "SPX",
            "SPX:daily",
            "1d",
            "candle",
            "long_lived",
            None,
            "1y",
            "1d",
        ),
    ]

    cursor_cm = make_cursor(fetchall=rows)

    inner_cursor = cursor_cm.__enter__.return_value
    inner_cursor.description = [
        SimpleNamespace(name="id"),
        SimpleNamespace(name="code"),
        SimpleNamespace(name="asset_id"),
        SimpleNamespace(name="asset_name"),
        SimpleNamespace(name="name"),
        SimpleNamespace(name="interval"),
        SimpleNamespace(name="series_type"),
        SimpleNamespace(name="retention"),
        SimpleNamespace(name="retention_period"),
        SimpleNamespace(name="bootstrap_history"),
        SimpleNamespace(name="publication_offset"),
    ]
    connection.cursor.return_value = cursor_cm

    result = backend.get_series()

    assert result.ok is True
    series = result.payload
    assert len(series) == 2
    assert series[0].retention == Retention.SHORT_LIVED
    assert series[1].series_type == SeriesType.CANDLE
    assert series[1].publication_offset == "1d"


def test_get_series_error(assert_error: AssertError, make_backend: Creator[FakeBackend]):
    backend, connection = make_backend().with_connection()
    connection.cursor.side_effect = psycopg.Error("boom")
    result = backend.get_series()
    assert_error(result, "get_series operation failed", "boom")


def test_save_sweep(make_backend: Creator[FakeBackend]):
    fake_backend = make_backend(fetchone=[42])
    backend = fake_backend.backend
    next_sweep = datetime.max
    sweep_start = datetime.min
    result = backend.save_sweep(series_id=42, next_sweep=next_sweep, sweep_start=sweep_start)
    assert result.ok is True
    assert result.payload == 42
    cursor = fake_backend.fake_sql.cursor
    cursor.execute.assert_called_once()
    assert cursor.execute.call_args_list[0].args[1] == (42, datetime.max, datetime.min)
