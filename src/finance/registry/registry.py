# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/registry/registry.py

from collections.abc import Iterable
from dataclasses import dataclass

from finance.common.object_utils import apply_overrides

from ..common.model import Asset, AssetMetadata, Series
from ..common.types import AppError


@dataclass
class ReconciledSeries:
    final: list[Series]
    to_persist: list[Series]


class Registry:
    """
    Progressive-loading registry:
    - load YAML assets/series
    - load DB assets/series
    - reconcile()
    - register authoritative objects
    """

    def __init__(self, assets: Iterable[Asset] | None = None, series: Iterable[Series] | None = None):
        # Accumulated inputs
        self._yaml_assets: list[Asset] = [] if assets is None else list(assets)
        self._yaml_series: list[Series] = [] if series is None else list(series)

        # Final authoritative registry
        self._assets_by_id: dict[int, Asset] = {}
        self._assets_by_name: dict[str, Asset] = {}

        self._series_by_id: dict[int, Series] = {}
        self._series_by_name: dict[str, Series] = {}

    # ------------------------------------------------------------
    # Reconciliation entry point
    # ------------------------------------------------------------

    def reconcile_series(self, saved_series: list[Series]) -> ReconciledSeries:
        series_result = self._reconcile_series(saved_series=saved_series)

        # Register authoritative series
        for s in series_result.final:
            self.register_stored_series(s)

        return series_result

    # ------------------------------------------------------------
    # Asset reconciliation
    # ------------------------------------------------------------

    def merge_and_find_new_assets(self, saved_assets: list[Asset]) -> list[Asset]:
        db_by_name = {a.name: a for a in saved_assets}

        to_persist: list[Asset] = []

        def find_existing_asset(yaml_asset):
            # First match by name (YAML identity)
            db_asset = db_by_name.get(yaml_asset.name)
            if db_asset:
                return db_asset

            # Then check if there is any record that is the same semantically. # This indicates a rename.
            # Not likely to happen often, so using an index cache isn't worth the overhead (other than with name).
            return next((s for s in saved_assets if s.same_semantics(yaml_asset)), None)

        for yaml_asset in self._yaml_assets:
            db_asset = find_existing_asset(yaml_asset)
            if yaml_asset.reconcile_with(db_asset):
                to_persist.append(yaml_asset)
            if db_asset is not None:
                self.register_stored_asset(yaml_asset)

        # CO: orphans = [
        # CO:     db_asset
        # CO:     for db_asset in self._db_assets
        # CO:     if not any(find_existing_asset(yaml_asset) == db_asset for yaml_asset in self._yaml_assets)
        # CO: ]

        return to_persist

    # ------------------------------------------------------------
    # Series reconciliation
    # ------------------------------------------------------------

    def _reconcile_series(self, saved_series: list[Series]) -> ReconciledSeries:
        db_by_name = {s.name: s for s in saved_series}

        def find_existing_series(yaml_series):
            # First match by name
            db_series = db_by_name.get(yaml_series.name)
            if db_series:
                return db_series

            # Then look for a semantic match. If found, the series was
            # likely renamed in the YAML (code changed, definition unchanged).
            return next(
                (s for s in saved_series if s.same_semantics(yaml_series)),
                None,
            )

        to_persist: list[Series] = []
        final: list[Series] = []

        for yaml_series in self._yaml_series:
            # get the asset id. Yaml doesn't know about ids
            # note this requires assets to have been reconciled already.
            if yaml_series.asset_id is None:
                asset = self.get_asset_by_name(yaml_series.asset_name)
                yaml_series.asset_id = asset.id
            db_series = find_existing_series(yaml_series)
            if db_series is None:
                to_persist.append(yaml_series)
            elif yaml_series.differs_from(db_series):
                to_persist.append(yaml_series.with_id(db_series.require_id()))
            else:
                final.append(db_series)

        # CO: orphans = [
        # CO:     db_series
        # CO:     for db_series in self._db_series_list
        # CO:     if not any(find_existing_series(yaml_series) == db_series for yaml_series in self._yaml_series)
        # CO: ]

        return ReconciledSeries(final=final, to_persist=to_persist)

    # ------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------

    def register_provider_metadata(self, asset_id: int, metadata: AssetMetadata) -> Asset | None:
        """
        Register metadata that the provider returned. Returns the asset if it needs to be stored.
        """
        yaml_asset = self._assets_by_id.get(asset_id)

        if yaml_asset is None:
            raise AppError(f"Cannot register provider metadata for unknown asset id {asset_id}")

        yaml_asset.provider_metadata = metadata

        merged_metadata = apply_overrides(metadata, yaml_asset.config_metadata)
        if merged_metadata != yaml_asset.effective_metadata:
            yaml_asset.effective_metadata = merged_metadata
            return yaml_asset
        return None

    def register_stored_asset(self, asset: Asset) -> None:
        """
        Register a final, DB-backed Asset object.
        The asset must have a valid id (assigned by the backend).
        """

        def store[T](asset_dict: dict[T, Asset], key: T, asset: Asset):
            if asset_dict.get(key) is None:
                asset_dict[key] = asset
            else:
                asset_dict[key].effective_metadata = asset.effective_metadata

        if asset.id is None:
            raise AppError("Cannot register asset without an id")

        store(self._assets_by_id, asset.id, asset)
        store(self._assets_by_name, asset.name, asset)

    def register_stored_series(self, series: Series) -> None:
        """
        Register a final, DB-backed Series object.
        The series must have a valid id (assigned by the backend).
        """
        if series.id is None:
            raise AppError("Cannot register series without an id")

        self._series_by_id[series.id] = series
        self._series_by_name[series.name] = series

    # ------------------------------------------------------------
    # Lookup API
    # ------------------------------------------------------------

    def get_asset_by_id(self, asset_id: int) -> Asset:
        return self._assets_by_id[asset_id]

    def get_asset_by_name(self, name: str) -> Asset:
        return self._assets_by_name[name]

    def get_series_by_id(self, series_id: int) -> Series:
        return self._series_by_id[series_id]

    def get_series_by_name(self, name: str) -> Series:
        return self._series_by_name[name]

    def all_assets(self) -> Iterable[Asset]:
        return list(self._assets_by_id.values())

    def all_series(self) -> Iterable[Series]:
        return list(self._series_by_id.values())
