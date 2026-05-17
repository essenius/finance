# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_fetch_yahoo.py

import json
from unittest.mock import Mock, patch

from finance.fetch.yahoo import fetch_yahoo_chart


def load_json(name):
    with open(f"tests/data/{name}.json") as f:
        return json.load(f)


@patch("finance.fetch.yahoo.requests.get")
def test_yahoo_parses_value_and_timestamp(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = load_json("yahoo_eurusd_rt")
    mock_get.return_value = mock_response

    result = fetch_yahoo_chart("EURUSD=X", None)

    assert isinstance(result["value"], float)
    assert isinstance(result["timestamp"], int)
    assert result["value"] == 1.179
    assert result["timestamp"] == 1778275765


@patch("finance.fetch.yahoo.requests.get")
def test_yahoo_returns_fallback_when_missing_timestamp(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = load_json("yahoo_eurusd_rt_no_date")
    mock_get.return_value = mock_response

    result = fetch_yahoo_chart("EURUSD=X", None)

    assert result["value"] == 1.1789672374725342
    assert result["timestamp"] == 1778275765


@patch("finance.fetch.yahoo.requests.get")
def test_yahoo_handles_missing_data(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {"chart": {"result": None}}
    mock_get.return_value = mock_response

    result = fetch_yahoo_chart("EURUSD=X", {})

    assert result["value"] is None
    assert result["timestamp"] is None


def test_yahoo_returns_none_when_no_price_and_no_candles(monkeypatch):
    # This JSON structure must:
    # - include meta with missing price/time
    # - include timestamp = [] (or None)
    # - include close = [] (or None)
    # - NOT raise KeyError (so structure must exist)
    fake_json = {
        "chart": {
            "result": [
                {
                    "meta": {"regularMarketPrice": None, "regularMarketTime": None},
                    "timestamp": [],  # no timestamps
                    "indicators": {
                        "quote": [
                            {"close": []}  # no closes
                        ]
                    },
                }
            ]
        }
    }

    mock_response = Mock()
    mock_response.json.return_value = fake_json

    # Patch requests.get to return our fake response
    monkeypatch.setattr("finance.fetch.yahoo.requests.get", lambda *args, **kwargs: mock_response)

    result = fetch_yahoo_chart("FAKE", None)

    assert result["value"] is None
    assert result["timestamp"] is None
