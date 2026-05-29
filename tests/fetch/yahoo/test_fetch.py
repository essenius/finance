# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fetch.py

from unittest.mock import Mock

import pytest


def test_fetch_dispatches_to_intraday(provider, monkeypatch):
    mock = Mock(return_value=["intraday-result"])
    monkeypatch.setattr(provider, "_fetch_intraday", mock)

    asset = {
        "symbol": "EURUSD=X",
        "timeseries": "intraday",
        "fields": ["close"],
    }

    result = provider.fetch(asset, last_timestamp=123)

    assert result == ["intraday-result"]
    mock.assert_called_once_with("EURUSD=X", ["close"], 123)


def test_fetch_dispatches_to_daily(provider, monkeypatch):
    mock = Mock(return_value=["daily-result"])
    monkeypatch.setattr(provider, "_fetch_daily", mock)

    asset = {
        "symbol": "AAPL",
        "timeseries": "daily",
        "fields": ["close"],
    }

    result = provider.fetch(asset, last_timestamp=456)

    assert result == ["daily-result"]
    mock.assert_called_once_with("AAPL", ["close"], 456)


def test_fetch_raises_for_unknown_timeseries(provider):
    asset = {
        "symbol": "BTC-USD",
        "timeseries": "weekly",
        "fields": ["close"],
    }

    with pytest.raises(ValueError) as exc:
        provider.fetch(asset)

    assert "weekly" in str(exc.value)


# -------------------------------
# Internal fetch helpers tests
# -------------------------------


@pytest.mark.parametrize(
    "data, expected_is_error, expected_message",
    [
        # explicit Yahoo error
        ({"chart": {"error": {"code": "Not Found"}}}, True, "{'code': 'Not Found'}"),
        # missing chart
        ({"bogus": False}, True, "no 'chart' in response"),
        # missing result
        ({"chart": {"result": None}}, True, "result empty"),
        # valid
        ({"chart": {"result": [{}]}}, False, None),
    ],
)
def test_is_error_response(provider, capsys, data, expected_is_error, expected_message):
    symbol = "x"
    result = provider._is_error_response(data, symbol)

    assert result is expected_is_error

    captured = capsys.readouterr()

    if expected_is_error:
        assert f"Error fetching Yahoo data for x: {expected_message}" in captured.err
    else:
        assert captured.err == ""


def test_fetch_success(provider, monkeypatch, capsys):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"chart": {"result": [{}]}}

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_response)

    result = provider._fetch("EURUSD=X", "1d", "5d")
    assert result == {}
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


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
def test_fetch_errors(provider, monkeypatch, capsys, response_setup, expected_error):
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

    result = provider._fetch("EURUSD=X", "1d", "5d")
    assert result == []

    err = capsys.readouterr().err
    assert expected_error in err


def test_fetch_returns_data_but_no_results(provider, monkeypatch):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"chart": {"result": []}}

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_response)
    result = provider._fetch("EURUSD=X", "1d", "5d")
    assert result == []
