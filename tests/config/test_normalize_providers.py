# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_providers.py

from datetime import timedelta

from finance.common.model import ProviderConfig
from finance.config.loader import normalize_providers


def test_normalize_providers_basic(unwrap):
    ecb = {
        "timezone": "Europe/Berlin",
        "timeout": "20s",
        "nonsense": "ignored",
        "constraints": {"history_limits": {"default": "60d", "1d": None}},
    }

    fred = {}

    providers = unwrap(normalize_providers({"ecb": ecb, "fred": fred, "bogus": "ignored"}))

    default_params = {"timezone": "UTC", "timeout": "10s", "history_limits": {}}

    assert providers["yahoo"] == ProviderConfig(name="yahoo", **default_params), "Yahoo"
    assert providers["fred"] == ProviderConfig(name="fred", **default_params), "FRED"
    assert providers["ecb"] == ProviderConfig(
        name="ecb",
        timezone="Europe/Berlin",
        timeout="20s",
        history_limits={timedelta(0): timedelta(days=60), timedelta(days=1): None},
    ), "ECB"


def test_normalize_providers_wrong_timezone(assert_error):
    fred = {"timezone": "bogus"}
    providers = normalize_providers({"fred": fred})
    assert_error(providers, "Could not parse provider 'fred'", "Invalid timezone 'bogus'")


"""
def test_normalize_providers_invalid_duration(assert_error):
    yahoo = {"daily_interval": "1q"}
    providers = normalize_providers({"yahoo": yahoo})
    assert_error(providers, "Could not parse provider 'yahoo'", "Invalid duration '1q'")
"""
