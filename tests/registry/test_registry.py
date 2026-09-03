# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/registry/test_registry.py

from datetime import date
from unittest.mock import Mock

import pytest

from finance.common.asset_metadata import AssetMetadata
from finance.common.model import Asset, Series
from finance.common.string_enums import Retention
from finance.common.types import AppError
from finance.registry.registry import Registry
from tests.support.types import Creator

# ------------------------------------------------------------
# Progressive loading
# ------------------------------------------------------------


def test_load_yaml_assets(make_asset: Creator[Asset]):
    asset = make_asset(name="SPX", id=1)
    registry = Registry(assets=[asset])
    assert registry._yaml_assets[0] is asset


def test_load_yaml_series(make_asset: Creator[Asset], make_series: Creator[Series]):
    asset = make_asset(name="SPX")
    series = make_series(asset=asset, retention=Retention.LONG_LIVED.value)
    registry = Registry(series=[series])
    assert registry._yaml_series[0] is series


# ------------------------------------------------------------
# Asset reconciliation
# ------------------------------------------------------------


def test_merge_and_find_new_assets_empty(make_asset: Creator[Asset]):

    asset_yaml = make_asset(name="SPX")
    registry = Registry(assets=[asset_yaml])
    result = registry.merge_and_find_new_assets(saved_assets=[])
    assert result == [asset_yaml]


def test_merge_and_find_new_assets_update(make_asset: Creator[Asset], make_metadata: Creator[AssetMetadata]):
    meta_x = make_metadata(instrument="x")
    meta_y = make_metadata(instrument="y")
    asset_yaml: Asset = make_asset(name="SPX", config_metadata=meta_x)
    asset_db: Asset = make_asset(name="SPX", id=1, effective_metadata=meta_y)

    registry = Registry(assets=[asset_yaml])
    result = registry.merge_and_find_new_assets([asset_db])
    assert len(result) == 1, "Different metadata, so must save"
    updated_asset = registry._yaml_assets[0]
    assert updated_asset.id == 1
    assert updated_asset.config_metadata == asset_yaml.config_metadata, "config metadata not changed"
    assert updated_asset.effective_metadata == asset_yaml.config_metadata, "effective metadata overridden by config"


def test_reconcile_assets_match_provider(
    make_asset: Creator[Asset], make_metadata: Creator[AssetMetadata], make_provider: Creator[Mock]
):

    # provider and provider code identical, name different (i.e. likely renamed in yaml)
    provider = make_provider()
    asset_yaml = make_asset(name="RRR", provider=provider, id=None)
    meta = make_metadata(currency="GBP")
    asset_db = make_asset(name="QQQ", provider=provider, id=2, symbol="x", effective_metadata=meta)
    registry = Registry(assets=[asset_yaml])

    result = registry.merge_and_find_new_assets([asset_db])

    assert len(result) == 1
    updated_asset = result[0]
    assert updated_asset.id == 2
    assert updated_asset.name == "RRR"
    assert updated_asset.symbol == "RRR"
    assert updated_asset.config_metadata is not None
    assert updated_asset.config_metadata.currency == "USD"
    assert updated_asset.effective_metadata is not None
    assert updated_asset.effective_metadata.currency == "USD"


# ------------------------------------------------------------
# Series reconciliation
# ------------------------------------------------------------


def test_reconcile_series_create_only(make_asset: Creator[Asset], make_series: Creator[Series]):

    # authoritative asset
    asset = make_asset(name="SPX", id=1)
    series_yaml = make_series(asset=asset)
    registry = Registry(series=[series_yaml])

    result = registry._reconcile_series([])

    assert result.to_persist == [series_yaml]
    assert result.final == []


def test_reconcile_series_update(make_asset: Creator[Asset], make_series: Creator[Series]):

    asset = make_asset(name="SPX", id=1)

    series_yaml = make_series(asset=asset, interval="1d")

    registry = Registry(series=[series_yaml])

    series_db = make_series(asset=asset, id=10, interval="2d")
    result = registry._reconcile_series([series_db])

    assert result.to_persist == [series_yaml.with_id(10)]
    assert result.final == []


def test_reconcile_series_orphans_ignored(make_asset: Creator[Asset], make_series: Creator[Series]):
    registry = Registry(series=[])

    asset = make_asset(name="SPX", id=1)

    series_db = make_series(asset=asset, id=10)

    result = registry._reconcile_series([series_db])

    assert result.to_persist == []
    assert result.final == []


# ------------------------------------------------------------
# Reconciliation entry point
# ------------------------------------------------------------


def test_reconcile_same(make_asset: Creator[Asset], make_series: Creator[Series]):
    asset = make_asset(name="SPX", id=None)
    series = make_series(asset, retention=Retention.LONG_LIVED.value, id=None)
    registry = Registry(assets=[asset], series=[series])

    asset2 = asset.with_id(1)
    to_persist = registry.merge_and_find_new_assets([asset2])
    assert to_persist == [], "no asset to persist"

    series2 = make_series(asset=asset2, retention=Retention.LONG_LIVED.value, id=2)
    reconciled_series = registry.reconcile_series([series2])

    assert reconciled_series.to_persist == [], "no series to persist"
    assert reconciled_series.final == [series2], "final series filled"


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------


def test_register_provider_metadata(make_asset: Creator[Asset], make_metadata: Creator[AssetMetadata]):
    asset: Asset = make_asset()
    yaml_asset = asset.with_id(None)
    registry = Registry(assets=[yaml_asset])
    registry.register_stored_asset(asset)

    meta = make_metadata(first_available_date=date(2020, 1, 1))
    to_persist = registry.register_provider_metadata(asset, meta)
    assert to_persist is not None
    assert to_persist.effective_metadata is not None
    assert to_persist.effective_metadata.first_available_date == date(2020, 1, 1)

    should_be_none = registry.register_provider_metadata(asset, meta)
    assert should_be_none is None, "Second registration should not trigger a save"


def test_register_stored_asset_requires_id(make_asset: Creator[Asset]):
    registry = Registry()
    asset = make_asset(name="SPX", id=None)

    with pytest.raises(AppError) as exc:
        registry.register_stored_asset(asset)
    assert str(exc.value) == "Cannot register asset without an id"


def test_register_stored_asset_success(make_asset: Creator[Asset], make_metadata: Creator[AssetMetadata]):
    registry = Registry()
    asset: Asset = make_asset(name="SPX", id=1)

    registry.register_stored_asset(asset)
    current = registry._assets_by_id[1]
    assert current.effective_metadata is not None
    assert current.effective_metadata.first_available_date is None

    assert registry._assets_by_id[1] is asset

    new_meta = make_metadata(first_available_date=date(2020, 1, 1))
    asset.effective_metadata = new_meta
    registry.register_stored_asset(asset)
    assert current.effective_metadata.first_available_date == date(2020, 1, 1)


def test_register_stored_series_requires_id(make_asset: Creator[Asset], make_series: Creator[Series]):
    registry = Registry()
    asset = make_asset(name="SPX", id=1)
    series = make_series(asset=asset, id=None)

    with pytest.raises(AppError) as exc:
        registry.register_stored_series(series)
    assert str(exc.value) == "Cannot register series without an id"


def test_register_stored_series_success(make_asset: Creator[Asset], make_series: Creator[Series]):
    registry = Registry()
    asset = make_asset(name="SPX", id=1)
    series = make_series(asset, id=10)

    registry.register_stored_series(series)

    assert registry._series_by_id[10] is series


# ------------------------------------------------------------
# Lookup
# ------------------------------------------------------------


def test_lookup_assets_and_series(make_asset: Creator[Asset], make_series: Creator[Series]):
    registry = Registry()

    asset = make_asset(name="SPX", id=1)
    series = make_series(asset=asset, id=10)

    registry.register_stored_asset(asset)
    registry.register_stored_series(series)

    assert registry.get_asset(1) is asset
    assert registry.get_series(10) is series

    assert list(registry.all_assets()) == [asset]
    assert list(registry.all_series()) == [series]
