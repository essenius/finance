# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_providers.py

from finance.config.loader import normalize_providers


def test_normalize_providers_basic(unwrap):
    ecb = {
        "timezone": "Europe/Berlin",
        "daily_history_limit": "20y",
        "intraday_history_limit": "10d",
        "nonsense": "ignored",
    }
    providers = unwrap(normalize_providers({"ecb": ecb, "bogus": "ignored"}))

    assert providers == {
        "yahoo": {"timezone": "UTC", "intraday_history_limit": "5d", "daily_history_limit": "10y"},
        "ecb": {"timezone": "Europe/Berlin", "intraday_history_limit": "10d", "daily_history_limit": "20y"},
        "fred": {"timezone": "UTC", "intraday_history_limit": "5d", "daily_history_limit": "10y"},
    }


def test_normalize_providers_wrong_timezone(assert_error):
    fred = {"timezone": "bogus"}
    providers = normalize_providers({"fred": fred})
    assert_error(providers, "Invalid timezone 'bogus' for provider 'fred'", None)
