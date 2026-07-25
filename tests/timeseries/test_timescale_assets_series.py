# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_timescale_assets_series.py

from datetime import datetime
from unittest.mock import MagicMock

from finance.common.result import Result
from finance.common.string_enums import Retention, SeriesType
from finance.timeseries.timescale_backend import TimescaleBackend

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


def test_refresh_short_lived_series_ids_loads_ids(make_backend):
    backend = make_backend()
    backend._connection.closed = False
    # rows returned by _execute_read
    backend._execute_read = MagicMock(
        return_value=[
            (10,),
            (20,),
            (30,),
        ]
    )

    backend.refresh_short_lived_series_ids()

    assert backend._short_lived_series_ids == {10, 20, 30}
    backend._execute_read.assert_called_once()
    assert "short_lived" in backend._execute_read.call_args[0][0]


def test_refresh_short_lived_series_ids_handles_empty(make_backend):
    backend = make_backend()
    backend._connection.closed = False

    backend._execute_read = MagicMock(return_value=[])

    backend.refresh_short_lived_series_ids()

    assert backend._short_lived_series_ids == set()


# ------------------------------------------------------------
# store_asset
# ------------------------------------------------------------


def test_store_asset_insert(make_backend, make_asset):
    backend = make_backend()
    backend._connection.closed = False

    asset = make_asset(id=None)

    backend._execute_write = MagicMock(return_value=Result.ok_payload(42))

    result = backend.store_asset(asset)

    assert result.ok
    stored = result.payload
    assert stored.id == 42

    backend._execute_write.assert_called_once()
    sql, params = backend._execute_write.call_args[0]
    assert "INSERT INTO asset" in sql
    assert params[0] == "eur_usd"
    assert params[2] == "yahoo"


def test_store_asset_update(make_backend, make_asset):
    backend = make_backend()
    backend._connection.closed = False

    asset = make_asset(id=99)

    backend._execute_write = MagicMock(return_value=Result.ok_payload(99))
    result = backend.store_asset(asset)

    assert result.ok
    assert result.payload is asset  # unchanged object

    backend._execute_write.assert_called_once()
    sql, params = backend._execute_write.call_args[0]
    assert "UPDATE asset" in sql
    assert params[-1] == 99


def test_store_asset_error_propagates(make_backend, make_asset, assert_error):
    backend = make_backend()
    backend._connection.closed = False

    asset = make_asset(id=None)

    backend._execute_write = MagicMock(return_value=Result.fail("boom"))

    result = backend.store_asset(asset)
    assert_error(result, "boom", None)


# ------------------------------------------------------------
# store_series
# ------------------------------------------------------------


def test_store_series_insert(make_backend, make_asset, make_series):
    backend = make_backend()
    backend._connection.closed = False

    asset = make_asset(id=5)
    series = make_series(asset=asset, id=None)
    backend._execute_write = MagicMock(return_value=Result.ok_payload(123))

    result = backend.store_series(series)

    assert result.ok
    stored = result.payload
    assert stored.id == 123

    backend._execute_write.assert_called_once()
    sql, params = backend._execute_write.call_args[0]
    assert "INSERT INTO series" in sql
    assert params[0] == "dummy"
    assert params[1] == 5


def test_store_series_update(make_backend, make_asset, make_series):
    backend = make_backend()
    backend._connection.closed = False
    asset = make_asset(id=5)
    series = make_series(asset=asset, id=77)

    backend._execute_write = MagicMock(return_value=Result.ok_payload(77))

    result = backend.store_series(series)

    assert result.ok
    assert result.payload is series

    backend._execute_write.assert_called_once()
    sql, params = backend._execute_write.call_args[0]
    assert "UPDATE series" in sql
    assert params[-1] == 77


def test_store_series_error_execute(assert_error, make_backend, make_asset, make_series):
    backend = make_backend()
    backend._connection.closed = False

    asset = make_asset(id=5)
    series = make_series(asset=asset, id=None)

    backend._execute_write = MagicMock(return_value=Result.fail("fail"))

    result = backend.store_series(series)
    assert_error(result, "fail", None)


def test_store_series_error_no_asset_id(assert_error, make_backend, make_asset, make_series):
    backend = make_backend()
    asset = make_asset(id=None)
    series = make_series(asset=asset, id=None)

    result = backend.store_series(series)
    assert_error(result, "Store series failed", "asset_id was not set")


# ------------------------------------------------------------
# get_assets
# ------------------------------------------------------------


def test_get_assets_returns_asset_list(make_backend):
    backend = make_backend()
    backend._connection.closed = False
    rows = [
        (1, "AAPL", "AAPL", "yahoo", "AAPL", "Apple Inc.", "stock", "US", "NASDAQ", "USD", "share"),
        (2, "MSFT", "MSFT", "yahoo", "MSFT", "Microsoft Corporation", "stock", "US", "NASDAQ", "USD", "share"),
    ]

    cursor_cm = make_cursor(fetchall=rows)
    backend._connection.cursor.return_value = cursor_cm

    result = backend.get_assets()

    assert result.ok
    assets = result.payload
    assert len(assets) == 2
    assert assets[0].symbol == "AAPL"
    assert assets[1].symbol == "MSFT"


def test_get_assets_error(assert_error, make_backend):
    backend = make_backend()
    backend._connection.closed = False

    backend._connection.cursor.side_effect = Exception("db error")

    result = backend.get_assets()
    assert_error(result, "get_assets operation failed", "db error")


# ------------------------------------------------------------
# get_series
# ------------------------------------------------------------


def test_get_series_returns_series_list(make_backend):
    backend: TimescaleBackend = make_backend()
    backend._connection.closed = False

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
            "Europe/Berlin",
            "1m",
            "min",
            "max",
            "sun",
            "sat",
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
            "1y",
            "UTC",
            "1d",
            "9:00",
            "17:00",
            "mon",
            "fri",
        ),
    ]

    cursor_cm = make_cursor(fetchall=rows)
    backend._connection.cursor.return_value = cursor_cm

    result = backend.get_series()

    assert result.ok
    series = result.payload
    assert len(series) == 2
    assert series[0].retention == Retention.SHORT_LIVED
    assert series[1].series_type == SeriesType.CANDLE
    assert series[1].publication_offset == "1d"


def test_get_series_error(assert_error, make_backend):
    backend = make_backend()
    backend._connection.cursor.side_effect = Exception("boom")
    result = backend.get_series()
    assert_error(result, "get_series operation failed", "boom")


def test_execute_read_returns_rows(make_backend):
    backend = make_backend()

    # mock cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [(1, "AAPL"), (2, "MSFT")]

    backend._connection.cursor.return_value = mock_cursor

    rows = backend._execute_read("SELECT * FROM asset WHERE id > %s", (10,))

    assert rows == [(1, "AAPL"), (2, "MSFT")]

    backend._connection.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once_with("SELECT * FROM asset WHERE id > %s", (10,))
    mock_cursor.fetchall.assert_called_once()
    mock_cursor.close.assert_called_once()


def test_execute_write_success(make_backend):
    backend = make_backend()

    # mock cursor context manager
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [42]

    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_cursor
    mock_cm.__exit__.return_value = False

    backend._connection.cursor.return_value = mock_cm

    # capture the operation passed into _database_operation
    def fake_db_op(operation, label):
        return operation()

    backend._database_operation = fake_db_op

    result = backend._execute_write("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;", ("AAPL",))

    assert result.ok
    assert result.payload == 42

    mock_cursor.execute.assert_called_once_with("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;", ("AAPL",))
    mock_cursor.fetchone.assert_called_once()


def test_save_sweep(unwrapped_backend):
    with unwrapped_backend(default_config) as backend:
        backend.mock_cursor.fetchone.return_value = [42]

        next_sweep = datetime.max
        sweep_start = datetime.min
        result = backend.save_sweep(series_id=42, next_sweep=next_sweep, sweep_start=sweep_start)

    assert result.ok
    assert result.payload == 42
    assert backend.mock_cursor.execute.call_count == 3
    assert backend.mock_cursor.execute.call_args_list[2].args[1] == (42, datetime.max, datetime.min)
