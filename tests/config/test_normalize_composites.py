# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_composites.py

from finance.config.loader import normalize_composites


def test_normalize_composites_basic(unwrap):
    raw = {
        "REAL10Y": {
            "expression": "fred_10y_nominal_daily - fred_10y_breakeven_daily",
            "tags": {"Series": "REAL10Y"},
        }
    }

    composites = unwrap(normalize_composites(raw))

    assert "REAL10Y" in composites
    c = composites["REAL10Y"]

    assert c["expression"] == "fred_10y_nominal_daily - fred_10y_breakeven_daily"
    assert c["tags"]["series"] == "REAL10Y"
    assert "timeseries" not in c
    assert "bucket" not in c


def test_normalize_composites_with_timeseries_and_buckets(unwrap):
    raw = {
        "SPREAD": {
            "expression": "t10y_daily - t2y_daily",
            "timeseries": "daily",
            "tags": {"Series": "SPREAD"},
        }
    }

    buckets = {"intraday": "b_intraday", "daily": "b_daily"}

    composites = unwrap(normalize_composites(raw, buckets=buckets))
    c = composites["SPREAD"]

    assert c["timeseries"] == "daily"
    assert c["bucket"] == "b_daily"


def test_normalize_composites_bucket_branch(unwrap):
    raw = {
        "SPREAD": {
            "expression": "t10y_daily - t2y_daily",
            "timeseries": "daily",
            "tags": {"Series": "SPREAD"},
        }
    }

    composites = unwrap(normalize_composites(raw))
    c = composites["SPREAD"]

    assert c.get("bucket") is None
