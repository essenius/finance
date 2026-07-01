# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_providers.py

from finance.common.model import ProviderConfig
from finance.config.loader import normalize_providers


def test_normalize_providers_basic(unwrap):
    ecb = {
        "timezone": "Europe/Berlin",
        "daily_history_limit": "20y",
        "intraday_history_limit": "10d",
        "nonsense": "ignored",
    }

    fred = {"daily_series_type": "value"}

    providers = unwrap(normalize_providers({"ecb": ecb, "fred": fred, "bogus": "ignored"}))

    default_params = {
        "timezone": "UTC",
        "intraday_history_limit": "5d",
        "daily_history_limit": "10y",
        "intraday_interval": "5m",
        "daily_interval": "1d",
        "daily_series_type": "candle",
    }

    assert providers["yahoo"] == ProviderConfig(name="yahoo", **default_params)
    assert providers["ecb"] == ProviderConfig(
        name="ecb",
        **default_params | {"timezone": "Europe/Berlin", "intraday_history_limit": "10d", "daily_history_limit": "20y"},
    )
    assert providers["fred"] == ProviderConfig(name="fred", **(default_params | {"daily_series_type": "value"}))


def test_normalize_providers_wrong_timezone(assert_error):
    fred = {"timezone": "bogus"}
    providers = normalize_providers({"fred": fred})
    assert_error(providers, "Could not parse provider 'fred'", "Invalid timezone 'bogus'")


def test_normalize_providers_invalid_duration(assert_error):
    yahoo = {"daily_interval": "1q"}
    providers = normalize_providers({"yahoo": yahoo})
    assert_error(providers, "Could not parse provider 'yahoo'", "Invalid duration '1q'")
