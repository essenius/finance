# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/conftest.py

import pytest
import requests

from finance.common.model import FetchResult
from finance.fetch.ecb import EcbProvider
from finance.fetch.fred import FredProvider
from finance.fetch.provider import MarketDataProvider
from finance.fetch.yahoo import YahooProvider


@pytest.fixture
def assert_ok():
    def _assert_ok(result: FetchResult, timestamp: int, value: float):
        assert result.ok
        point = result.payload[0]
        assert point.timestamp == timestamp
        assert point.value == value

    return _assert_ok


class FakeResponse:
    def __init__(self, status, json_data, text=None):
        self.status_code = status
        self._json = json_data
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.exceptions.HTTPError(self.text or "boom")


@pytest.fixture
def fake_session():
    class FakeSession:
        def __init__(self):
            self.responses = []
            self.calls = 0

        def queue(self, status, json_data, text=None):
            self.responses.append(FakeResponse(status, json_data, text))
            return self

        def queue_error(self, exc):
            self.responses.append(exc)
            return self

        def get(self, *a, **k):
            r = self.responses[self.calls]
            self.calls += 1
            if isinstance(r, Exception):
                raise r
            return r

    def _make():
        return FakeSession()

    return _make


@pytest.fixture
def ecb_provider(fixed_now, fake_session):
    def _make():
        return EcbProvider(
            api_key=None, provider_config={"timezone": "Europe/Berlin"}, now_provider=fixed_now, session=fake_session()
        )

    return _make


@pytest.fixture
def fred_provider(fixed_now, fake_session):
    def _make(api_key="TESTKEY"):
        return FredProvider(
            api_key=api_key,
            provider_config={"timezone": "America/Chicago"},
            now_provider=fixed_now,
            session=fake_session(),
        )

    return _make


@pytest.fixture
def yahoo_provider(fixed_now):
    return YahooProvider(
        asset_config={},
        provider_config={"timezone": "UTC"},
        now_provider=fixed_now,
    )


@pytest.fixture
def dummy_provider():
    def _make():
        return MarketDataProvider(
            provider_config={"timezone": "UTC"},
        )

    return _make


@pytest.fixture
def make_asset_dict(make_asset):
    def _make(id=1, name="eur_usd", provider="yahoo", provider_code="EURUSD=X"):
        asset = make_asset(id=id, name=name, provider=provider, provider_code=provider_code)
        return {name: asset}

    return _make
