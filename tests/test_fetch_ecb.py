# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_fetch_ecb.py

import json
from unittest.mock import Mock
from finance.fetch.ecb import fetch_ecb

def test_ecb_fetch_real_fixture(monkeypatch):
    with open("tests/data/ecb_eurusd.json") as f:
        fake_json = json.load(f)
    print(f"Loaded ECB fixture: {fake_json}")
    mock_resp = Mock()
    mock_resp.json.return_value = fake_json
    mock_resp.status_code = 200
    mock_resp.text = json.dumps(fake_json)

    # Patch requests.get to return your real fixture
    monkeypatch.setattr("finance.fetch.ecb.requests.get", lambda *a, **k: mock_resp)

    result = fetch_ecb("USD_EUR")

    assert result["value"] == 1.1761

    # ECB timestamp: 2026-05-08T00:00:00.000+02:00
    assert result["timestamp"] == 1778191200


def test_ecb_fetch_non_200(monkeypatch):
    mock_resp = Mock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    monkeypatch.setattr(
        "finance.fetch.ecb.requests.get",
        lambda *a, **k: mock_resp
    )

    result = fetch_ecb("USD_EUR")

    assert result["value"] is None
    assert result["timestamp"] is None

def test_ecb_fetch_malformed_json(monkeypatch):
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.text = "{}"
    mock_resp.json.return_value = {}  # missing everything

    monkeypatch.setattr(
        "finance.fetch.ecb.requests.get",
        lambda *a, **k: mock_resp
    )

    result = fetch_ecb("USD_EUR")

    assert result["value"] is None
    assert result["timestamp"] is None
