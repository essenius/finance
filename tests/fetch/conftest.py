# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/conftest.py

from collections.abc import Callable
from datetime import datetime

import pytest

from finance.common.configuration import ProviderConfig
from finance.common.model import FetchResult
from finance.common.string_enums import SupportedProviders
from finance.fetch.ecb import EcbProvider
from finance.fetch.fred import FredProvider
from finance.fetch.yahoo import YahooProvider
from tests.support.fakes import FakeProvider, FakeSession
from tests.support.types import Creator, Factory


@pytest.fixture
def assert_ok() -> Callable[[FetchResult, datetime, float], None]:
    def _assert_ok(result: FetchResult, time: datetime, close: float) -> None:
        assert result.ok is True
        point = result.payload.points[0]
        assert point.time == time
        assert point.close == close

    return _assert_ok


@pytest.fixture
def fake_session() -> Factory[FakeSession]:
    def _make() -> FakeSession:
        return FakeSession()

    return _make


@pytest.fixture
def ecb_provider(
    fixed_now: Factory[datetime], fake_session: Factory[FakeSession]
) -> Factory[FakeProvider[EcbProvider]]:
    def _make() -> FakeProvider[EcbProvider]:
        session = fake_session()
        return FakeProvider(
            provider=EcbProvider(
                provider_config=ProviderConfig.from_config({"name": SupportedProviders.ECB.value}),
                now_provider=fixed_now,
                session=session,
            ),
            session=session,
        )

    return _make


@pytest.fixture
def fred_provider(
    fixed_now: Factory[datetime], fake_session: Factory[FakeSession]
) -> Creator[FakeProvider[FredProvider]]:
    def _make(api_key: str = "TESTKEY") -> FakeProvider[FredProvider]:
        session = fake_session()
        return FakeProvider(
            provider=FredProvider(
                provider_config=ProviderConfig.from_config({"name": SupportedProviders.FRED.value, "api_key": api_key}),
                now_provider=fixed_now,
                session=session,
            ),
            session=session,
        )

    return _make


@pytest.fixture
def yahoo_provider(
    fixed_now: Factory[datetime], fake_session: Factory[FakeSession]
) -> Creator[FakeProvider[YahooProvider]]:
    def _make(now_provider: Factory[datetime] = fixed_now) -> FakeProvider[YahooProvider]:
        session = fake_session()
        return FakeProvider(
            provider=YahooProvider(
                provider_config=ProviderConfig.from_config({"name": SupportedProviders.YAHOO.value}),
                now_provider=now_provider,
                session=session,
            ),
            session=session,
        )

    return _make
