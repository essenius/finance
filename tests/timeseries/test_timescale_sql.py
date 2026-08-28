# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_timescale_sql.py


from psycopg.sql import SQL, Composed, Identifier

from tests.support.fakes import FakeSql
from tests.support.types import AssertError, ContextManagerFactory, Creator


def test_execute_read_returns_rows(sql_with_fake_connection: Creator[FakeSql]):
    fake_sql = sql_with_fake_connection(fetchall=[(1, "AAPL"), (2, "MSFT")])
    sql = fake_sql.client
    rows_result = sql.execute_read("SELECT * FROM {table} WHERE id > %s", (10,), table="asset")

    assert rows_result.ok is True
    assert rows_result.payload == {"rows": [(1, "AAPL"), (2, "MSFT")], "columns": {}}
    assert fake_sql.connection is not None
    fake_sql.cursor.execute.assert_called_once_with(
        Composed([SQL("SELECT * FROM "), Identifier("asset"), SQL(" WHERE id > %s")]), (10,)
    )
    fake_sql.cursor.fetchall.assert_called_once()

    assert sql.is_connected()
    sql.close_connection()
    assert not sql.is_connected()


def test_execute_read_fails(assert_error: AssertError, sql_with_fake_connection: Creator[FakeSql]):
    fake_sql = sql_with_fake_connection(fetchall=[(1, "AAPL"), (2, "MSFT")])
    sql = fake_sql.client
    cursor = fake_sql.cursor
    cursor.description = None
    rows_result = sql.execute_read("SELECT * FROM {} WHERE id > %s", (10,))

    assert_error(rows_result, "Read operation failed", "Query result does not contain column names")


def test_execute_write_success(sql_with_fake_connection: Creator[FakeSql]):
    fake_sql = sql_with_fake_connection(fetchone=[42])
    sql = fake_sql.client
    result = sql.execute_write("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;", ("AAPL",))

    assert result.ok is True
    assert result.payload == 42

    fake_sql.cursor.execute.assert_called_once_with(
        SQL("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;"), ("AAPL",)
    )
    fake_sql.cursor.fetchone.assert_called_once()


def test_execute_write_fails(assert_error: AssertError, sql_with_fake_connection: Creator[FakeSql]):
    fake_sql = sql_with_fake_connection(fetchone=[42])
    sql = fake_sql.client
    fake_sql.cursor.fetchone.return_value = None
    result = sql.execute_write("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;", ("AAPL",))
    assert_error(result, "Write operation failed", "Query did not return a result")

    fake_sql.cursor.execute.assert_called_once_with(
        SQL("INSERT INTO asset(symbol) VALUES (%s) RETURNING id;"), ("AAPL",)
    )
    fake_sql.cursor.fetchone.assert_called_once()


def test_close(sql_with_fake_psycopg: ContextManagerFactory[FakeSql], assert_error: AssertError):

    with sql_with_fake_psycopg(execute_error=True) as fake_sql:
        sql = fake_sql.client
        sql.close_connection()
        assert not sql.is_connected(), "Disconnected"
        sql.close_connection()
        assert not sql.is_connected(), "Still Disconnected after second close"
        result = sql.execute_write("", ())
        assert_error(result, reason="Database startup failed", error="Execute boom!")


def test_connect_exception(sql_with_fake_psycopg: ContextManagerFactory[FakeSql], assert_error: AssertError):
    with sql_with_fake_psycopg(execute_error=True) as fake_sql:
        sql = fake_sql.client
        sql.close_connection()
        assert fake_sql.connect is not None
        fake_sql.connect.side_effect = Exception("Boom!")
        result = sql.execute_read("")
        assert_error(result, "Connect failed", "Boom!")


def test_connect_succeeded(sql_with_fake_psycopg: ContextManagerFactory[FakeSql]):
    with sql_with_fake_psycopg() as fake_sql:
        result = fake_sql.client.execute_many("", [], context="many")
        assert result.ok is True
        assert result.payload is None
