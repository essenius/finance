# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_ecb.py

import json
from unittest.mock import Mock

import pytest

from finance.fetch.ecb import EcbProvider


def make_asset(symbol="EUR_USD", field="price"):
    return {"symbol": symbol, "fields": [field]}


def mock_ecb_response(monkeypatch, status, json_data, text=None):
    mock_resp = Mock()
    mock_resp.status_code = status
    mock_resp.json.return_value = json_data
    if text:
        mock_resp.text = text  # if text else json.dumps(json_data)

    monkeypatch.setattr("finance.fetch.ecb.requests.get", lambda *a, **k: mock_resp)


def test_ecb_fetch_real_fixture(monkeypatch):
    with open("tests/data/ecb_eurusd.json") as f:
        fake_json = json.load(f)

    mock_ecb_response(monkeypatch, 200, fake_json)
    # mock_resp.text = json.dumps(fake_json)

    provider = EcbProvider()
    result = provider.fetch(make_asset(), last_timestamp=None)

    assert result == [{"timestamp": 1778191200, "fields": {"price": 1.1761}}]


def test_ecb_fetch_ok(monkeypatch):
    fake_json = {
        "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.1761]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"start": "2026-05-08T00:00:00.000+02:00"}]}]}},
    }
    mock_ecb_response(monkeypatch, 200, fake_json)

    provider = EcbProvider()
    result = provider.fetch(make_asset(), last_timestamp=None)
    assert result == [{"timestamp": 1778191200, "fields": {"price": 1.1761}}]


def test_ecb_fetch_non_200(monkeypatch, capsys):
    mock_ecb_response(monkeypatch, 500, "", "Internal Server Error")

    provider = EcbProvider()
    result = provider.fetch(make_asset(), last_timestamp=None)

    assert result == []
    assert "status 500 (Internal Server Error)" in capsys.readouterr().err


MALFORMED_CASES = [
    ({}, "missing key 'dataSets'", "price"),
    ({"dataSets": []}, "missing index [0]", "price"),
    ({"dataSets": [{"series": {}}]}, "missing key '0:0:0:0:0'", "price"),
    ({"dataSets": [{"series": {"0:0:0:0:0": {"observations": {}}}}]}, "missing key '0'", "price"),
    (
        {"dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": 1.234}}}}]},
        "cannot index with [0] into float",
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
def test_ecb_malformed_json(monkeypatch, capsys, json_data, expected, context):
    mock_ecb_response(monkeypatch, 200, json_data)

    provider = EcbProvider()
    result = provider.fetch(make_asset(), None)

    assert result == []

    err = capsys.readouterr().err
    assert expected in err
    assert f"in path for {context}" in err
