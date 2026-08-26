# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/conftest.py

from datetime import datetime
from typing import Any

import pytest
import requests

from finance.common.configuration import ProviderConfig
from finance.common.model import FetchResult
from finance.common.string_enums import SupportedProviders
from finance.fetch.ecb import EcbProvider
from finance.fetch.fred import FredProvider
from finance.fetch.provider import MarketDataProvider, ResponseProtocol
from finance.fetch.yahoo import YahooProvider
from tests.support.types import ConfigurableFactory, Factory


@pytest.fixture
def assert_ok():
    def _assert_ok(result: FetchResult, time: datetime, close: float) -> None:
        assert result.ok is True
        point = result.payload.points[0]
        assert point.time == time
        assert point.close == close

    return _assert_ok


class FakeResponse:
    status_code: int
    text: str
    def __init__(self, status: int, json_data: object, text: str=""):
        self.status_code = status
        self._json = json_data
        self.text = text

    def json(self) -> object:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code != 200:
            raise requests.exceptions.HTTPError(self.text or "boom")


class FakeSession:
    url: str
    params: dict[str, Any] | None
    timeout: float | None

    def __init__(self):
        self.responses: list[ResponseProtocol|Exception] = []
        self.calls = 0

    def queue(self, status: int, json_data: object, text:str=""):
        self.responses.append(FakeResponse(status, json_data, text))
        return self

    def queue_error(self, exc: Exception):
        self.responses.append(exc)
        return self

    def get(self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None, **kwargs: Any) -> ResponseProtocol:
        self.url = url
        self.params = params
        self.timeout = timeout
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def fake_session() -> Factory[FakeSession]:
    def _make() -> FakeSession:
        return FakeSession()

    return _make


@pytest.fixture
def ecb_provider(fixed_now, fake_session) -> Factory[EcbProvider]:
    def _make() -> EcbProvider:
        return EcbProvider(
            provider_config=ProviderConfig.from_config({"name": SupportedProviders.ECB.value}),
            now_provider=fixed_now,
            session=fake_session(),
        )

    return _make


@pytest.fixture
def fred_provider(fixed_now, fake_session) -> Factory[FredProvider]:
    def _make(api_key: str = "TESTKEY") -> FredProvider:
        return FredProvider(
            provider_config=ProviderConfig.from_config({"name": SupportedProviders.FRED.value, "api_key": api_key}),
            now_provider=fixed_now,
            session=fake_session(),
        )

    return _make


@pytest.fixture
def yahoo_provider(
    fixed_now: Factory[datetime], fake_session: Factory[FakeSession]
) -> ConfigurableFactory[YahooProvider]:
    def _make(now_provider: Factory[datetime] = fixed_now) -> YahooProvider:
        return YahooProvider(
            provider_config=ProviderConfig.from_config({"name": SupportedProviders.YAHOO.value}),
            now_provider=now_provider,
            session=fake_session(),
        )

    return _make


@pytest.fixture
def dummy_provider() -> Factory[MarketDataProvider]:
    def _make() -> MarketDataProvider:
        return MarketDataProvider(
            provider_config=ProviderConfig.from_config({"name": "dummy"}),
        )

    return _make


@pytest.fixture
def make_asset_dict(make_asset):
    def _make(id=1, name="eur_usd", provider="yahoo", provider_code="EURUSD=X"):
        asset = make_asset(id=id, name=name, provider=provider, provider_code=provider_code)
        return {name: asset}

    return _make
