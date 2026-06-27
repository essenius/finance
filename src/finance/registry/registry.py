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
        self._yaml_assets: dict[str, Asset] = {}
        self._yaml_series: dict[str, Series] = {}

        self._db_assets: dict[str, Asset] = {}
        self._db_series: dict[str, Series] = {}

        # Final authoritative registry
        self._assets_by_id: dict[int, Asset] = {}
        self._assets_by_name: dict[str, Asset] = {}

        self._series_by_id: dict[int, Series] = {}
        self._series_by_name: dict[str, Series] = {}

    # ------------------------------------------------------------
    # Progressive loading API
    # ------------------------------------------------------------

    def load_yaml_assets(self, assets: Iterable[Asset]):
        for a in assets:
            self._yaml_assets[a.name] = a

    def load_yaml_series(self, series: Iterable[Series]):
        for s in series:
            self._yaml_series[s.name] = s

    def load_db_assets(self, assets: Iterable[Asset]):
        for a in assets:
            self._db_assets[a.name] = a

    def load_db_series(self, series: Iterable[Series]):
        for s in series:
            self._db_series[s.name] = s

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
        yaml = self._yaml_assets
        db = self._db_assets

        to_persist = []
        final = []

        for key, yaml_asset in yaml.items():
            db_asset = db.get(key)
            if db_asset is None:
                to_persist.append(yaml_asset)
            elif yaml_asset.differs_from(db_asset):
                to_persist.append(yaml_asset.with_id(db_asset.id))
            else:
                final.append(db_asset)

        orphans = [a for key, a in db.items() if key not in yaml]

        return ReconciledAssets(final, to_persist, orphans)

    # ------------------------------------------------------------
    # Series reconciliation
    # ------------------------------------------------------------

    def _reconcile_series(self) -> ReconciledSeries:
        yaml = self._yaml_series
        db = self._db_series

        to_persist = []
        final = []

        for key, yaml_series in yaml.items():
            # get the asset id. Yaml doesn't know about ids
            if yaml_series.asset_id is None:
                asset = self.get_asset_by_name(yaml_series.asset_name)
                yaml_series.asset_id = asset.id
            db_series = db.get(key)
            if db_series is None:
                to_persist.append(yaml_series)
            elif yaml_series.differs_from(db_series):
                to_persist.append(yaml_series.with_id(db_series.id))
            else:
                final.append(db_series)

        orphans = [s for key, s in db.items() if key not in yaml]

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
