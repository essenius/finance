# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/support/fakes.py

from datetime import datetime, timedelta
from typing import Any, Protocol, cast
from unittest.mock import MagicMock

import requests

from finance.common.json_utils import JsonLike
from finance.common.time_utils import UTC
from finance.fetch.provider import MarketDataProvider, ResponseProtocol


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
    url: str
    params: dict[str, Any] | None
    timeout: float | None

    def __init__(self):
        self.responses: list[ResponseProtocol | Exception] = []
        self.calls = 0

    def queue(self, status: int, json_data: JsonLike, text: str = ""):
        self.responses.append(FakeResponse(status, json_data, text))
        return self

    def queue_error(self, exc: Exception):
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


def fake_session(provider: MarketDataProvider) -> FakeSession:
    return cast(FakeSession, provider.session)


class SqlWithMockCursor(Protocol):
    mock_cursor: MagicMock
    mock_connect: MagicMock
    _connection: MagicMock
