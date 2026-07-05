# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/registry/registry.py

from collections.abc import Iterable
from dataclasses import dataclass

from ..common.model import Asset, Series


@dataclass
class ReconciledAssets:
    final: list[Asset]
    to_persist: list[Asset]
    orphans: list[Asset]


@dataclass
class ReconciledSeries:
    final: list[Series]
    to_persist: list[Series]
    orphans: list[Series]


@dataclass
class ReconciliationResult:
    assets: ReconciledAssets
    series: ReconciledSeries


class Registry:
    """
    Progressive-loading registry:
    - load YAML assets/series
    - load DB assets/series
    - reconcile()
    - register authoritative objects
    """

    def __init__(self):
        # Accumulated inputs
        self._yaml_assets: list[Asset] = {}
        self._yaml_series: list[Series] = {}

        self._db_assets: list[Asset] = {}
        self._db_series_list: list[Series] = {}

        # Final authoritative registry
        self._assets_by_id: dict[int, Asset] = {}
        self._assets_by_name: dict[str, Asset] = {}

        self._series_by_id: dict[int, Series] = {}
        self._series_by_name: dict[str, Series] = {}

    # ------------------------------------------------------------
    # Progressive loading API
    # ------------------------------------------------------------

    def load_yaml_assets(self, assets: Iterable[Asset]):
        self._yaml_assets = list(assets)

    def load_yaml_series(self, series: Iterable[Series]):
        self._yaml_series = list(series)

    def load_db_assets(self, assets: Iterable[Asset]):
        self._db_assets = list(assets)

    def load_db_series(self, series: Iterable[Series]):
        self._db_series_list = list(series)

    # ------------------------------------------------------------
    # Reconciliation entry point
    # ------------------------------------------------------------

    def reconcile_assets(self) -> ReconciledAssets:
        assets_result = self._reconcile_assets()

        # Register authoritative assets
        for a in assets_result.final:
            self.register_final_asset(a)

        return assets_result

    def reconcile_series(self) -> ReconciledSeries:
        series_result = self._reconcile_series()

        # Register authoritative series
        for s in series_result.final:
            self.register_final_series(s)

        return series_result

    # ------------------------------------------------------------
    # Asset reconciliation
    # ------------------------------------------------------------

    def _reconcile_assets(self) -> ReconciledAssets:
        db_by_name = {a.name: a for a in self._db_assets}

        to_persist = []
        final = []

        def find_existing_asset(yaml_asset):
            # First match by name (YAML identity)
            db_asset = db_by_name.get(yaml_asset.name)
            if db_asset:
                return db_asset

            # Then check if there is any record that is the same semantically.
            # This indicates a rename. Not likely to happen often, so using an
            # index cache isn't worth the overhead (other than with name).
            return next(
                (s for s in self._db_assets if s.same_semantics(yaml_asset)),
                None,
            )

        for yaml_asset in self._yaml_assets:
            db_asset = find_existing_asset(yaml_asset)
            if db_asset is None:
                to_persist.append(yaml_asset)
            elif yaml_asset.differs_from(db_asset):
                to_persist.append(yaml_asset.with_id(db_asset.id))
            else:
                final.append(db_asset)

        orphans = [
            db_asset
            for db_asset in self._db_assets
            if not any(find_existing_asset(yaml_asset) == db_asset for yaml_asset in self._yaml_assets)
        ]

        return ReconciledAssets(final, to_persist, orphans)

    # ------------------------------------------------------------
    # Series reconciliation
    # ------------------------------------------------------------

    def _reconcile_series(self) -> ReconciledSeries:
        db_by_name = {s.name: s for s in self._db_series_list}

        def find_existing_series(yaml_series):
            # First match by name
            db_series = db_by_name.get(yaml_series.name)
            if db_series:
                return db_series

            # Then look for a semantic match. If found, the series was
            # likely renamed in the YAML (code changed, definition unchanged).
            return next(
                (s for s in self._db_series_list if s.same_semantics(yaml_series)),
                None,
            )

        to_persist = []
        final = []

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
                to_persist.append(yaml_series.with_id(db_series.id))
            else:
                final.append(db_series)

        orphans = [
            db_series
            for db_series in self._db_series_list
            if not any(find_existing_series(yaml_series) == db_series for yaml_series in self._yaml_series)
        ]

        return ReconciledSeries(final, to_persist, orphans)

    # ------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------

    def register_final_asset(self, asset: Asset) -> None:
        """
        Register a final, DB-backed Asset object.
        The asset must have a valid id (assigned by the backend).
        """
        if asset.id is None:
            raise ValueError("Cannot register asset without an id")

        self._assets_by_id[asset.id] = asset
        self._assets_by_name[asset.name] = asset

    def register_final_series(self, series: Series) -> None:
        """
        Register a final, DB-backed Series object.
        The series must have a valid id (assigned by the backend).
        """
        if series.id is None:
            raise ValueError("Cannot register series without an id")

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
