# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_fields.py

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
        None,
        ["missing value for 'high'", "missing value for 'volume'"],
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
        None,
        [
            "missing value for 'close'",
            "missing value for 'high'",
            "missing value for 'low'",
            "missing value for 'volume'",
        ],
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
        None,
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
        None,
    ),
    # missing timestamp → empty
    (
        ["close"],
        {
            "regularMarketPrice": 10.0,
        },
        None,
        "timestamp missing",
        None,
    ),
]


@pytest.mark.parametrize("fields, meta, expected, err, warn", META_CASES)
def test_get_from_meta_param(provider, fields, meta, expected, err, warn):
    result = provider._get_from_meta("x", fields, meta)

    if expected is None:
        assert not result.ok
        assert "Cannot synthesize from metadata" in result.reason
        if err is None:
            assert result.error is None
        else:
            assert err in result.error
        return
    else:
        assert result.reason is None
        assert result.ok

    if warn is None:
        assert result.warning is None
    else:
        for warning in warn:
            assert warning in result.warning

    payload = result.payload
    if expected is None:
        assert payload == []
    else:
        assert len(payload) == 1
        assert payload[0].fields == expected


def test_metadata_price_and_close_equivalent():
    provider = make_provider()
    meta = {
        "regularMarketTime": 1000,
        "regularMarketPrice": 42.0,
    }

    result = provider._get_from_meta("y", ["price", "close"], meta)
    assert result.ok
    fields = result.payload[0].fields

    assert fields == {
        "price": 42.0,
        "close": 42.0,
    }
