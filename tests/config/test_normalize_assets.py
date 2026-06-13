# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_assets.py

from finance.config.loader import CANDLE, PRICE, normalize_assets, normalize_providers


def test_normalize_assets_basic(unwrap):
    raw = {
        "eurusd": {
            "provider": "yahoo",
            "symbol": "EURUSD=X",
            "tags": {
                "Symbol": "EURUSD",
                "Instrument": "forex",
            },
            "timeseries": {"intraday": {"interval": "10m", "history_limit": "4d"}},
        }
    }

    assets = unwrap(normalize_assets(raw, {}, {}, {}))

    # loader expands into eurusd_intraday
    assert "eurusd_intraday" in assets
    a = assets["eurusd_intraday"]

    assert a["provider"] == "yahoo"
    assert a["symbol"] == "EURUSD=X"

    # tags normalized to lowercase
    assert a["tags"]["symbol"] == "EURUSD"
    assert a["tags"]["instrument"] == "forex"

    # timeseries fields preserved / defaulted
    assert a["interval"] == "10m"
    assert a["interval_seconds"] == 600
    assert a["history_limit"] == "4d"
    assert a["history_limit_seconds"] == 345600

    assert a["fields"] == PRICE


def test_normalize_assets_field_not_allowed(assert_error):
    raw = {
        "eurusd": {
            "provider": "yahoo",
            "symbol": "EURUSD=X",
            "tags": {
                "Symbol": "EURUSD",
                "Instrument": "forex",
            },
            "timeseries": {
                "intraday": {
                    "interval": "10m",
                    "fields": ["bogus"],
                }
            },
        }
    }

    result = normalize_assets(raw, {}, {}, {})
    assert_error(
        result, "Cannot redefine field set for intraday timeseries (is always 'price') in asset 'eurusd'", None
    )


def test_normalize_assets_default_fields(unwrap):
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {
                "daily": {
                    "interval": "1d"
                    # no fields → default to CANDLE
                }
            },
        }
    }

    field_sets = {"candle": CANDLE}
    assets = unwrap(normalize_assets(raw, field_sets, {}, {"yahoo": {"daily_history_limit": "9y"}}))
    a = assets["spx_daily"]

    assert a["fields"] == CANDLE


def test_normalize_assets_allow_price_on_daily(unwrap):
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {"daily": {"interval": "1d", "fields": "price"}},
        }
    }

    field_sets = {"candle": CANDLE, "price": PRICE}
    providers = unwrap(normalize_providers({}))
    assets = unwrap(normalize_assets(raw, field_sets, {}, providers))
    a = assets["spx_daily"]

    assert a["fields"] == PRICE


def test_normalize_assets_field_set_expansion(unwrap):
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {"daily": {"interval": "1d", "fields": "ohlc"}},
        }
    }

    field_sets = {"ohlc": ["open", "high", "low", "close"]}
    providers = unwrap(normalize_providers({}))

    assets = unwrap(normalize_assets(raw, field_sets, {}, providers))
    a = assets["spx_daily"]

    assert a["fields"] == ["open", "high", "low", "close"]


def test_normalize_assets_bucket_flattening(unwrap):
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {
                "intraday": {"interval": "10m"},
                "daily": {"interval": "1d"},
            },
        }
    }

    buckets = {"intraday": "b_intraday", "daily": "b_daily"}
    field_sets = {"candle": CANDLE}
    providers = unwrap(normalize_providers({}))

    assets = unwrap(normalize_assets(raw, field_sets, buckets, providers))

    assert assets["spx_intraday"]["bucket"] == "b_intraday"
    assert assets["spx_daily"]["bucket"] == "b_daily"


def test_normalize_assets_missing_required_field(assert_error):
    raw = {
        "eurusd": {
            # "provider" is missing → should trigger ValueError
            "symbol": "EURUSD=X",
            "timeseries": {"intraday": {"interval": "10m"}},
        }
    }

    assert_error(normalize_assets(raw, {}, {}, {}), "Missing required field 'provider' in asset 'eurusd'", None)


def test_normalize_assets_unknown_series(assert_error):
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {"boom": {}},
        }
    }

    assert_error(normalize_assets(raw, {}, {}, {}), "Unknown timeseries name 'boom' in asset 'spx'", None)


def test_normalize_assets_missing_interval(assert_error):
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {
                "daily": {
                    # missing interval
                }
            },
        }
    }

    field_sets = {"candle": CANDLE}

    assert_error(
        normalize_assets(raw, field_sets, {}, {}),
        "Missing required field 'interval' in timeseries 'daily' in asset 'spx'",
        None,
    )


def test_normalize_assets_unknown_field_set(assert_error):
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {"daily": {"interval": "1d", "fields": "does_not_exist"}},
        }
    }

    field_sets = {"ohlc": ["open", "high", "low", "close"]}

    assert_error(normalize_assets(raw, field_sets, {}, {}), "Unknown field set 'does_not_exist' in asset 'spx'", None)
