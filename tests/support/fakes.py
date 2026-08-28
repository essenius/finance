# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/support/fakes.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Self, cast
from unittest.mock import AsyncMock, MagicMock

import requests

from finance.common.json_utils import JsonLike
from finance.common.time_utils import UTC
from finance.fetch.provider import MarketDataProvider, ProviderProtocol, ResponseProtocol
from finance.timeseries.series_backend import SeriesBackend
from finance.timeseries.timescale_sql import TimescaleSqlClient


class FakeClock:
    def __init__(self):
        self.t = datetime(2025, 6, 15, 15, 6, 40, tzinfo=UTC)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += timedelta(seconds=dt)


class FakeResponse:
    status_code: int
    text: str

    def __init__(self, status: int, json_data: JsonLike, text: str = ""):
        self.status_code = status
        self._json = json_data
        self.text = text

    def json(self) -> JsonLike:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code != 200:
            raise requests.exceptions.HTTPError(self.text or "boom")


class FakeSession:
    url: str | None
    params: dict[str, Any] | None
    timeout: float | None

    def __init__(self):
        self.url = None
        self.params = None
        self.timeout = None
        self.responses: list[ResponseProtocol | Exception] = []
        self.calls = 0

    def queue(self, status: int, json_data: JsonLike, text: str = "") -> Self:
        self.responses.append(FakeResponse(status, json_data, text))
        return self

    def queue_error(self, exc: Exception) -> Self:
        self.responses.append(exc)
        return self

    def get(
        self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None, **kwargs: Any
    ) -> ResponseProtocol:
        self.url = url
        self.params = params
        self.timeout = timeout
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


@dataclass
class FakeProvider[T: ProviderProtocol]:
    provider: T
    session: FakeSession

    def only(self) -> T:
        return self.provider


def fake_session(provider: MarketDataProvider) -> FakeSession:
    return cast(FakeSession, provider.session)


@dataclass
class FakeSql:
    client: TimescaleSqlClient
    connection: MagicMock
    cursor: MagicMock
    connect: MagicMock | AsyncMock | None = None


@dataclass
class FakeBackend:
    backend: SeriesBackend
    fake_sql: FakeSql
    clock: FakeClock

    def with_sql(self) -> tuple[SeriesBackend, TimescaleSqlClient]:
        return self.backend, self.fake_sql.client

    def with_connection(self) -> tuple[SeriesBackend, MagicMock]:
        return self.backend, self.fake_sql.connection

    def with_cursor(self) -> tuple[SeriesBackend, MagicMock]:
        return self.backend, self.fake_sql.cursor

    def with_clock(self) -> tuple[SeriesBackend, FakeClock]:
        return self.backend, self.clock

    def only(self) -> SeriesBackend:
        return self.backend
