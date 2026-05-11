# finance/tests/test_fetch_fred.py
from unittest.mock import Mock

import pytest
from finance.fetch.fred import fetch_fred_series

def test_fred_fetch_normal(monkeypatch):
    fake_json = {
        "observations": [
            {"value": "2.34", "date": "2024-05-09"}
        ]
    }

    mock_resp = Mock()
    mock_resp.json.return_value = fake_json
    monkeypatch.setattr("finance.fetch.fred.requests.get", lambda *a, **k: mock_resp)

    result = fetch_fred_series("T10YIE", {})
    print(f"Fetched FRED result: {result}")
    assert result["value"] == 2.34
    assert result["timestamp"] == 1715212800  # 2024-05-09

def test_fred_fetch_empty_observations(monkeypatch):
    fake_json = {"observations": []}

    mock_resp = Mock()
    mock_resp.json.return_value = fake_json
    monkeypatch.setattr("finance.fetch.fred.requests.get", lambda *a, **k: mock_resp)

    result = fetch_fred_series("T10YIE", {})

    assert result["value"] is None
    assert result["timestamp"] is None

@pytest.mark.parametrize("bad_value", ["", ".", None])
def test_fred_fetch_missing_value(monkeypatch, bad_value):
    fake_json = {
        "observations": [
            {"value": bad_value, "date": "2024-05-09"}
        ]
    }

    mock_resp = Mock()
    mock_resp.json.return_value = fake_json
    monkeypatch.setattr("finance.fetch.fred.requests.get", lambda *a, **k: mock_resp)

    result = fetch_fred_series("T10YIE", {})

    assert result["value"] is None
    assert result["timestamp"] is None


def test_fred_fetch_network_error(monkeypatch):
    def boom(*a, **k):
        raise Exception("network down")

    monkeypatch.setattr("finance.fetch.fred.requests.get", boom)

    result = fetch_fred_series("T10YIE", {})

    assert result["value"] is None
    assert result["timestamp"] is None