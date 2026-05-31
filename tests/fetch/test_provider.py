# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_provider.py

import logging
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from finance.fetch.provider import MarketDataProvider


class DummyProvider(MarketDataProvider):
    def fetch(self, asset, last_timestamp):
        return []


def test_init_defaults():
    p = DummyProvider()

    # config defaults to empty dict
    assert p.config == {}

    # now_provider defaults to a callable returning UTC datetime
    now = p.now()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_check_status_ok(caplog):
    p = DummyProvider()

    resp = Mock()
    resp.status_code = 200
    resp.text = ""

    with caplog.at_level(logging.ERROR):
        assert p._check_status("ABC", resp) is True

    # No errors logged
    assert caplog.text == ""


def test_check_status_non_200(caplog):
    p = DummyProvider()

    resp = Mock()
    resp.status_code = 500
    resp.text = "Internal Server Error"

    with caplog.at_level(logging.ERROR):
        assert p._check_status("XYZ", resp) is False

    assert "Error fetching Dummy data for XYZ: status 500 (Internal Server Error)" in caplog.text



def test_check_status_non_200_without_text(caplog):
    p = DummyProvider()

    resp = Mock()
    resp.status_code = 500
    resp.text = None

    with caplog.at_level(logging.ERROR):
        assert p._check_status("XYZ", resp) is False

    assert "Error fetching Dummy data for XYZ: status 500" in caplog.text


@pytest.mark.parametrize(
    "args, expected",
    [
        (("boom", "EURUSD"), "Error fetching Dummy data for EURUSD: boom"),
        (("boom",), "Error fetching Dummy data: boom"),
    ],
)
def test_error_prints_and_returns_empty(args, expected, caplog):
    p = DummyProvider()

    with caplog.at_level(logging.ERROR):
        result = p.error(*args)

    assert result == []
    assert expected in caplog.text


def test_require_api_key_missing(caplog):
    p = DummyProvider(config={})  # no api_key

    with caplog.at_level(logging.ERROR):
        key = p._require_api_key("AAPL")

    assert key is None
    assert "API key missing" in caplog.text


def test_require_api_key_present(caplog):
    p = DummyProvider(config={"api_key": "SECRET"})

    with caplog.at_level(logging.ERROR):
        key = p._require_api_key("AAPL")

    assert key == "SECRET"
    assert caplog.text == ""  # no error logged


def test_safe_success():
    p = DummyProvider()

    def good():
        return [1, 2, 3]

    result = p._safe("ABC", good)
    assert result == [1, 2, 3]


def test_safe_exception(caplog):
    p = DummyProvider()

    def bad():
        raise ValueError("kaboom")

    with caplog.at_level(logging.ERROR):
        result = p._safe("ABC", bad)

    assert result == []  # safe wrapper returns empty list
    assert "Error fetching Dummy data for ABC: kaboom" in caplog.text


# -------------------------
# _safe_get tests
# -------------------------


def test_safe_get_ok():
    p = DummyProvider()
    data = {"a": [{"b": 123}]}

    value, err = p._safe_get(data, ["a", 0, "b"])
    assert value == 123
    assert err is None


@pytest.mark.parametrize(
    "data, path, expected",
    [
        ({"a": {}}, ["a", "b"], "missing key 'b'"),
        ({"a": []}, ["a", 0], "missing index [0]"),
        ({"a": 42}, ["a", 0], "cannot index with [0] into int"),
    ],
)
def test_safe_get_errors(data, path, expected):
    p = DummyProvider()
    value, err = p._safe_get(data, path)
    assert value is None
    assert err == expected


def test_fetch_not_implemented():

    with pytest.raises(NotImplementedError):
        MarketDataProvider().fetch({"symbol": "ABC", "fields": ["price"]}, last_timestamp=None)
