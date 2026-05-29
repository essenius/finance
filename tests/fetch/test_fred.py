# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_fred.py

from unittest.mock import Mock

import pytest

from finance.fetch.fred import FredProvider


def make_provider(api_key="TESTKEY"):
    return FredProvider({"api_key": api_key})


def make_asset(symbol="T10YIE", field="price"):
    return {"symbol": symbol, "fields": [field]}


def mock_fred_response(monkeypatch, status, json_data):
    mock_resp = Mock()
    mock_resp.status_code = status
    mock_resp.json.return_value = json_data
    monkeypatch.setattr("finance.fetch.fred.requests.get", lambda *a, **k: mock_resp)


def test_fred_fetch_normal(monkeypatch):

    mock_fred_response(monkeypatch, 200, {"observations": [{"value": "2.34", "date": "2024-05-09"}]})

    provider = make_provider()
    result = provider.fetch(make_asset(), None)

    assert result == [{"timestamp": 1715212800, "fields": {"price": 2.34}}]


# -------------------------------
# PARAMETRIZED MALFORMED CASES
# -------------------------------

MALFORMED_CASES = [
    # Missing API key (provider-level behavior)
    (
        None,  # api_key
        {"observations": [{"value": "2.34", "date": "2024-05-09"}]},
        "API key missing",
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
def test_fred_malformed_cases(monkeypatch, capsys, api_key, json_data, expected_error):

    # Missing API key → no HTTP call
    if api_key is not None:
        mock_fred_response(monkeypatch, 200, json_data)

    provider = make_provider(api_key) if api_key is not None else FredProvider()

    result = provider.fetch(make_asset(), None)
    assert result == []

    err = capsys.readouterr().err
    assert expected_error in err


def test_fred_fetch_network_error(monkeypatch, capsys):

    monkeypatch.setattr("finance.fetch.fred.requests.get", lambda *a, **k: (_ for _ in ()).throw(Exception("boom")))

    provider = make_provider()
    assert provider.fetch(make_asset(), None) == []

    assert "boom" in capsys.readouterr().err


def test_fred_status_code_not_200(monkeypatch, capsys):

    mock_fred_response(monkeypatch, 500, {})

    provider = make_provider()
    assert provider.fetch(make_asset(), None) == []

    assert "status 500" in capsys.readouterr().err
