# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_timescale_backend.py

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from finance.common.model import Series, SeriesPoint
from finance.timeseries.timescale_backend import TimescaleBackend

default_config = {
    "host": "host123",
    "user": "fin_user",
    "password": "s3cr3t",
    "db": "fin2",
}


def series_by_id(id: int) -> Series:
    return None


@contextmanager
def make_backend(config, execute_error=False):  # returns Result[TimescaleBackend]
    # Fake cursor
    fake_cursor = MagicMock()
    fake_cursor.execute.return_value = None

    # Fake connection
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    if execute_error:
        fake_conn.cursor.return_value.__enter__.return_value.execute.side_effect = Exception("Execute boom!")

    # Patch psycopg.connect so backend receives fake_conn
    with patch("psycopg.connect", return_value=fake_conn) as mock_connect:
        result = TimescaleBackend.from_config(config, series_by_id)

        # Attach mocks to the backend so tests can inspect them
        if result.ok:
            backend = result.payload
            backend.mock_connect = mock_connect
            backend.mock_conn = fake_conn
            backend.mock_cursor = fake_cursor
        yield result


@contextmanager
def unwrapped_backend(config, execute_error=False):
    with make_backend(config, execute_error) as result:
        yield result.payload


def test_constructor_is_pure():

    backend = TimescaleBackend(None, series_by_id)
    assert backend._connection is None
    assert backend._pending == []


def test_from_config_failure_cert(assert_error):
    config = {
        "host": "myhost",
        "port": 1234,
        "user": "finuser",
        "password": "secret",
        "db": "fin1",
        "ssl_mode": "verify-ca",
        "max_batch_size": 500,
        "max_batch_age_seconds": 2.5,
    }

    with make_backend(config) as result:
        assert_error(
            result,
            "Timescale backend initialization failed",
            "verify-ca requires path in TIMESCALEDB_SSL_ROOT_CERT in .env or ssl_root_cert in yaml",
        )


def test_from_config_success_no_defaults():
    config = {
        "host": "myhost",
        "port": 1234,
        "user": "finuser",
        "password": "secret",
        "db": "fin1",
        "ssl_mode": "verify-full",
        "max_batch_size": 500,
        "max_batch_age_seconds": 2.5,
    }

    with make_backend(config) as result:
        assert result.ok

        backend = result.payload
        timescale_config = backend._config
        assert timescale_config.host == "myhost"
        assert timescale_config.port == 1234
        assert timescale_config.user == "finuser"
        assert timescale_config.password == "secret"
        assert timescale_config.dbname == "fin1"
        assert timescale_config.sslmode == "verify-full"
        assert timescale_config.max_batch_size == 500
        assert timescale_config.max_batch_age == timedelta(seconds=2.5)

        assert backend._pending == []
        assert backend._last_flush is None
        assert backend.now is not None


def test_from_config_success_defaults():

    with make_backend(default_config) as result:
        assert result.ok

        backend = result.payload
        timescale_config = backend._config
        assert timescale_config.host == "host123"
        assert timescale_config.user == "fin_user"
        assert timescale_config.password == "s3cr3t"
        assert timescale_config.dbname == "fin2"
        assert timescale_config.port == 5432
        assert timescale_config.sslmode == "verify-full"
        assert timescale_config.max_batch_size == 1000
        assert timescale_config.max_batch_age == timedelta(seconds=2.0)

        assert backend._pending == []
        assert backend._last_flush is None
        assert backend.now is not None


def test_from_config_failure(assert_error):
    with make_backend({}) as result:
        assert_error(result, "Timescale backend initialization failed", "Cannot find mandatory config key 'host'")


def test_ensure_connected_reconnects():

    with unwrapped_backend(default_config) as backend:
        backend._connection = None

        backend.mock_connect.return_value = backend.mock_conn
        result = backend.ensure_connected()
        assert result.ok
        assert backend._connection is backend.mock_connect.return_value


def test_ensure_connected_does_not_reconnect():

    class FakeConnection:
        closed: bool = False

    with unwrapped_backend(default_config) as backend:
        backend._connection = FakeConnection()

        result = backend.ensure_connected()
        assert result.ok


def test_flush_without_pending_does_nothing():
    with unwrapped_backend(default_config) as backend:
        # the only way this can return without an error (no connection) is if pending is empty
        result = backend.flush()
        assert result.ok


def test_flush_without_connection_and_exception(fixed_now, assert_error):
    # force an immediate flush after adding via the batch size

    with unwrapped_backend(default_config | {"max_batch_size": 1}) as backend:
        now = fixed_now()
        entry = SeriesPoint(series_id=0, time=now, close=1)

        with patch("psycopg.connect") as mock_connect:
            mock_connect.side_effect = Exception("Boom!")
            result = backend.add(entry)
            assert_error(result, "Connect failed", "Boom!")


def test_add_writes_two_entries(fixed_now):

    with unwrapped_backend(default_config | {"max_batch_size": 2}) as backend:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        now = fixed_now()
        next = now + timedelta(seconds=1)
        entry1 = SeriesPoint(series_id=1, time=now, close=1)
        entry2 = SeriesPoint(series_id=2, time=next, close=1.1, volume=2)

        with patch("psycopg.connect", return_value=mock_conn):
            result = backend.add(entry1)
            assert result.ok, "First add"
            assert len(backend._pending) == 1
            mock_cursor.executemany.assert_not_called()
            result = backend.add(entry2)
            assert result.ok, "second add"
            mock_cursor.executemany.assert_called()
            assert backend._pending == []


def test_close_writes(fixed_now):

    with unwrapped_backend(default_config | {"max_batch_size": 2}) as backend:
        # mock_conn = MagicMock()
        # mock_cursor = MagicMock()

        # mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        now = fixed_now()
        entry1 = SeriesPoint(series_id=1, time=now, close=1)

        # with patch("psycopg.connect", return_value=mock_conn):
        result = backend.add(entry1)
        assert result.ok, "add"
        assert len(backend._pending) == 1
        result = backend.close()
        assert result.ok, "close"
        backend.mock_cursor.executemany.assert_called()
        assert backend._pending == []


def test_flush_writes_when_batch_too_old(fixed_now):

    with unwrapped_backend(default_config | {"max_batch_age_seconds": 0}) as backend:
        now = fixed_now()
        entry = SeriesPoint(series_id=1, time=now, close=1)

        result = backend.add(entry)

        assert result.ok
        backend.mock_cursor.executemany.assert_called()
        assert backend._pending == []


def test_flush_raises_in_context_manager(fixed_now, assert_error):

    with unwrapped_backend(default_config | {"max_batch_size": 1}) as backend:
        # mock cursor context manager
        mock_cursor_cm = MagicMock()
        mock_cursor_cm.__enter__.side_effect = Exception("Cursor boom!")
        backend.mock_conn.cursor.return_value = mock_cursor_cm

        entry = SeriesPoint(series_id=1, time=fixed_now(), close=1)

        # patch connect so ensure_connected() returns our mock_conn
        # with patch("psycopg.connect", return_value=mock_conn):
        result = backend.add(entry)

        assert_error(result, "Database startup failed", "Cursor boom!")


# -------------------------
# Read first and read last
# -------------------------


def make_mock_cursor(rows):
    """
    Helper that returns a mock cursor context manager
    whose cursor.fetchone() returns the given rows.
    """
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = rows

    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_cursor
    mock_cm.__exit__.return_value = False
    return mock_cm


def test_read_first_returns_candle_row(fixed_now):

    with unwrapped_backend(default_config) as backend:
        now = fixed_now()
        mock_cursor_cm = make_mock_cursor(rows=[(1, now, 10, 12, 8, 11, 1000)])
        backend.mock_conn.cursor.return_value = mock_cursor_cm

        result = backend.read_first(1)

        assert result.ok
        assert result.payload == SeriesPoint(series_id=1, time=now, open=10, high=12, low=8, close=11, volume=1000)


def test_read_first_returns_value_row(fixed_now):
    with unwrapped_backend(default_config) as backend:
        backend._intraday_series_ids = {1}
        now = fixed_now()
        mock_cursor_cm = make_mock_cursor(rows=[(1, now, None, None, None, 15, None)])
        backend.mock_conn.cursor.return_value = mock_cursor_cm

        result = backend.read_first(1)

        assert result.ok
        assert result.payload == SeriesPoint(series_id=1, time=now, close=15)


def test_read_first_returns_none_when_empty():
    with unwrapped_backend(default_config) as backend:
        mock_cursor_cm = make_mock_cursor(rows=[None])  # fetchone() returns None
        backend.mock_conn.cursor.return_value = mock_cursor_cm

        result = backend.read_first(1)

        assert result.ok
        assert result.payload is None


def test_read_first_handles_db_error(unwrap):
    with unwrapped_backend(default_config) as backend:
        backend.mock_conn.cursor.side_effect = Exception("boom")

        result = backend.read_first(1)

        assert not result.ok
        assert "boom" in result.error


def test_read_first_rejects_empty_id(unwrap, assert_error):
    with unwrapped_backend(default_config) as backend:
        mock_cursor_cm = make_mock_cursor(rows=[None])  # fetchone() returns None
        backend.mock_conn.cursor.return_value = mock_cursor_cm
        result = backend.read_first(None)

        assert_error(result, "Series id not set for Read first", None)


def test_read_last_returns_daily_value_point(unwrap, fixed_now):
    with unwrapped_backend(default_config) as backend:
        now = fixed_now()
        midnight_today = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)
        mock_cursor_cm = make_mock_cursor(rows=[(1, midnight_today, None, None, None, 11, None)])
        backend.mock_conn.cursor.return_value = mock_cursor_cm

        result = backend.read_last(1)

        assert result.ok
        assert result.payload == SeriesPoint(series_id=1, time=midnight_today, close=11)


def test_fail_on_execute(assert_error):
    with make_backend(default_config, execute_error=True) as result:
        assert_error(result, "Database startup failed", "Execute boom!")
