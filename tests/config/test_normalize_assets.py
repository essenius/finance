# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_assets.py

from finance.common.model import DAILY, INTRADAY, Asset, Resolution, Series
from finance.config.loader import normalize_assets_and_series, normalize_providers


def test_normalize_assets_basic(unwrap):
    raw = {
        "eurusd": {
            "provider": "yahoo",
            "provider_code": "EURUSD=X",
            "symbol": "EURUSD",
            "tags": {
                "Instrument": "Forex",
            },
            "resolution": {INTRADAY: {"interval": "10m", "history_limit": "4d"}},
        }
    }

    assets, series = unwrap(normalize_assets_and_series(raw, {}))

    # loader expands into eurusd_intraday
    asset: Asset = assets["eurusd"]

    assert asset.provider == "yahoo"
    assert asset.provider_code == "EURUSD=X"
    assert asset.name == "eurusd"
    assert asset.symbol == "EURUSD"
    assert asset.instrument == "Forex"

    # series fields preserved / defaulted
    series: Series = series["eurusd_intraday"]
    assert series.interval == "10m"
    assert series.interval_seconds == 600
    assert series.history_limit == "4d"
    assert series.history_limit_seconds == 345600
    assert series.series_type == "value"
    assert series.resolution == Resolution.INTRADAY


def test_normalize_assets_missing_required_field(assert_error):
    raw = {
        "eurusd": {
            # "provider" is missing → should trigger ValueError
            "provider_code": "EURUSD=X",
            "resolution": {INTRADAY: {"interval": "10m"}},
        }
    }

    assert_error(
        normalize_assets_and_series(raw, {}),
        "Error parsing assets",
        "Missing required field 'provider' in asset 'eurusd'",
    )


def test_normalize_assets_unknown_resolution(assert_error):
    raw = {
        "spx": {
            "provider": "yahoo",
            "provider_code": "^GSPC",
            "symbol": "SPX",
            "resolution": {"boom": {}},
        }
    }
    result = normalize_assets_and_series(raw, {})
    assert_error(
        result, "Error parsing assets", "Invalid Resolution in asset 'spx': 'boom'. Allowed: ['intraday', 'daily']"
    )


def test_normalize_assets_default_resolution_settings(unwrap):
    raw = {
        "spx": {
            "provider": "yahoo",
            "provider_code": "^GSPC",
            "symbol": "SPX",
            "resolution": {DAILY: {}},
        }
    }

    providers = unwrap(normalize_providers({}))
    assets, series = unwrap(normalize_assets_and_series(raw, providers))

    assert assets["spx"].symbol == "SPX"
    assert series[f"spx_{DAILY}"].interval == "1d"
    assert series[f"spx_{DAILY}"].history_limit == "10y"
