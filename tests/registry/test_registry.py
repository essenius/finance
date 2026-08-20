# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/registry/test_registry.py

from datetime import date

import pytest

from finance.common.model import Asset
from finance.common.string_enums import Retention
from finance.registry.registry import Registry

# ------------------------------------------------------------
# Progressive loading
# ------------------------------------------------------------


def test_load_yaml_assets(make_asset):
    asset = make_asset(name="SPX", id=1)
    registry = Registry(assets=[asset])
    assert registry._yaml_assets[0] is asset


def test_load_yaml_series(make_asset, make_series):
    asset = make_asset(name="SPX")
    series = make_series(asset=asset, retention=Retention.LONG_LIVED)
    registry = Registry(series=[series])
    assert registry._yaml_series[0] is series


# ------------------------------------------------------------
# Asset reconciliation
# ------------------------------------------------------------


def test_merge_and_find_new_assets_empty(make_asset):

    asset_yaml = make_asset(name="SPX")
    registry = Registry(assets=[asset_yaml])
    result = registry.merge_and_find_new_assets(saved_assets=[])
    assert result == [asset_yaml]


def test_merge_and_find_new_assets_update(make_asset, make_metadata):
    meta_x = make_metadata(instrument="x")
    meta_y = make_metadata(instrument="y")
    asset_yaml: Asset = make_asset(name="SPX", config_metadata=meta_x)
    asset_db: Asset = make_asset(name="SPX", id=1, effective_metadata=meta_y)

    registry = Registry(assets=[asset_yaml])
    result = registry.merge_and_find_new_assets([asset_db])
    assert result == [], "No need to save as already persisted"
    updated_asset = registry._yaml_assets[0]
    assert updated_asset.id == 1
    assert updated_asset.config_metadata == asset_yaml.config_metadata, "config metadata not changed"
    assert updated_asset.effective_metadata == asset_yaml.config_metadata, "effective metadata overridden by config"


def test_reconcile_assets_match_provider(make_asset, make_metadata):

    # provider and provider code identical, name different (i.e. likely renamed in yaml)
    asset_yaml = make_asset(name="RRR", id=None)
    meta = make_metadata(currency="GBP")
    asset_db = make_asset(name="QQQ", id=2, symbol="x", effective_metadata=meta)
    registry = Registry(assets=[asset_yaml])

    result = registry.merge_and_find_new_assets([asset_db])

    assert result == []
    updated_asset = registry._yaml_assets[0]
    assert updated_asset.id == 2
    assert updated_asset.name == "RRR"
    assert updated_asset.symbol == "RRR"
    assert updated_asset.config_metadata.currency == "USD"
    assert updated_asset.effective_metadata.currency == "USD"


# ------------------------------------------------------------
# Series reconciliation
# ------------------------------------------------------------


def test_reconcile_series_create_only(make_asset, make_series):

    # authoritative asset
    asset = make_asset(name="SPX", id=1)
    series_yaml = make_series(asset=asset)
    registry = Registry(series=[series_yaml])
    registry._assets_by_name = {"SPX": asset}

    result = registry._reconcile_series([])

    assert result.to_persist == [series_yaml]
    assert result.final == []


def test_reconcile_series_update(make_asset, make_series):

    asset = make_asset(name="SPX", id=1)

    series_yaml = make_series(asset=asset, interval="1d")

    registry = Registry(series=[series_yaml])
    registry._assets_by_name = {"SPX": asset}

    series_db = make_series(asset=asset, id=10, interval="2d")
    result = registry._reconcile_series([series_db])

    assert result.to_persist == [series_yaml.with_id(10)]
    assert result.final == []


def test_reconcile_series_orphans_ignored(make_asset, make_series):
    registry = Registry(series=[])

    asset = make_asset(name="SPX", id=1)
    registry._assets_by_name = {"SPX": asset}

    series_db = make_series(asset=asset, id=10)

    result = registry._reconcile_series([series_db])

    assert result.to_persist == []
    assert result.final == []


def test_reconcile_series_match_asset_resolution(make_asset, make_series):
    asset = make_asset(name="SPX", id=None)

    # we make a series with a different name than in the DB (i.e. renamed in yaml)
    # yaml has no IDs
    series_yaml = make_series(asset=asset, name="different", id=None)

    registry = Registry(series=[series_yaml])
    registry._assets_by_name = {"SPX": asset}

    # the matching record in the database
    db_asset = asset.with_id(2)
    series_db = make_series(asset=db_asset, id=10)

    result = registry._reconcile_series([series_db])
    # the two match, so one to persist and nu orphans.
    assert result.to_persist == [series_yaml.with_id(10)]
    assert result.final == []


# ------------------------------------------------------------
# Reconciliation entry point
# ------------------------------------------------------------


def test_reconcile_same(make_asset, make_series):
    asset = make_asset(name="SPX", id=None)
    series = make_series(asset, retention=Retention.LONG_LIVED, id=None)
    registry = Registry(assets=[asset], series=[series])
    registry._assets_by_name = {"SPX": asset}

    asset2 = asset.with_id(1)
    to_persist = registry.merge_and_find_new_assets([asset2])
    assert to_persist == [], "no asset to persist"

    series2 = make_series(asset=asset2, retention=Retention.LONG_LIVED, id=2)
    reconciled_series = registry.reconcile_series([series2])

    assert reconciled_series.to_persist == [], "no series to persist"
    assert reconciled_series.final == [series2], "final series filled"


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------


def test_register_provider_metadata(make_asset, make_metadata):
    asset_id = 1
    asset: Asset = make_asset()
    registry = Registry(assets=[asset])
    registry.register_stored_asset(asset.with_id(asset_id))

    meta = make_metadata(first_trade_date=date(2020, 1, 1))
    to_persist = registry.register_provider_metadata(asset_id, meta)
    assert to_persist is not None
    assert to_persist.effective_metadata.first_trade_date == date(2020, 1, 1)

    should_be_none = registry.register_provider_metadata(asset_id, meta)
    assert should_be_none is None, "Second registration should not trigger a save"


def test_register_provider_metadata_requires_asset(make_asset, make_metadata):
    registry = Registry()
    with pytest.raises(ValueError) as exc:
        registry.register_provider_metadata(1, make_metadata())
    assert str(exc.value) == "Cannot register provider metadata for unknown asset id 1"


def test_register_stored_asset_requires_id(make_asset):
    registry = Registry()
    asset = make_asset(name="SPX", id=None)

    with pytest.raises(ValueError) as exc:
        registry.register_stored_asset(asset)
    assert str(exc.value) == "Cannot register asset without an id"


def test_register_stored_asset_success(make_asset, make_metadata):
    registry = Registry()
    asset: Asset = make_asset(name="SPX", id=1)

    registry.register_stored_asset(asset)
    current = registry._assets_by_id[1]
    assert current.effective_metadata.first_trade_date is None

    assert registry._assets_by_id[1] is asset
    assert registry._assets_by_name["SPX"] is asset

    new_meta = make_metadata(first_trade_date=date(2020, 1, 1))
    asset.effective_metadata = new_meta
    registry.register_stored_asset(asset)
    # current = registry._assets_by_id[1]
    assert current.effective_metadata.first_trade_date == date(2020, 1, 1)


def test_register_stored_series_requires_id(make_asset, make_series):
    registry = Registry()
    asset = make_asset(name="SPX", id=1)
    series = make_series(asset=asset, id=None)

    with pytest.raises(ValueError) as exc:
        registry.register_stored_series(series)
    assert str(exc.value) == "Cannot register series without an id"


def test_register_stored_series_success(make_asset, make_series):
    registry = Registry()
    asset = make_asset(name="SPX", id=1)
    series = make_series(asset, id=10)

    registry.register_stored_series(series)

    assert registry._series_by_id[10] is series
    assert registry._series_by_name["SPX:dummy"] is series


# ------------------------------------------------------------
# Lookup
# ------------------------------------------------------------


def test_lookup_assets_and_series(make_asset, make_series):
    registry = Registry()

    asset = make_asset(name="SPX", id=1)
    series = make_series(asset=asset, id=10)

    registry.register_stored_asset(asset)
    registry.register_stored_series(series)

    assert registry.get_asset_by_id(1) is asset
    assert registry.get_asset_by_name("SPX") is asset
    assert registry.get_series_by_id(10) is series
    assert registry.get_series_by_name("SPX:dummy") is series

    assert list(registry.all_assets()) == [asset]
    assert list(registry.all_series()) == [series]
