# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_assets.py

from datetime import timedelta

from finance.common.model import Asset, Retention, Series, SeriesType
from finance.config.loader import normalize_assets_and_series


def test_normalize_assets_basic(unwrap):
    raw = {
        "eurusd": {
            "provider": {
                "name": "yahoo",
                "code": "EURUSD=X",
            },
            "symbol": "EURUSD",
            "tags": {
                "Instrument": "Forex",
            },
            "series": {
                "daily": {
                    "interval": "1d",
                    "series_type": "candle",
                    "retention": "long_lived",
                    "bootstrap_history": "5y",
                }
            },
        }
    }

    assets, series = unwrap(normalize_assets_and_series(raw, {}))

    asset: Asset = assets[0]
    assert asset.provider == "yahoo"
    assert asset.provider_code == "EURUSD=X"
    assert asset.name == "eurusd"
    assert asset.symbol == "EURUSD"
    assert asset.instrument == "Forex"

    # series fields preserved / defaulted
    series: Series = series[0]
    assert series.name == "eurusd:daily"
    assert series.interval == "1d"
    assert series.interval_delta() == timedelta(days=1)
    assert series.bootstrap_history == "5y"
    assert series.bootstrap_history_delta() == timedelta(days=365.25 * 5)
    assert series.series_type == SeriesType.CANDLE
    assert series.retention == Retention.LONG_LIVED


def test_normalize_assets_missing_required_field(assert_error):
    raw = {
        "eurusd": {
            # "provider" is missing → should trigger ValueError
            "series": {"intraday": {"interval": "10m"}},
        }
    }

    result = normalize_assets_and_series(raw, {})
    assert_error(result, "Could not parse asset 'eurusd'", "Missing required field 'provider'")


def test_normalize_assets_malformed_provider(assert_error):
    raw = {
        "eurusd": {
            "provider": "yahoo",
            "series": {"intraday": {"interval": "10m"}},
        }
    }

    result = normalize_assets_and_series(raw, {})
    assert_error(result, "Could not parse asset 'eurusd'", "malformed provider section")


def test_normalize_assets_missing_interval(assert_error):
    raw = {
        "spx": {
            "provider": {
                "name": "yahoo",
                "code": "^GSPC",
            },
            "symbol": "SPX",
            "series": {"daily": {"retention": "bogus"}},
        }
    }
    result = normalize_assets_and_series(raw, {})
    assert_error(result, "Could not parse asset 'spx'", "Missing required field 'interval'")


def test_normalize_assets_invalid_retention(assert_error):
    raw = {
        "spx": {
            "provider": {
                "name": "yahoo",
                "code": "^GSPC",
            },
            "symbol": "SPX",
            "series": {"daily": {"interval": "1d", "retention": "bogus"}},
        }
    }
    result = normalize_assets_and_series(raw, {})
    assert_error(
        result, "Could not parse asset 'spx'", "Invalid Retention: 'bogus'. Allowed: ['short_lived', 'long_lived']"
    )


def test_normalize_asset_with_template(unwrap):
    series_cfg = {
        "spx": {
            "provider": {
                "name": "yahoo",
                "code": "^GSPC",
            },
            "symbol": "SPX",
            "series": {"series1": "template1"},
        }
    }
    template = {"template1": {"interval": "1d"}}
    asset_list, series_list = unwrap(normalize_assets_and_series(series_cfg, template))
    assert len(asset_list) == 1
    assert len(series_list) == 1
    series: Series = series_list[0]
    assert series.interval == "1d"
    assert series.series_type == "candle", "default series type"
    assert series.retention == "long_lived", "default retention for >= 1d"
    assert series.name == "spx:series1"
    assert series.bootstrap_history == "10y", "default history for >= 1d"


def test_normalize_asset_missing_template(assert_error):
    series_cfg = {
        "spx": {
            "provider": {
                "name": "yahoo",
                "code": "^GSPC",
            },
            "symbol": "SPX",
            "series": {"series1": "template1"},
        }
    }
    result = normalize_assets_and_series(series_cfg, {})
    assert_error(result, "Could not parse asset 'spx'", "Could not find series template 'template1'")


"""
TODO delete
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

    assert len(assets) == 1
    assert assets[0].symbol == "SPX"
    assert len(series) == 1
    assert series[0].interval == "1d"
    assert series[0].history_limit == "10y"
"""
