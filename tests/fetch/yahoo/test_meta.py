# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_meta.py


def test_get_from_meta_full_success(yahoo_provider, unwrap):
    meta = {
        "regularMarketTime": 1000,
        "regularMarketPrice": 10.0,
        "regularMarketDayHigh": 12.0,
        "regularMarketDayLow": 8.0,
        "regularMarketVolume": 1000,
    }

    result = yahoo_provider._get_from_meta("x", ["close", "high", "low", "volume"], meta, 900, 1100)
    payload = unwrap(result)

    assert len(payload) == 1
    assert payload[0].fields == {"close": 10.0, "high": 12.0, "low": 8.0, "volume": 1000.0}


def test_get_from_meta_partial_success(yahoo_provider, unwrap):
    meta = {
        "regularMarketTime": 1000,
        "regularMarketPrice": 10.0,
        "regularMarketDayHigh": None,
        "regularMarketDayLow": 8.0,
        "regularMarketVolume": None,
    }

    result = yahoo_provider._get_from_meta("x", ["close", "high", "low", "volume"], meta, 900, 1100)
    payload = unwrap(result)

    assert len(payload) == 1
    assert payload[0].fields == {"close": 10.0, "low": 8.0}


def test_get_from_meta_all_missing(yahoo_provider, assert_error):
    meta = {
        "regularMarketTime": 1000,
        "regularMarketPrice": None,
        "regularMarketDayHigh": None,
        "regularMarketDayLow": None,
        "regularMarketVolume": None,
    }

    result = yahoo_provider._get_from_meta("x", ["close", "high", "low", "volume"], meta, 900, 1100)
    assert_error(result, "Cannot synthesize from metadata", "No fields synthesized")


def test_get_from_meta_open_requested_fails(yahoo_provider, assert_error):
    meta = {"regularMarketTime": 1000, "regularMarketPrice": 10.0}
    result = yahoo_provider._get_from_meta("x", ["open", "close"], meta, 900, 1100)
    assert_error(result, "Cannot synthesize from metadata", "Cannot synthesize 'open'")


def test_get_from_meta_unknown_field_maps_to_close(yahoo_provider, unwrap):
    meta = {"regularMarketTime": 1000, "regularMarketPrice": 42.0}
    result = yahoo_provider._get_from_meta("x", ["foo"], meta, 900, 1100)
    payload = unwrap(result)
    assert payload[0].fields == {"foo": 42.0}


def test_get_from_meta_no_timestamp(yahoo_provider, assert_error):
    meta = {"regularMarketPrice": 10.0}
    result = yahoo_provider._get_from_meta("x", ["close"], meta, 900, 1100)
    assert_error(result, "Cannot synthesize from metadata", "timestamp missing")


def test_get_from_meta_timestamp_outside_range(yahoo_provider, assert_error):
    meta = {"regularMarketTime": 500, "regularMarketPrice": 10.0}
    result = yahoo_provider._get_from_meta("x", ["close"], meta, 900, 1100)
    assert_error(result, "Cannot synthesize from metadata", "metadata timestamp outside requested range")


def test_get_from_meta_price_and_close_equivalent(yahoo_provider, unwrap):
    meta = {"regularMarketTime": 1000, "regularMarketPrice": 42.0}
    result = yahoo_provider._get_from_meta("x", ["price", "close"], meta, 900, 1100)
    payload = unwrap(result)
    assert payload[0].fields == {"price": 42.0, "close": 42.0}
