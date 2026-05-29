# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_url.py

from finance.fetch.yahoo import YahooProvider


def test_build_url_basic():
    """_build_url must assemble a correct Yahoo URL with interval=1d and range."""
    provider = YahooProvider()

    url = provider._build_url("EURUSD=X", "1d", "3d")

    # Symbol must be encoded
    assert "EURUSD%3DX" in url

    # Query parameters must be present
    assert "interval=1d" in url
    assert "range=3d" in url
    assert "includePrePost=false" in url
    assert "events=div%2Csplits" in url


def test_build_url_symbol_encoding():
    """Symbols with special characters must be encoded correctly."""
    provider = YahooProvider()

    url = provider._build_url("BTC-USD", "1m", "5d")

    # Dash is safe, so it stays
    assert "BTC-USD" in url

    url2 = provider._build_url("^GSPC", "1d", "5d")

    # Caret must be encoded
    assert "%5EGSPC" in url2


def test_build_url_does_not_include_periods():
    """_build_url must never include period1 or period2."""
    provider = YahooProvider()

    url = provider._build_url("EURUSD=X", "1m", "7d")

    assert "period1" not in url
    assert "period2" not in url
