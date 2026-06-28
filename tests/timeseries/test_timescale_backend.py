# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_timescale_backend.py

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from finance.common.model import CandlePoint, DailyValuePoint, IntradayPoint, SeriesPoint
from finance.timeseries.timescale_backend import TimescaleBackend

default_config = {
    "host": "host123",
    "user": "fin_user",
    "password": "s3cr3t",
    "db": "fin2",
}


def test_constructor_is_pure():
    backend = TimescaleBackend(None)
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

    result = TimescaleBackend.from_config(config)

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

    result = TimescaleBackend.from_config(config)

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

    assert backend._connection is None
    assert backend._pending == []
    assert backend._last_flush is None
    assert backend.now is not None


def test_from_config_success_defaults():

    result = TimescaleBackend.from_config(default_config)

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

    assert backend._connection is None
    assert backend._pending == []
    assert backend._last_flush is None
    assert backend.now is not None


def test_from_config_failure(assert_error):
    result = TimescaleBackend.from_config({})
    assert_error(result, "Timescale backend initialization failed", "Cannot find mandatory config key 'host'")


def test_ensure_connected_reconnects(unwrap):

    backend = unwrap(TimescaleBackend.from_config(default_config))
    backend._connection = None

    with patch("psycopg.connect") as mock_connect:
        mock_connect.return_value = object()
        result = backend.ensure_connected()
        assert result.ok
        assert backend._connection is mock_connect.return_value


def test_ensure_connected_does_not_reconnect(unwrap):

    class FakeConnection:
        closed: bool = False

    backend = unwrap(TimescaleBackend.from_config(default_config))
    backend._connection = FakeConnection()

    result = backend.ensure_connected()
    assert result.ok


def test_flush_without_pending_does_nothing(unwrap):
    backend = unwrap(TimescaleBackend.from_config(default_config))
    # the only way this can return without an error (no connection) is if pending is empty
    result = backend.flush()
    assert result.ok


def test_flush_without_connection_and_exception(unwrap, fixed_now, assert_error):
    # force an immediate flush after adding via the batch size
    backend = unwrap(TimescaleBackend.from_config(default_config | {"max_batch_size": 1}))
    now = fixed_now()

    entry = IntradayPoint(series_id=0, time=now, value=1)

    with patch("psycopg.connect") as mock_connect:
        mock_connect.side_effect = Exception("Boom!")
        result = backend.add(entry)
        assert_error(result, "Connect failed", "Boom!")


def test_add_writes_two_entries(unwrap, fixed_now):
    backend: TimescaleBackend = unwrap(TimescaleBackend.from_config(default_config | {"max_batch_size": 2}))

    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = fixed_now()
    next = now + timedelta(seconds=1)
    entry1 = IntradayPoint(series_id=1, time=now, value=1)
    entry2 = CandlePoint(series_id=2, time=next, close=1.1, volume=2)

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.add(entry1)
        assert result.ok, "First add"
        assert len(backend._pending) == 1
        mock_cursor.executemany.assert_not_called()
        result = backend.add(entry2)
        assert result.ok, "second add"
        mock_cursor.executemany.assert_called()
        assert backend._pending == []


def test_close_writes(unwrap, fixed_now):
    backend = unwrap(TimescaleBackend.from_config(default_config | {"max_batch_size": 2}))

    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = fixed_now()
    entry1 = IntradayPoint(series_id=1, time=now, value=1)

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.add(entry1)
        assert result.ok, "add"
        assert len(backend._pending) == 1
        result = backend.close()
        assert result.ok, "close"
        mock_cursor.executemany.assert_called()
        assert backend._pending == []


def test_flush_writes_when_batch_too_old(unwrap, fixed_now):
    backend: TimescaleBackend = unwrap(TimescaleBackend.from_config(default_config | {"max_batch_age_seconds": 0}))

    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = fixed_now()
    entry = IntradayPoint(series_id=1, time=now, value=1)

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.add(entry)

    assert result.ok
    mock_cursor.executemany.assert_called()
    assert backend._pending == []


def test_flush_raises_in_context_manager(unwrap, fixed_now, assert_error):
    backend: TimescaleBackend = unwrap(TimescaleBackend.from_config(default_config | {"max_batch_size": 1}))

    # mock connection
    mock_conn = MagicMock()

    # mock cursor context manager
    mock_cursor_cm = MagicMock()
    mock_cursor_cm.__enter__.side_effect = Exception("Cursor boom!")
    mock_conn.cursor.return_value = mock_cursor_cm

    entry = IntradayPoint(series_id=1, time=fixed_now(), value=1)

    # patch connect so ensure_connected() returns our mock_conn
    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.add(entry)

    assert_error(result, "Flush operation failed", "Cursor boom!")


def test_flush_invalid_series_point(unwrap, fixed_now, assert_error):
    backend: TimescaleBackend = unwrap(TimescaleBackend.from_config(default_config | {"max_batch_size": 1}))

    entry = SeriesPoint(series_id=1, time=fixed_now())

    # patch connect so ensure_connected() returns our mock_conn
    # with patch("psycopg.connect", return_value=mock_conn):
    result = backend.add(entry)

    assert_error(result, "Flush failed", "Unsupported SeriesPoint subtype: SeriesPoint")


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


def test_read_first_returns_candle_row(unwrap, fixed_now):
    backend = unwrap(TimescaleBackend.from_config(default_config))
    now = fixed_now()
    mock_conn = MagicMock()
    mock_cursor_cm = make_mock_cursor(rows=[(1, now, 10, 12, 8, 11, 1000)])

    mock_conn.cursor.return_value = mock_cursor_cm

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.read_first(1)

    assert result.ok
    assert result.payload == CandlePoint(series_id=1, time=now, open=10, high=12, low=8, close=11, volume=1000)


def test_read_first_returns_value_row(unwrap, fixed_now):
    backend = unwrap(TimescaleBackend.from_config(default_config))
    backend._intraday_series_ids = {1}
    mock_conn = MagicMock()

    now = fixed_now()
    mock_cursor_cm = make_mock_cursor(rows=[(1, now, 15)])

    mock_conn.cursor.return_value = mock_cursor_cm

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.read_first(1)

    assert result.ok
    assert result.payload == IntradayPoint(series_id=1, time=now, value=15)


def test_read_first_returns_none_when_empty(unwrap):
    backend = unwrap(TimescaleBackend.from_config(default_config))

    mock_conn = MagicMock()
    mock_cursor_cm = make_mock_cursor(rows=[None])  # fetchone() returns None

    mock_conn.cursor.return_value = mock_cursor_cm

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.read_first(1)

    assert result.ok
    assert result.payload is None


def test_read_first_handles_db_error(unwrap):
    backend = unwrap(TimescaleBackend.from_config(default_config))

    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = Exception("boom")

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.read_first(1)

    assert not result.ok
    assert "boom" in result.error


def test_read_first_rejects_empty_id(unwrap, assert_error):
    backend = unwrap(TimescaleBackend.from_config(default_config))
    mock_conn = MagicMock()
    mock_cursor_cm = make_mock_cursor(rows=[None])  # fetchone() returns None

    mock_conn.cursor.return_value = mock_cursor_cm

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.read_first(None)

    assert_error(result, "Series id not set for Read first", None)


def test_read_last_returns_daily_value_point(unwrap, fixed_now):
    backend = unwrap(TimescaleBackend.from_config(default_config))
    now = fixed_now().date()
    mock_conn = MagicMock()
    mock_cursor_cm = make_mock_cursor(rows=[(1, now, None, None, None, 11, None)])

    mock_conn.cursor.return_value = mock_cursor_cm

    with patch("psycopg.connect", return_value=mock_conn):
        result = backend.read_last(1)

    assert result.ok
    midnight_today = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)
    assert result.payload == DailyValuePoint(series_id=1, time=midnight_today, value=11)
