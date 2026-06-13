# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_ecb.py

import json

import pytest

# Helper


def make_asset(symbol="EUR_USD", field="price"):
    return {"symbol": symbol, "fields": [field]}


# Tests


def test_ecb_fetch_real_fixture(ecb_provider, assert_ok):
    with open("tests/data/ecb_eurusd.json") as f:
        fake_json = json.load(f)

    provider = ecb_provider()
    provider.session.queue(200, fake_json)

    # timestamps are for May 8, 2026 in CEST
    result = provider.fetch("eurusd_1", make_asset(), start_timestamp=1778191200, end_timestamp=1778277599)
    # time stamp must be May 8, 2026 00:00 UTC
    assert_ok(result, timestamp=1778198400, value=1.1761)


def test_ecb_fetch_ok(ecb_provider, assert_ok):
    fake_json = {
        "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.1761]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"id": "2026-05-08"}]}]}},
    }

    provider = ecb_provider()
    provider.session.queue(200, fake_json)
    result = provider.fetch("eurusd_2", make_asset(), start_timestamp=1778191200, end_timestamp=1778277599)
    assert_ok(result, timestamp=1778198400, value=1.1761)


@pytest.mark.parametrize(
    "symbol",
    [
        "EUR",
        "EUR_USD_GBP",
        "_",
    ],
)
def test_ecb_fetch_wrong_symbol(ecb_provider, symbol):
    provider = ecb_provider()
    provider.session.queue(200, {})
    result = provider.fetch("eurusd_3", make_asset(symbol=symbol), start_timestamp=1778191200, end_timestamp=1778277599)
    assert not result.ok
    assert f"Could not split symbol '{symbol}' into base_quote" in result.reason
    assert result.payload is None


def test_ecb_fetch_non_200(ecb_provider, assert_error):
    provider = ecb_provider()
    provider.session.queue(500, "", "Internal Server Error")
    result = provider.fetch("eurusd_http", make_asset(), 0, 0)
    assert_error(result, "Exception during ECB fetch of EUR_USD", "Internal Server Error")


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
def test_ecb_malformed_json(ecb_provider, json_data, expected, context, assert_error):
    provider = ecb_provider()
    provider.session.queue(200, json_data)
    result = provider.fetch("eurusd_4", make_asset(), 0, 0)
    assert_error(result, f"Could not find ECB {context}", expected)


def test_ecb_fetch_multiple_points_skip_invalid(unwrap, ecb_provider):
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
    provider.session.queue(200, fake_json)
    points = unwrap(provider.fetch("eurusd_multi", make_asset(), 0, 0))

    assert len(points) == 2
    assert points[0].fields["price"] == 1.10
    assert points[1].fields["price"] == 1.12
