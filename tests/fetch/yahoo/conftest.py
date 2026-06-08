# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/conftest.py

import datetime
from datetime import UTC

import pytest

from finance.common.model import MeasurementResult
from finance.fetch.yahoo import YahooProvider


@pytest.fixture
def provider():
    return YahooProvider(config={}, now_provider=lambda: datetime.datetime(2024, 1, 10, 12, 0, tzinfo=UTC))


@pytest.fixture
def capture_fetch(monkeypatch):
    """Capture arguments passed to _fetch and return them."""
    captured = {}

    def wrapper(provider, return_value):
        def fake_fetch(name, symbol, interval_str, range_str):
            captured["name"] = name
            captured["symbol"] = symbol
            captured["interval"] = interval_str
            captured["range"] = range_str
            return MeasurementResult.ok_payload(name, return_value)

        monkeypatch.setattr(provider, "_fetch", fake_fetch)
        return captured

    return wrapper


@pytest.fixture
def make_payload():
    """Generate a minimal Yahoo Finance payload."""

    def _make(ts_list, quote_dict):
        return {
            "timestamp": ts_list,
            "indicators": {"quote": [quote_dict]},
        }

    return _make
