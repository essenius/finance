# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_ecb.py

import json
from unittest.mock import Mock

import pytest
import requests

from finance.fetch.ecb import EcbProvider


def make_asset(symbol="EUR_USD", field="price"):
    return {"symbol": symbol, "fields": [field]}


def mock_ecb_response(monkeypatch, status, json_data, text=None):
    mock_resp = Mock()
    mock_resp.status_code = status
    mock_resp.json.return_value = json_data

    if status == 200:
        mock_resp.raise_for_status.return_value = None
    else:
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(text or "boom")
    if text:
        mock_resp.text = text  # if text else json.dumps(json_data)

    monkeypatch.setattr("finance.fetch.ecb.requests.get", lambda *a, **k: mock_resp)


def test_ecb_fetch_real_fixture(monkeypatch, assert_ok):
    with open("tests/data/ecb_eurusd.json") as f:
        fake_json = json.load(f)

    mock_ecb_response(monkeypatch, 200, fake_json)
    # mock_resp.text = json.dumps(fake_json)

    provider = EcbProvider()
    result = provider.fetch("eurusd_1", make_asset(), last_timestamp=None)

    assert_ok(result, timestamp=1778191200, value=1.1761)


def test_ecb_fetch_ok(monkeypatch, assert_ok):
    fake_json = {
        "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.1761]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"start": "2026-05-08T00:00:00.000+02:00"}]}]}},
    }
    mock_ecb_response(monkeypatch, 200, fake_json)

    provider = EcbProvider()
    result = provider.fetch("eurusd_2", make_asset(), last_timestamp=None)

    assert_ok(result, timestamp=1778191200, value=1.1761)


@pytest.mark.parametrize(
    "symbol",
    [
        "EUR",
        "EUR_USD_GBP",
        "_",
    ],
)
def test_ecb_fetch_wrong_symbol(symbol):
    provider = EcbProvider()
    result = provider.fetch("eurusd_3", make_asset(symbol=symbol), last_timestamp=None)
    assert not result.ok
    assert f"Could not split symbol '{symbol}' into base_quote" in result.reason
    assert result.payload is None


def test_ecb_fetch_non_200(monkeypatch):
    mock_ecb_response(monkeypatch, 500, "", "Internal Server Error")

    provider = EcbProvider()

    result = provider.fetch("eurusd_3", make_asset(), last_timestamp=None)

    assert not result.ok
    assert "Internal Server Error" in result.error
    assert "Exception during fetch" in result.reason
    assert result.payload is None


MALFORMED_CASES = [
    ({}, "missing key 'dataSets'", "price"),
    ({"dataSets": []}, "missing index [0]", "price"),
    ({"dataSets": [{"series": {}}]}, "missing key '0:0:0:0:0'", "price"),
    ({"dataSets": [{"series": {"0:0:0:0:0": {"observations": {}}}}]}, "missing key '0'", "price"),
    (
        {"dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": 1.234}}}}]},
        "cannot index with [0] at ['dataSets', 0, 'series', '0:0:0:0:0', 'observations', '0']",
        "price",
    ),
    (
        {
            "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.234]}}}}],
            "structure": {"dimensions": {"observation": []}},
        },
        "missing index [0]",
        "timestamp",
    ),
]


@pytest.mark.parametrize("json_data, expected, context", MALFORMED_CASES)
def test_ecb_malformed_json(monkeypatch, json_data, expected, context, assert_error):
    mock_ecb_response(monkeypatch, 200, json_data)

    provider = EcbProvider()

    result = provider.fetch("eurusd_4", make_asset(), None)

    assert_error(result, f"Could not interpret path for {context}", expected)
