# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_assets.py

from datetime import timedelta

from finance.common.json_utils import JsonReader
from finance.common.model import Asset, ProviderProtocol, Series
from finance.common.string_enums import Retention, SeriesType
from finance.common.types import Unwrap
from finance.config.loader import BusinessConfig, normalize_assets_and_series
from tests.support.types import AssertError, Creator


def test_normalize_assets_basic(unwrap: Unwrap[BusinessConfig], make_providers: Creator[dict[str, ProviderProtocol]]):
    reader = JsonReader(
        {
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
    )

    business = unwrap(normalize_assets_and_series(reader, JsonReader({}), make_providers()))

    asset: Asset = business.assets[0]
    assert asset.provider.name == "yahoo"
    assert asset.provider_code == "EURUSD=X"
    assert asset.name == "eurusd"
    assert asset.symbol == "EURUSD"
    assert asset.config_metadata is not None
    assert asset.config_metadata.instrument == "Forex"

    # series fields preserved / defaulted
    series: Series = business.series[0]
    assert series.name == "eurusd:daily"
    assert series.interval == "1d"
    assert series.interval_delta() == timedelta(days=1)
    assert series.bootstrap_history == "5y"
    assert series.bootstrap_history_delta() == timedelta(days=365.25 * 5)
    assert series.series_type == SeriesType.CANDLE
    assert series.retention == Retention.LONG_LIVED


def test_normalize_assets_missing_required_field(
    assert_error: AssertError, make_providers: Creator[dict[str, ProviderProtocol]]
):
    reader = JsonReader(
        {
            "eurusd": {
                # "provider" is missing → should trigger ParseError
                "series": {"intraday": {"interval": "10m"}},
            }
        }
    )

    result = normalize_assets_and_series(reader, JsonReader({}), make_providers())
    assert_error(result, "Could not parse asset 'eurusd'", "['provider', 'name']: Missing required key `provider`")


def test_normalize_assets_malformed_provider(
    assert_error: AssertError, make_providers: Creator[dict[str, ProviderProtocol]]
):
    reader = JsonReader(
        {
            "eurusd": {
                "provider": "yahoo",
                "series": {"intraday": {"interval": "10m"}},
            }
        }
    )

    result = normalize_assets_and_series(reader, JsonReader({}), make_providers())
    assert_error(
        result, "Could not parse asset 'eurusd'", "['provider', 'name']: type `str` is not a container (level: 1)"
    )


def test_normalize_assets_missing_interval(
    assert_error: AssertError, make_providers: Creator[dict[str, ProviderProtocol]]
):
    reader = JsonReader(
        {
            "spx": {
                "provider": {
                    "name": "yahoo",
                    "code": "^GSPC",
                },
                "symbol": "SPX",
                "series": {"daily": {"retention": "bogus"}},
            }
        }
    )
    result = normalize_assets_and_series(reader, JsonReader({}), make_providers())
    assert_error(result, "Could not parse asset 'spx'", "['interval']: Missing required key `interval`")


def test_normalize_assets_invalid_retention(
    assert_error: AssertError, make_providers: Creator[dict[str, ProviderProtocol]]
):
    reader = JsonReader(
        {
            "spx": {
                "provider": {
                    "name": "yahoo",
                    "code": "^GSPC",
                },
                "symbol": "SPX",
                "series": {"daily": {"interval": "1d", "retention": "bogus"}},
            }
        }
    )
    result = normalize_assets_and_series(reader, JsonReader({}), make_providers())
    assert_error(
        result, "Could not parse asset 'spx'", "Invalid Retention: 'bogus'. Allowed: ['short_lived', 'long_lived']"
    )


def test_normalize_asset_with_template(
    unwrap: Unwrap[BusinessConfig], make_providers: Creator[dict[str, ProviderProtocol]]
):
    reader = JsonReader(
        {
            "spx": {
                "provider": {
                    "name": "yahoo",
                    "code": "^GSPC",
                },
                "symbol": "SPX",
                "series": {"series1": "template1"},
            }
        }
    )
    template_reader = JsonReader({"template1": {"interval": "1d"}})
    business: BusinessConfig = unwrap(normalize_assets_and_series(reader, template_reader, make_providers()))
    assert len(business.assets) == 1
    assert len(business.series) == 1
    series: Series = business.series[0]
    assert series.interval == "1d"
    assert series.series_type == "candle", "default series type"
    assert series.retention == "long_lived", "default retention for >= 1d"
    assert series.name == "spx:series1"
    assert series.bootstrap_history == "10y", "default history for >= 1d"


def test_normalize_asset_missing_template(
    assert_error: AssertError, make_providers: Creator[dict[str, ProviderProtocol]]
):
    reader = JsonReader(
        {
            "spx": {
                "provider": {
                    "name": "yahoo",
                    "code": "^GSPC",
                },
                "symbol": "SPX",
                "series": {"series1": "template1"},
            }
        }
    )
    result = normalize_assets_and_series(reader, JsonReader({}), make_providers())
    assert_error(result, "Could not parse asset 'spx'", "['template1']: Missing required key `template1`")
