# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_asset_metadata.py

from datetime import date, time

from finance.common.asset_metadata import AssetMetadata
from finance.common.json_utils import JsonObject


def test_defaults():

    # no default asset class applied even though from_config would.
    meta1 = AssetMetadata(instrument="CURRENCY")
    assert meta1.instrument == "CURRENCY"
    assert meta1.asset_class is None

    meta2 = AssetMetadata(instrument="ETF")
    assert meta2.instrument == "ETF"
    assert meta2.asset_class is None

    meta3 = AssetMetadata(instrument="FUTURE", asset_class="COMMODITY")
    assert meta3.instrument == "FUTURE"
    assert meta3.asset_class == "COMMODITY"


def test_from_config_default_asset_class():
    config: JsonObject = {
        "first_available_date": "2001-02-03",
        "week_start": "mon",
        "market_close": "15:00",
        "instrument": "CRYPTOCURRENCY",
    }
    meta = AssetMetadata.from_config(config)
    assert meta.first_available_date == date(2001, 2, 3)
    assert meta.week_start == "mon"
    assert meta.week_end is None
    assert meta.market_close == time(hour=15)
    assert meta.market_open is None
    assert meta.instrument == "CRYPTOCURRENCY"
    assert meta.asset_class == "CRYPTOCURRENCY"


def test_from_config_no_default_asset_class():
    config: JsonObject = {"instrument": "MUTUALFUND"}
    meta = AssetMetadata.from_config(config)
    assert meta.instrument == "MUTUALFUND"
    assert meta.asset_class is None


def test_from_config_asset_class():
    config: JsonObject = {"instrument": "FUTURE", "asset_class": "COMMODITY"}
    meta = AssetMetadata.from_config(config)
    assert meta.instrument == "FUTURE"
    assert meta.asset_class == "COMMODITY"
