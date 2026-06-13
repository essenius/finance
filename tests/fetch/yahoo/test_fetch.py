# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fetch.py

from unittest.mock import Mock, patch

# ----------------------------------------------------------------------
# _fetch_impl()
# ----------------------------------------------------------------------


def test_fetch_impl_success(yahoo_provider, unwrap):
    response = Mock()
    response.json.return_value = {"chart": {"result": [{"foo": "bar"}], "error": None}}
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    payload = unwrap(result)
    assert payload == {"foo": "bar"}


def test_fetch_impl_missing_chart(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {}
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    assert_error(result, "Could not interpret fetch response", "no 'chart' in response")


def test_fetch_impl_empty_result(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {"chart": {"result": []}}
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    assert_error(result, "Could not interpret fetch response", "result empty")


def test_fetch_impl_yahoo_error_object(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [{"foo": "bar"}],
            "error": {"code": "BadSymbol", "description": "Symbol not found"},
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider._fetch_impl("http://x", "m")

    assert_error(
        result, "Could not interpret fetch response", "{'code': 'BadSymbol', 'description': 'Symbol not found'}"
    )


# ----------------------------------------------------------------------
# fetch()
# ----------------------------------------------------------------------


def test_fetch_success(yahoo_provider, unwrap):
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "timestamp": [1000],
                    "indicators": {"quote": [{"close": [10.0]}]},
                    "meta": {},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        asset = {"symbol": "AAPL", "fields": ["close"], "interval": "1d"}
        result = yahoo_provider.fetch("m", asset, 900, 1100)

    payload = unwrap(result)
    assert len(payload) == 1
    assert payload[0].fields == {"close": 10.0}


def test_impl_http_error(yahoo_provider, assert_error):
    response = Mock()
    response.raise_for_status.side_effect = Exception("boom")

    with patch.object(yahoo_provider.session, "get", return_value=response):
        result = yahoo_provider.fetch("x", {"symbol": "y", "fields": [], "interval": "1d"}, 10, 100)

    assert_error(result, "Exception during Yahoo fetch", "boom")


def test_fetch_fallback_to_meta(yahoo_provider, unwrap):
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "timestamp": [],
                    "indicators": {"quote": [{}]},
                    "meta": {"regularMarketTime": 1000, "regularMarketPrice": 42.0},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        asset = {"symbol": "AAPL", "fields": ["close"], "interval": "1d"}
        result = yahoo_provider.fetch("m", asset, 900, 1100)

    payload = unwrap(result)
    assert len(payload) == 1
    assert payload[0].fields == {"close": 42.0}


def test_fetch_propagates_extract_candles_error(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [
                {
                    "timestamp": None,
                    "indicators": {"quote": [{}]},
                    "meta": {},
                }
            ],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        asset = {"symbol": "AAPL", "fields": ["close"], "interval": "1d"}
        result = yahoo_provider.fetch("m", asset, 900, 1100)

    assert_error(result, "Cannot synthesize from metadata", "timestamp missing")


"""
def test_fetch_resolve_field_mapping_failure(yahoo_provider, assert_error):
    response = Mock()
    response.json.return_value = {
        "chart": {
            "result": [{
                "timestamp": [1000],
                "indicators": {"quote": [{"close": [10.0]}]},
                "meta": {},
            }],
            "error": None,
        }
    }
    response.raise_for_status.return_value = None

    with patch.object(yahoo_provider.session, "get", return_value=response):
        asset = {"symbol": "AAPL", "fields": ["close", "foo"], "interval": "1d"}
        result = yahoo_provider.fetch("m", asset, 900, 1100)

    assert_error(result, "Unsupported field combination: ['close', 'foo']", None)


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
def test_error_response(yahoo_provider, data, expected_message):
    result = yahoo_provider._error_response(data)

    if expected_message is None:
        assert result is None
    else:
        assert result == expected_message


def test_fetch_success(yahoo_provider, monkeypatch):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"chart": {"result": [{}]}}

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_response)

    result = yahoo_provider._fetch("z", "EURUSD=X", "1d", "5d")

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
def test_fetch_errors(yahoo_provider, monkeypatch, response_setup, expected_error):
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

    result = yahoo_provider._fetch("r", "EURUSD=X", "1d", "5d")

    assert not result.ok
    assert expected_error in result.error
    assert "Exception during fetch" in result.reason


def test_fetch_returns_data_but_no_results(yahoo_provider, monkeypatch):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "chart": {
            "result": None,
            "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"},
        }
    }

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_response)
    result = yahoo_provider._fetch("s", "EURUSD=X", "1d", "5d")
    assert not result.ok
    assert result.reason == "Could not interpret fetch response"
    assert result.error == "{'code': 'Not Found', 'description': 'No data found, symbol may be delisted'}"
"""
