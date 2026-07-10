# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_fred.py

from datetime import UTC, datetime

import pytest


def test_fred_fetch_normal_with_skipped(fred_provider, assert_ok, make_asset, make_series, fixed_now):

    provider = fred_provider()
    provider.session.queue(
        status=200,
        json_data={
            "observations": [
                {"value": "2.34", "date": "2024-05-09"},
                {"value": "", "date": "2024-05-10"},
                {"value": ".", "date": "2024-05-11"},
                {"value": None, "date": "2024-05-12"},
                {"value": "2.55", "date": "bogus"},
            ]
        },
    )
    asset = make_asset(provider_code="T10YIE")
    now = fixed_now()  # ignored but we need a value
    result = provider.fetch(make_series(asset), asset, now, now, True)
    # no change in date as the date is a label, not a timestamp
    assert_ok(result, datetime(2024, 5, 9, 0, 0, 0, tzinfo=UTC), 2.34)
    assert len(result.payload) == 1, "Ignored invalid values"


# -------------------------------
# PARAMETRIZED MALFORMED CASES
# -------------------------------

MALFORMED_CASES = [
    # Missing API key (provider-level behavior)
    (
        None,  # api_key
        {"observations": [{"value": "2.34", "date": "2024-05-09"}]},
        "FRED requires an API key",
    ),
    # Observations missing entirely
    (
        "TESTKEY",
        {"foo": "bar"},
        "no 'observations' in response",
    ),
    # Observations empty
    (
        "TESTKEY",
        {"observations": []},
        "no 'observations' in response",
    ),
]


@pytest.mark.parametrize("api_key, json_data, expected_error", MALFORMED_CASES)
def test_fred_malformed_cases(
    assert_error, fred_provider, make_asset, make_series, api_key, json_data, expected_error, fixed_now
):
    provider = fred_provider(api_key)
    # Missing API key → no HTTP call
    if api_key is not None:
        provider.session.queue(200, json_data)

    now = fixed_now()  # again, ignored
    asset = make_asset(provider_code="T10YIE")
    result = provider.fetch(make_series(asset), asset, now, now, True)
    assert_error(result, expected_error, None)


def test_fred_fetch_network_error(assert_error, fred_provider, make_asset, make_series, fixed_now):
    provider = fred_provider()
    provider.session.queue_error(Exception("Boom!"))

    asset = make_asset(provider_code="T10YIE")
    now = fixed_now()
    result = provider.fetch(make_series(asset), asset, now, now, True)

    assert_error(result, "Exception during FRED fetch", "Boom!")


def test_fred_status_code_not_200(assert_error, fred_provider, make_asset, make_series, fixed_now):
    provider = fred_provider()
    provider.session.queue(500, {}, "status 500")
    asset = make_asset(provider_code="T10YIE")
    now = fixed_now()
    result = provider.fetch(make_series(asset), asset, now, now, True)
    assert_error(result, "Exception during FRED fetch", "status 500")
