# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/conftest.py

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from finance.common.configuration import TimescaleConfig
from finance.timeseries.series_backend import SeriesBackend
from finance.timeseries.timescale_sql import TimescaleSqlClient
from tests.support.fakes import FakeBackend, FakeClock, FakeSql
from tests.support.types import ContextManagerFactory, Creator, Factory


@pytest.fixture
def make_timescale_config() -> Creator[TimescaleConfig]:
    def _make(**overrides) -> TimescaleConfig:
        defaults = {
            "host": "host123",
            "user": "fin_user",
            "password": "s3cr3t",
            "db": "fin2",
        }

        params = defaults | overrides

        return TimescaleConfig.from_config(params)

    return _make


@pytest.fixture
def sql_with_fake_connection(make_backend_config: Factory[TimescaleConfig]) -> Creator[FakeSql]:
    def _make(connected: bool = True, **kwargs) -> FakeSql:

        config = make_backend_config()
        sql = TimescaleSqlClient(config)

        connection = MagicMock()
        connection.closed = not connected
        sql._connection = connection

        cursor = MagicMock()
        cursor.fetchone.return_value = kwargs.get("fetchone")
        cursor.fetchall.return_value = kwargs.get("fetchall")
        cursor.execute.return_value = kwargs.get("execute")

        cursor_cm = connection.cursor.return_value
        cursor_cm.__enter__.return_value = cursor
        cursor_cm.__exit__.return_value = False

        return FakeSql(client=sql, connection=connection, cursor=cursor)

    return _make


@pytest.fixture
def sql_with_fake_psycopg(make_backend_config: Factory[TimescaleConfig]) -> ContextManagerFactory[FakeSql]:
    @contextmanager
    def _make(execute_error=False) -> Generator[FakeSql, None, None]:
        cursor = MagicMock()
        cursor.execute.return_value = None
        cursor.executemany.return_value = None

        connection = MagicMock()
        connection.closed = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False

        if execute_error:
            cursor.execute.side_effect = Exception("Execute boom!")

        with patch("psycopg.connect", return_value=connection) as connect:
            sql = TimescaleSqlClient(make_backend_config())

            yield FakeSql(client=sql, connection=connection, cursor=cursor, connect=connect)

    return _make


@pytest.fixture
def make_backend_config() -> Creator[TimescaleConfig]:
    def _make(max_batch_size: int = 2, max_batch_age_seconds: float = 2) -> TimescaleConfig:
        config = {
            "host": "x",
            "db": "finance",
            "user": "u",
            "password": "p",
            "max_batch_size": max_batch_size,
            "max_batch_age_seconds": max_batch_age_seconds,
        }
        return TimescaleConfig.from_config(config)

    return _make


@pytest.fixture
def make_backend(
    make_backend_config: Creator[TimescaleConfig], sql_with_fake_connection: Creator[FakeSql]
) -> Creator[FakeBackend]:
    def _make(max_batch_size: int = 2, max_batch_age_seconds: int = 2, connected: bool = True, **kwargs) -> FakeBackend:
        config = make_backend_config(max_batch_size=max_batch_size, max_batch_age_seconds=max_batch_age_seconds)
        fake_sql = sql_with_fake_connection(connected=connected, **kwargs)
        clock = FakeClock()

        return FakeBackend(SeriesBackend(config=config, sql_client=fake_sql.client, now=clock), fake_sql, clock)

    return _make
