# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_providers.py

from datetime import timedelta

from finance.common.model import ProviderConfig
from finance.config.loader import normalize_providers


def test_normalize_providers_basic(unwrap):
    ecb = {
        "timeout": "20s",
        "nonsense": "ignored",
        "constraints": {"history_limits": {"default": "60d", "1d": None}},
        "overlap": {"default": "0"},
    }

    fred = {}

    providers = unwrap(normalize_providers({"ecb": ecb, "fred": fred, "bogus": "ignored"}))

    default_params = {"timeout": "10s", "history_limits": {}, "sweep": {}}

    assert providers["yahoo"] == ProviderConfig(name="yahoo", **default_params), "Yahoo"
    assert providers["fred"] == ProviderConfig(name="fred", **default_params), "FRED"
    assert providers["ecb"] == ProviderConfig(
        name="ecb",
        timeout="20s",
        history_limits={timedelta(0): timedelta(days=60), timedelta(days=1): None},
        sweep={},
    ), "ECB"


def test_normalize_providers_wrong_timeout(assert_error):
    fred = {"timeout": "bogus"}
    providers = normalize_providers({"fred": fred})
    assert_error(providers, "Could not parse provider 'fred'", "Invalid duration 'bogus' in timeout")
