# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_composites.py

"""
TODO re-enable
from finance.common.model import Asset
from finance.config.loader import normalize_composites


def test_normalize_composites_basic(unwrap):
    raw = {
        "REAL10Y": {
            "expression": "fred_10y_nominal_daily - fred_10y_breakeven_daily",
            "symbol": "REAL10Y",
            "tags": {"region": "USA"},
        }
    }

    composites = unwrap(normalize_composites(raw))

    assert "REAL10Y" in composites
    c = composites["REAL10Y"]
    assert c.get(RESOLUTION) is None
    assert c["expression"] == "fred_10y_nominal_daily - fred_10y_breakeven_daily"
    asset: Asset = c["asset"]
    assert asset.symbol == "REAL10Y"
    assert asset.provider == "composite"
    assert asset.region == "USA"
    assert asset.exchange is None


def test_normalize_composites_with_resolution(unwrap):
    raw = {
        "SPREAD": {
            "expression": "t10y_daily - t2y_daily",
            "symbol": "SPREAD",
            RESOLUTION: DAILY,
            "tags": {"unit": "Percent"},
        }
    }

    composites = unwrap(normalize_composites(raw))
    c = composites["SPREAD"]
    assert c[RESOLUTION] == DAILY
    asset: Asset = c["asset"]
    assert asset.symbol == "SPREAD"
    assert asset.provider == "composite"
    assert asset.region is None
    assert asset.unit == "Percent"
"""
