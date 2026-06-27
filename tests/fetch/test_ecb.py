# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_ecb.py

import json

import pytest


def test_ecb_fetch_real_fixture(ecb_provider, assert_ok, make_asset, make_series):
    with open("tests/data/ecb_eurusd.json") as f:
        fake_json = json.load(f)

    provider = ecb_provider()
    provider.session.queue(200, fake_json)

    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)
    # timestamps are for May 8, 2026 in CEST
    result = provider.fetch(series, asset, start_timestamp=1778191200, end_timestamp=1778277599)
    # time stamp must be May 8, 2026 00:00 UTC
    assert_ok(result, timestamp=1778198400, value=1.1761)


def test_ecb_fetch_ok(ecb_provider, assert_ok, make_asset, make_series):
    fake_json = {
        "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.1761]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"id": "2026-05-08"}]}]}},
    }

    provider = ecb_provider()
    provider.session.queue(200, fake_json)
    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)

    result = provider.fetch(series, asset, start_timestamp=1778191200, end_timestamp=1778277599)
    assert_ok(result, timestamp=1778198400, value=1.1761)


@pytest.mark.parametrize(
    "provider_code",
    [
        "EUR",
        "EUR_USD_GBP",
        "_",
    ],
)
def test_ecb_fetch_wrong_provider_code(ecb_provider, make_series, make_asset, provider_code):
    provider = ecb_provider()
    provider.session.queue(200, {})

    asset = make_asset(provider_code=provider_code)
    series = make_series(asset)

    result = provider.fetch(series, asset, start_timestamp=1778191200, end_timestamp=1778277599)
    assert not result.ok
    assert f"Could not split provider code '{provider_code}' into base_quote" in result.reason
    assert result.payload is None


def test_ecb_fetch_non_200(ecb_provider, assert_error, make_asset, make_series):
    provider = ecb_provider()
    provider.session.queue(500, "", "Internal Server Error")

    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)
    result = provider.fetch(series, asset, 0, 0)
    assert_error(result, "Exception during ECB fetch of eur_usd_intraday", "Internal Server Error")


MALFORMED_CASES = [
    ({}, "missing key 'dataSets'", "series"),
    ({"dataSets": []}, "missing index [0]", "series"),
    ({"dataSets": [{"series": {}}]}, "missing key '0:0:0:0:0'", "series entry"),
    ({"dataSets": [{"series": {"0:0:0:0:0": {}}}]}, "missing key 'observations'", "observations"),
    (
        {
            "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.234]}}}}],
            "structure": {"dimensions": {"observation": []}},
        },
        "missing index [0]",
        "date metadata",
    ),
]


@pytest.mark.parametrize("json_data, expected, context", MALFORMED_CASES)
def test_ecb_malformed_json(ecb_provider, make_asset, make_series, json_data, expected, context, assert_error):
    provider = ecb_provider()
    provider.session.queue(200, json_data)

    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)
    result = provider.fetch(series, asset, 0, 0)
    assert_error(result, f"Could not find ECB {context}", expected)


def test_ecb_fetch_multiple_points_skip_invalid(unwrap, ecb_provider, make_series, make_asset):
    fake_json = {
        "dataSets": [
            {
                "series": {
                    "0:0:0:0": {
                        "observations": {
                            "0": [1.10],
                            "1": [],
                            "2": 1.11,  # not a list
                            "3": [None],
                            "4": [0],
                            "5": [1.12],
                        }
                    }
                }
            }
        ],
        "structure": {
            "dimensions": {
                "observation": [
                    {
                        "values": [
                            {"id": "2024-01-01"},
                            {"id": "2024-01-02"},
                            {"id": "2024-01-03"},
                            {"id": "2024-01-04"},
                            {"id": "bogus"},
                            {"id": "2024-01-05"},
                        ]
                    }
                ]
            }
        },
    }

    provider = ecb_provider()
    provider.session.queue(
        200,
        fake_json,
        make_series,
    )
    asset = make_asset(provider_code="EUR_USD")
    series = make_series(asset)
    points = unwrap(provider.fetch(series, asset, 0, 0))

    assert len(points) == 2
    assert points[0].value == 1.10
    assert points[1].value == 1.12
