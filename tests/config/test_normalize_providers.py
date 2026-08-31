# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_providers.py

from datetime import timedelta

from finance.common.configuration import ProviderConfig
from finance.common.json_utils import JsonObject, JsonReader
from finance.common.types import Unwrap
from finance.config.loader import normalize_providers
from tests.support.types import AssertError


def test_normalize_providers_basic(unwrap: Unwrap[dict[str, ProviderConfig]]):
    ecb: JsonObject = {
        "timeout": "20s",
        "nonsense": "ignored",
        "constraints": {"history_limits": {"default": "60d", "1d": None}},
        "overlap": {"default": "0"},
    }

    fred: JsonObject = {"api_key_required": True, "api_key": "secret"}

    providers = unwrap(normalize_providers(JsonReader({"ecb": ecb, "fred": fred, "bogus": "ignored"}), {}))

    default_params = {"timeout": "10s", "history_limits": {}, "sweep": {}}

    assert providers["yahoo"] == ProviderConfig(name="yahoo", api_key_required=False, **default_params), "Yahoo"
    assert providers["fred"] == ProviderConfig(
        name="fred", api_key_required=True, api_key="secret", **default_params
    ), "FRED"
    assert providers["ecb"] == ProviderConfig(
        name="ecb",
        api_key_required=False,
        timeout="20s",
        api_key=None,
        history_limits={timedelta(0): timedelta(days=60), timedelta(days=1): None},
        sweep={},
    ), "ECB"


def test_normalize_providers_wrong_timeout(assert_error: AssertError):
    fred: JsonObject = {"timeout": "bogus"}
    providers = normalize_providers(JsonReader({"fred": fred}), {})
    assert_error(providers, "Could not parse provider 'fred'", "Invalid duration 'bogus' in timeout")


def test_normalize_providers_no_required_api_key(assert_error: AssertError):
    fred: JsonObject = {"api_key_required": True}
    providers = normalize_providers(JsonReader({"fred": fred}), {})
    assert_error(providers, "Could not parse provider 'fred'", "Required API key not found in FRED_API_KEY")
