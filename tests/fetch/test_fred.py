# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_fred.py

import pytest

from finance.fetch.fred import FredProvider


def make_provider(api_key="TESTKEY"):
    return FredProvider({"api_key": api_key})


def make_asset(symbol="T10YIE", field="price"):
    return {"symbol": symbol, "fields": [field]}


"""
def mock_fred_response(monkeypatch, status, json_data):
    mock_resp = Mock()
    mock_resp.status_code = status
    mock_resp.json.return_value = json_data
    monkeypatch.setattr("finance.fetch.fred.requests.get", lambda *a, **k: mock_resp)
"""


def test_fred_fetch_normal(monkeypatch, assert_ok, mock_get_response):

    mock_get_response(monkeypatch, "fred", 200, {"observations": [{"value": "2.34", "date": "2024-05-09"}]})
    provider = make_provider()
    result = provider.fetch("f1", make_asset(), None)
    assert_ok(result, 1715212800, 2.34)


# -------------------------------
# PARAMETRIZED MALFORMED CASES
# -------------------------------

MALFORMED_CASES = [
    # Missing API key (provider-level behavior)
    (
        None,  # api_key
        {"observations": [{"value": "2.34", "date": "2024-05-09"}]},
        "FRED requires an API key",
    ),
    # Observations missing entirely
    (
        "TESTKEY",
        {"foo": "bar"},
        "no 'observations' in response",
    ),
    # Observations empty
    (
        "TESTKEY",
        {"observations": []},
        "no 'observations' in response",
    ),
    # Invalid values
    (
        "TESTKEY",
        {"observations": [{"value": "", "date": "2024-05-09"}]},
        "invalid value '' in first observation",
    ),
    (
        "TESTKEY",
        {"observations": [{"value": ".", "date": "2024-05-09"}]},
        "invalid value '.' in first observation",
    ),
    (
        "TESTKEY",
        {"observations": [{"value": None, "date": "2024-05-09"}]},
        "invalid value 'None' in first observation",
    ),
]


@pytest.mark.parametrize("api_key, json_data, expected_error", MALFORMED_CASES)
def test_fred_malformed_cases(monkeypatch, assert_error, api_key, json_data, expected_error, mock_get_response):

    # Missing API key → no HTTP call
    if api_key is not None:
        mock_get_response(monkeypatch, "fred", 200, json_data)

    provider = make_provider(api_key) if api_key is not None else FredProvider()

    result = provider.fetch("f2", make_asset(), None)

    assert_error(result, expected_error, None)


def test_fred_fetch_network_error(monkeypatch, assert_error):

    monkeypatch.setattr("finance.fetch.fred.requests.get", lambda *a, **k: (_ for _ in ()).throw(Exception("boom")))

    provider = make_provider()
    result = provider.fetch("f3", make_asset(), None)

    assert_error(result, "Exception during fetch", "boom")


def test_fred_status_code_not_200(monkeypatch, assert_error, mock_get_response):

    mock_get_response(monkeypatch, "fred", 500, {}, "status 500")

    provider = make_provider()

    result = provider.fetch("f4", make_asset(), None)
    assert_error(result, "Exception during fetch", "status 500")
