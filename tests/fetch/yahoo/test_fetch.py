# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fetch.py

from unittest.mock import Mock

import pytest

from finance.common.model import FetchResult


def test_fetch_dispatches_to_intraday(provider, monkeypatch):
    mock = Mock(return_value=FetchResult.ok_payload("x", []))
    monkeypatch.setattr(provider, "_fetch_intraday", mock)

    asset = {
        "symbol": "EURUSD=X",
        "timeseries": "intraday",
        "fields": ["price"],
    }

    result = provider.fetch("x", asset, last_timestamp=123)
    assert result.ok
    assert result.payload == []
    mock.assert_called_once_with("x", "EURUSD=X", 123)


def test_fetch_dispatches_to_daily(provider, monkeypatch):
    mock = Mock(return_value=FetchResult.ok_payload("x", []))
    monkeypatch.setattr(provider, "_fetch_daily", mock)

    asset = {
        "symbol": "AAPL",
        "timeseries": "daily",
        "fields": ["close"],
    }

    result = provider.fetch("y", asset, last_timestamp=456)

    assert result.payload == []
    mock.assert_called_once_with("y", "AAPL", ["close"], 456)


# -------------------------------
# Internal fetch helpers tests
# -------------------------------


@pytest.mark.parametrize(
    "data, expected_message",
    [
        # explicit Yahoo error
        ({"chart": {"error": {"code": "Not Found"}}}, "{'code': 'Not Found'}"),
        # missing chart
        ({"bogus": False}, "no 'chart' in response"),
        # missing result
        ({"chart": {"result": None}}, "result empty"),
        # valid
        ({"chart": {"result": [{}]}}, None),
    ],
)
def test_error_response(provider, data, expected_message):
    result = provider._error_response(data)

    if expected_message is None:
        assert result is None
    else:
        assert result == expected_message


def test_fetch_success(provider, monkeypatch):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"chart": {"result": [{}]}}

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_response)

    result = provider._fetch("z", "EURUSD=X", "1d", "5d")

    assert result.ok
    assert result.payload == {}


@pytest.mark.parametrize(
    "response_setup, expected_error",
    [
        # HTTP error
        (
            {"raise_for_status": Exception("HTTP 500")},
            "HTTP 500",
        ),
        # JSON error
        (
            {"json": Exception("bad json")},
            "bad json",
        ),
    ],
)
def test_fetch_errors(provider, monkeypatch, response_setup, expected_error):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"chart": {"result": [{}]}}

    # Override behaviors
    for method, value in response_setup.items():
        if isinstance(value, Exception):
            getattr(mock_response, method).side_effect = value
        else:
            getattr(mock_response, method).return_value = value

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_response)

    result = provider._fetch("r", "EURUSD=X", "1d", "5d")

    assert not result.ok
    assert expected_error in result.error
    assert "Exception during fetch" in result.reason


def test_fetch_returns_data_but_no_results(provider, monkeypatch):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "chart": {
            "result": None,
            "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"},
        }
    }

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_response)
    result = provider._fetch("s", "EURUSD=X", "1d", "5d")
    assert not result.ok
    assert result.reason == "Could not interpret fetch response"
    assert result.error == "{'code': 'Not Found', 'description': 'No data found, symbol may be delisted'}"
