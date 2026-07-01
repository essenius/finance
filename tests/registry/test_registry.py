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
    assert registry._yaml_assets[0] is asset


def test_load_yaml_series(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX")
    series = make_series(asset, resolution=Resolution.DAILY)
    registry.load_yaml_series([series])
    assert registry._yaml_series[0] is series


def test_load_db_assets(make_asset):
    registry = Registry()
    asset = make_asset("SPX", id=1)
    registry.load_db_assets([asset])
    assert registry._db_assets[0] is asset


def test_load_db_series(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX", id=1)
    series = make_series(asset, id=10)
    registry.load_db_series([series])
    assert registry._db_series_list[0] is series


# ------------------------------------------------------------
# Asset reconciliation
# ------------------------------------------------------------


def test_reconcile_assets_create_only(make_asset):
    registry = Registry()

    asset_yaml = make_asset("SPX")
    registry.load_yaml_assets([asset_yaml])

    result = registry._reconcile_assets()

    assert result.to_persist == [asset_yaml], "to persist"
    assert result.orphans == [], "orphans"
    assert result.final == [], "final"


def test_reconcile_assets_update(make_asset):
    registry = Registry()

    asset_yaml = make_asset("SPX", instrument="x")
    asset_db = make_asset("SPX", id=1, instrument="y")

    registry.load_yaml_assets([asset_yaml])
    registry.load_db_assets([asset_db])

    result = registry._reconcile_assets()

    assert result.to_persist == [asset_yaml]
    assert result.orphans == []
    assert result.final == []


def test_reconcile_assets_orphans(make_asset):
    registry = Registry()

    asset_db = make_asset("QQQ", id=2)
    registry.load_db_assets([asset_db])

    result = registry._reconcile_assets()

    assert result.to_persist == []
    assert result.orphans == [asset_db]
    assert result.final == []

def test_reconcile_assets_match_provider(make_asset):
    registry = Registry()

    # provider and provider code identical, name different (i.e. likely renamed in yaml)
    asset_yaml = make_asset("RRR", id=None)
    asset_db = make_asset("QQQ", id=2)
    registry.load_yaml_assets([asset_yaml])
    registry.load_db_assets([asset_db])

    result = registry._reconcile_assets()

    assert result.to_persist == [asset_yaml.with_id(2)]
    assert result.orphans == []
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
    registry.load_yaml_series([series_yaml])

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

    registry.load_yaml_series([series_yaml])
    registry.load_db_series([series_db])

    result = registry._reconcile_series()

    assert result.to_persist == [series_yaml.with_id(10)]
    assert result.orphans == []
    assert result.final == []


def test_reconcile_series_orphans(make_asset, make_series):
    registry = Registry()

    asset = make_asset("SPX", id=1)
    registry._assets_by_name = {"SPX": asset}

    series_db = make_series(asset, id=10)
    registry.load_db_series([series_db])

    result = registry._reconcile_series()

    assert result.to_persist == []
    assert result.orphans == [series_db]
    assert result.final == []

def test_reconcile_series_match_asset_resolution(make_asset, make_series):
    registry = Registry()

    # yaml has no IDs
    asset = make_asset("SPX", id=None)
    registry._assets_by_name = {"SPX": asset}

    # we make a series with a different name than in the DB (i.e. renamed in yaml)
    series_yaml = make_series(asset, name="different", id=None)
    registry.load_yaml_series([series_yaml])
    # same asset and resolution, different name

    # the matching record in the database
    db_asset = asset.with_id(2)
    series_db = make_series(db_asset, id=10)
    registry.load_db_series([series_db])

    result = registry._reconcile_series()
    # the two match, so one to persist and nu orphans.
    assert result.to_persist == [series_yaml.with_id(10)]
    assert result.orphans == []
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
