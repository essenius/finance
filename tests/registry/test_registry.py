# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/registry/test_registry.py

import pytest

from finance.common.model import Resolution
from finance.registry.registry import Registry

# ------------------------------------------------------------
# Progressive loading
# ------------------------------------------------------------


def test_load_yaml_assets(make_asset):
    registry = Registry()
    asset = make_asset("SPX", id=1)
    registry.load_yaml_assets([asset])
    assert registry._yaml_assets["SPX"] is asset


def test_load_yaml_series(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX")
    series = make_series(asset, resolution=Resolution.DAILY)
    registry.load_yaml_series([series])
    assert registry._yaml_series["SPX_daily"] is series


def test_load_db_assets(make_asset):
    registry = Registry()
    asset = make_asset("SPX", id=1)
    registry.load_db_assets([asset])
    assert registry._db_assets["SPX"] is asset


def test_load_db_series(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX", id=1)
    series = make_series(asset, id=10)
    registry.load_db_series([series])
    assert registry._db_series["SPX_intraday"] is series


# ------------------------------------------------------------
# Asset reconciliation
# ------------------------------------------------------------


def test_reconcile_assets_create_only(make_asset):
    registry = Registry()

    asset_yaml = make_asset("SPX")
    registry._yaml_assets = {"SPX": asset_yaml}

    result = registry._reconcile_assets()

    assert result.to_persist == [asset_yaml]
    assert result.orphans == []
    assert result.final == []


def test_reconcile_assets_update(make_asset):
    registry = Registry()

    asset_yaml = make_asset("SPX", instrument="x")
    asset_db = make_asset("SPX", id=1, instrument="y")

    registry._yaml_assets = {"SPX": asset_yaml}
    registry._db_assets = {"SPX": asset_db}

    result = registry._reconcile_assets()

    assert result.to_persist == [asset_yaml]
    assert result.orphans == []
    assert result.final == []


def test_reconcile_assets_orphans(make_asset):
    registry = Registry()

    asset_db = make_asset("QQQ", id=2)
    registry._db_assets = {"QQQ": asset_db}

    result = registry._reconcile_assets()

    assert result.to_persist == []
    assert result.orphans == [asset_db]
    assert result.final == []


# ------------------------------------------------------------
# Series reconciliation
# ------------------------------------------------------------


def test_reconcile_series_create_only(make_asset, make_series):
    registry = Registry()

    # authoritative asset
    asset = make_asset("SPX", id=1)
    registry._assets_by_name = {"SPX": asset}

    series_yaml = make_series(asset)
    registry._yaml_series = {"SPX_intraday": series_yaml}

    result = registry._reconcile_series()

    assert result.to_persist == [series_yaml]
    assert result.orphans == []
    assert result.final == []


def test_reconcile_series_update(make_asset, make_series):
    registry = Registry()

    asset = make_asset("SPX", id=1)
    registry._assets_by_name = {"SPX": asset}

    series_yaml = make_series(asset, interval="1d")
    series_db = make_series(asset, id=10, interval="2d")

    registry._yaml_series = {"SPX_intraday": series_yaml}
    registry._db_series = {"SPX_intraday": series_db}

    result = registry._reconcile_series()

    assert result.to_persist == [series_yaml.with_id(10)]
    assert result.orphans == []
    assert result.final == []


def test_reconcile_series_orphans(make_asset, make_series):
    registry = Registry()

    asset = make_asset("SPX", id=1)
    registry._assets_by_name = {"SPX": asset}

    series_db = make_series(asset, id=10)
    registry._db_series = {"SPX_intraday": series_db}

    result = registry._reconcile_series()

    assert result.to_persist == []
    assert result.orphans == [series_db]
    assert result.final == []


# ------------------------------------------------------------
# Reconciliation entry point
# ------------------------------------------------------------


def test_reconcile_same(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX", id=None)
    registry.load_yaml_assets([asset])
    asset2 = asset.with_id(1)
    registry.load_db_assets([asset2])
    reconciled_assets = registry.reconcile_assets()
    assert reconciled_assets.orphans == [], "no orphan assets"
    assert reconciled_assets.to_persist == [], "no asset to persist"
    assert reconciled_assets.final == [asset2], "final assets filled"


    series = make_series(asset, resolution=Resolution.DAILY, id=None)
    registry.load_yaml_series([series])
    series2 = make_series(asset2, resolution=Resolution.DAILY, id=2)
    registry.load_db_series([series2])

    reconciled_series = registry.reconcile_series()

    assert reconciled_series.orphans == [], "no orphan series"
    assert reconciled_series.to_persist == [], "no series to persist"
    assert reconciled_series.final == [series2], "final series filled"


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------


def test_register_final_asset_requires_id(make_asset):
    registry = Registry()
    asset = make_asset("SPX", id=None)

    with pytest.raises(ValueError):
        registry.register_final_asset(asset)


def test_register_final_asset_success(make_asset):
    registry = Registry()
    asset = make_asset("SPX", id=1)

    registry.register_final_asset(asset)

    assert registry._assets_by_id[1] is asset
    assert registry._assets_by_name["SPX"] is asset


def test_register_final_series_requires_id(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX", id=1)
    series = make_series(asset, id=None)

    with pytest.raises(ValueError):
        registry.register_final_series(series)


def test_register_final_series_success(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX", id=1)
    series = make_series(asset, id=10)

    registry.register_final_series(series)

    assert registry._series_by_id[10] is series
    assert registry._series_by_name["SPX_intraday"] is series


# ------------------------------------------------------------
# Lookup
# ------------------------------------------------------------


def test_lookup_assets_and_series(make_asset, make_series):
    registry = Registry()

    asset = make_asset("SPX", id=1)
    series = make_series(asset, id=10)

    registry.register_final_asset(asset)
    registry.register_final_series(series)

    assert registry.get_asset_by_id(1) is asset
    assert registry.get_asset_by_name("SPX") is asset
    assert registry.get_series_by_id(10) is series
    assert registry.get_series_by_name("SPX_intraday") is series

    assert list(registry.all_assets()) == [asset]
    assert list(registry.all_series()) == [series]
