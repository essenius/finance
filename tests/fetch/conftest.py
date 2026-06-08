# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/conftest.py

import time
from unittest.mock import Mock

import pytest
import requests

from finance.common.model import FetchResult


@pytest.fixture
def assert_ok():
    def _assert_ok(result: FetchResult, timestamp: int, value: float):
        assert result.ok
        point = result.payload[0]
        assert point.timestamp == timestamp
        assert point.fields == {"price": value}

    return _assert_ok


@pytest.fixture
def mock_get_response():

    def _mock_get_response(monkeypatch, target, status, json_data, text=None):
        mock_resp = Mock()
        mock_resp.status_code = status
        mock_resp.json.return_value = json_data

        if status == 200:
            mock_resp.raise_for_status.return_value = None
        else:
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(text or "boom")
        if text:
            mock_resp.text = text  # if text else json.dumps(json_data)

        monkeypatch.setattr(f"finance.fetch.{target}.requests.get", lambda *a, **k: mock_resp)

    return _mock_get_response


@pytest.fixture
def frozen_time(monkeypatch):
    now = 1_000_000_000
    monkeypatch.setattr(time, "time", lambda: now)
    return now
