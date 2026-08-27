# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_timescale_sql.py


def test_execute_read_returns_rows(sql_with_fake_connection):
    sql, cursor = sql_with_fake_connection(fetchall=[(1, "AAPL"), (2, "MSFT")])
    rows_result = sql.execute_read("SELECT * FROM asset WHERE id > %s", (10,))

    assert rows_result.ok is True
    assert rows_result.payload == {"rows": [(1, "AAPL"), (2, "MSFT")], "columns": {}}

    sql._connection.cursor.assert_called_once(), "the context manager was called"
    cursor.execute.assert_called_once_with("SELECT * FROM asset WHERE id > %s", (10,))
    cursor.fetchall.assert_called_once()

    assert sql.is_connected()
    sql.close_connection()
    assert not sql.is_connected()


def test_execute_write_success(sql_with_fake_connection):
    sql, cursor = sql_with_fake_connection(fetchone=[42])

    result = sql.execute_write("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;", ("AAPL",))

    assert result.ok is True
    assert result.payload == 42

    cursor.execute.assert_called_once_with("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;", ("AAPL",))
    cursor.fetchone.assert_called_once()


def fake(cursor):
    return "fake"


def test_close(sql_with_fake_psycopg, assert_error):

    with sql_with_fake_psycopg(execute_error=True) as sql:
        sql.close_connection()
        assert not sql.is_connected(), "Disconnected"
        sql.close_connection()
        assert not sql.is_connected(), "Still Disconnected after second close"
        result = sql.execute_write("", ())
        assert_error(result, reason="Database startup failed", error="Execute boom!")


def test_connect_failed(sql_with_fake_psycopg, assert_error):
    with sql_with_fake_psycopg(execute_error=True) as sql:
        sql.close_connection()
        sql.mock_connect.side_effect = Exception("Boom!")
        result = sql.execute_read("")
        assert_error(result, "Connect failed", "Boom!")


def test_connect_succeeded(sql_with_fake_psycopg, unwrap):
    with sql_with_fake_psycopg() as sql:
        result = sql.execute_many("", [], "many")
        assert result.ok is True
        assert result.payload is None
