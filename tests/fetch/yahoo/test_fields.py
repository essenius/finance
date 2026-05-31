# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fields.py

import logging
from datetime import UTC, datetime

import pytest

from finance.fetch.yahoo import YahooProvider

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def make_provider(config=None):
    """Provider with deterministic now() and injected config."""

    class P(YahooProvider):
        def now(self):
            return datetime(2026, 5, 25, tzinfo=UTC)

    return P(config=config or {})


# ----------------------------------------------------------------------
# _map_fields() tests
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "candle, fields, expected, error",
    [
        # price mapping
        ({"fields": {"close": 123.45}}, ["price"], {"price": 123.45}, None),
        # subset mapping
        (
            {"fields": {"open": 1, "high": 2, "low": 3, "close": 4, "volume": 5}},
            ["open", "close"],
            {"open": 1.0, "close": 4.0},
            None,
        ),
        # mixed price + OHLC → error
        ({"fields": {"close": 10}}, ["price", "open"], None, ValueError),
        # unknown field → error
        ({"fields": {"close": 10}}, ["foo"], None, ValueError),
    ],
)
def test_map_fields_param(provider, candle, fields, expected, error):
    if error:
        with pytest.raises(error):
            provider._map_fields(candle, fields)
    else:
        assert provider._map_fields(candle, fields) == expected


# ----------------------------------------------------------------------
# _get_from_meta() tests
# ----------------------------------------------------------------------


META_CASES = [
    # full success
    (
        ["close", "high", "low", "volume"],
        {
            "regularMarketTime": 1000,
            "regularMarketPrice": 10.0,
            "regularMarketDayHigh": 12.0,
            "regularMarketDayLow": 8.0,
            "regularMarketVolume": 1000,
        },
        {
            "close": 10.0,
            "high": 12.0,
            "low": 8.0,
            "volume": 1000.0,
        },
        None,
    ),
    # partial success
    (
        ["close", "high", "low", "volume"],
        {
            "regularMarketTime": 1000,
            "regularMarketPrice": 10.0,
            "regularMarketDayHigh": None,
            "regularMarketDayLow": 8.0,
            "regularMarketVolume": None,
        },
        {
            "close": 10.0,
            "low": 8.0,
        },
        "metadata missing value for 'high'",
    ),
    # all missing → empty
    (
        ["close", "high", "low", "volume"],
        {
            "regularMarketTime": 1000,
            "regularMarketPrice": None,
            "regularMarketDayHigh": None,
            "regularMarketDayLow": None,
            "regularMarketVolume": None,
        },
        None,
        "metadata missing value for 'close'",
    ),
    # open requested → fail fast
    (
        ["open", "close"],
        {
            "regularMarketTime": 1000,
            "regularMarketPrice": 10.0,
        },
        None,
        "cannot synthesize 'open' from metadata",
    ),
    # unknown field → fail fast
    (
        ["close", "foo"],
        {
            "regularMarketTime": 1000,
            "regularMarketPrice": 10.0,
        },
        None,
        "unknown field 'foo'",
    ),
    # missing timestamp → empty
    (
        ["close"],
        {
            "regularMarketPrice": 10.0,
        },
        None,
        "timestamp missing in metadata",
    ),
]


@pytest.mark.parametrize("fields, meta, expected, err", META_CASES)
def test_get_from_meta_param(caplog, provider, fields, meta, expected, err):
    with caplog.at_level(logging.ERROR):
        result = provider._get_from_meta(fields, meta, "x")

    if expected is None:
        assert result == []
        if err is not None:
            assert err in caplog.text
        else:
            # no error expected → no log
            assert caplog.text == ""
    else:
        assert len(result) == 1
        assert result[0]["fields"] == expected

        if err is not None:
            assert err in caplog.text
        else:
            assert caplog.text == ""


def test_metadata_price_and_close_equivalent():
    provider = make_provider()
    meta = {
        "regularMarketTime": 1000,
        "regularMarketPrice": 42.0,
    }

    result = provider._get_from_meta(["price", "close"], meta)
    fields = result[0]["fields"]

    assert fields == {
        "price": 42.0,
        "close": 42.0,
    }
