# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/conftest.py

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from finance.common.model import SeriesPoint
from finance.common.string_enums import Retention
from finance.timeseries.series_backend import SeriesBackend, TimescaleConfig
from finance.timeseries.timescale_sql import TimescaleSqlClient
from tests.support.types import ConfigurableFactory, ContextManagerFactory, Factory, FakeClock


@pytest.fixture
def sql_with_fake_connection(
    make_backend_config: Factory[TimescaleConfig],
) -> ConfigurableFactory[tuple[TimescaleSqlClient, MagicMock]]:
    def _make(connected: bool = True, **kwargs) -> tuple[TimescaleSqlClient, MagicMock]:

        config = make_backend_config()
        sql = TimescaleSqlClient(config)
        sql._connection = MagicMock()
        sql._connection.closed = not connected

        sql.mock_cursor = MagicMock()
        fetch_one = kwargs.get("fetchone")
        sql.mock_cursor.fetchone.return_value = fetch_one
        fetch_all = kwargs.get("fetchall")
        sql.mock_cursor.fetchall.return_value = fetch_all
        execute = kwargs.get("execute")
        sql.mock_cursor.execute.return_value = execute
        sql._connection.cursor.return_value.__enter__.return_value = sql.mock_cursor
        return sql, sql.mock_cursor

    return _make


@pytest.fixture
def sql_with_fake_psycopg(make_backend_config: Factory[TimescaleConfig]) -> ContextManagerFactory[TimescaleSqlClient]:
    @contextmanager
    def _make(execute_error=False):
        fake_cursor = MagicMock()
        fake_cursor.execute.return_value = None
        fake_cursor.executemany.return_value = None

        fake_connection = MagicMock()
        fake_connection.closed = False
        fake_connection.cursor.return_value.__enter__.return_value = fake_cursor
        fake_connection.cursor.return_value.__exit__.return_value = False

        if execute_error:
            fake_cursor.execute.side_effect = Exception("Execute boom!")

        with patch("psycopg.connect", return_value=fake_connection) as mock_connect:
            sql = TimescaleSqlClient(make_backend_config())

            sql.mock_connect = mock_connect
            sql.mock_cursor = fake_cursor

            yield sql

    return _make


@pytest.fixture
def make_backend_config() -> Factory[TimescaleConfig]:
    def _make(max_batch_size: int = 2, max_batch_age_seconds: int = 2) -> TimescaleConfig:
        return TimescaleConfig(
            host="x",
            dbname="finance",
            user="u",
            password="p",
            max_batch_size=max_batch_size,
            max_batch_age=timedelta(seconds=max_batch_age_seconds),
        )

    return _make


@pytest.fixture
def make_backend(
    make_backend_config: Factory[TimescaleConfig],
    sql_with_fake_connection: ConfigurableFactory[tuple[TimescaleSqlClient, MagicMock]],
) -> ConfigurableFactory[SeriesBackend]:
    def _make(
        max_batch_size: int = 2, max_batch_age_seconds: int = 2, connected: bool = True, **kwargs
    ) -> SeriesBackend:
        config = make_backend_config(max_batch_size=max_batch_size, max_batch_age_seconds=max_batch_age_seconds)

        sql_client, _ = sql_with_fake_connection(connected=connected, **kwargs)
        return SeriesBackend(config=config, sql_client=sql_client, now=FakeClock())

    return _make


@pytest.fixture
def make_entry() -> ConfigurableFactory[SeriesPoint]:
    def _make(
        id: int = 1, fields: dict | None = None, retention: Retention = Retention.DAILY, timestamp: int = 0
    ) -> SeriesPoint:
        return SeriesPoint(series_id=id, time=timestamp, retention=retention, fields=fields or {})

    return _make


@pytest.fixture
def make_entries(make_entry: ConfigurableFactory[SeriesPoint]) -> Factory[list[SeriesPoint]]:
    def _make(n) -> list[SeriesPoint]:
        return [make_entry(fields={"v": i}, timestamp=i) for i in range(n)]

    return _make
