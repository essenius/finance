# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/model.py

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from finance.common.asset_metadata import AssetMetadata
from finance.common.json_utils import JsonObject, JsonReader
from finance.common.object_utils import apply_overrides
from finance.common.series_calendar import SeriesCalendar

from ..common.candle_identity import CandleIdentity
from ..common.configuration import SweepConfig
from ..common.guards import require, require_duration
from ..common.string_enums import Candle, Retention, SeriesType
from ..common.time_utils import UTC, parse_duration, validate_duration
from .types import Result

BACKEND = "timescaledb"


@dataclass(frozen=True)
class SeriesPoint:
    series_id: int
    time: datetime

    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None

    def to_dict(self) -> dict:
        result = {
            "series_id": self.series_id,
            "time": self.time.astimezone(UTC).isoformat(timespec="seconds"),
        }

        for field_name in Candle:
            value = getattr(self, field_name.value)
            if value is not None:
                result[field_name.value] = value

        return result

    @staticmethod
    def from_dict(data: dict) -> SeriesPoint:

        return SeriesPoint(
            series_id=data["series_id"],
            time=datetime.fromisoformat(data["time"]),
            open=data.get("open"),
            high=data.get("high"),
            low=data.get("low"),
            close=data["close"],  # cannot be None
            volume=data.get("volume"),
        )

    def __repr__(self):
        result = f"{self.__class__.__name__}(id={self.series_id}, time={self.time.astimezone(UTC).isoformat(timespec='seconds')}"
        for field_name in Candle:
            value = getattr(self, field_name.value)
            if value is not None:
                result += f", {field_name.value}={value}"
        result += ")"
        return result


type SeriesPoints = list[SeriesPoint]


@dataclass(frozen=True)
class FetchData:
    series_id: int
    series: Series
    points: SeriesPoints
    metadata: AssetMetadata | None = None


type FetchResult = Result[FetchData]
type SeriesResult = Result[SeriesPoint | None]
type SeriesPointsResult = Result[SeriesPoints]


@dataclass
class Asset:
    # identity
    name: str
    symbol: str
    provider: str
    provider_code: str

    # metadata
    config_metadata: AssetMetadata
    effective_metadata: AssetMetadata
    provider_metadata: AssetMetadata | None = None

    # assigned by the backend
    id: int | None = None

    def __repr__(self):
        return f"Asset(id={self.id}, name={self.name}, symbol={self.symbol}, provider_code={self.provider_code}, metadata={self.effective_metadata})"

    @classmethod
    def from_config(cls, name: str, config: JsonObject) -> Asset:
        reader = JsonReader(config)
        provider_reader = reader.reader_for("provider", allow_missing="no")
        config_meta = AssetMetadata.from_config(config)

        return cls(
            name=name,
            symbol=reader.get(str, "symbol", default=name.upper()),
            provider=provider_reader.require(str, "name"),
            provider_code=provider_reader.require(str, "code"),
            config_metadata=config_meta,
            effective_metadata=config_meta,
        )

    def differs_from(self, other: Asset) -> bool:
        """
        if this is classified as the same entity (one of the identity checks passed),
        check if any properties are different
        """
        return (
            self.name != other.name
            or self.symbol != other.symbol
            or not self.same_semantics(other)
            or self.effective_metadata != other.effective_metadata
        )

    def same_semantics(self, other: Asset) -> bool:
        """check if two assets are semantically the same (e.g. indicating a rename)"""
        return self.provider == other.provider and self.provider_code == other.provider_code

    def reconcile_with(self, current: Asset | None) -> bool:
        # The configured metadata overrides what is in the database (i.e. currently effective)
        # so if there is anything in the config diffferent from current, we need to save.

        if current is not None:
            self.id = current.id
            needs_save = (
                self.name != current.name
                or self.symbol != current.symbol
                or self.provider != current.provider
                or self.provider_code != current.provider_code
            )
            self.effective_metadata = apply_overrides(current.effective_metadata, self.config_metadata)
            return needs_save or self.effective_metadata != current.effective_metadata

        # We don't have a record yet, so we must save (we need an ID). Move the current config to effective as default

        self.effective_metadata = self.config_metadata
        return True

    def require_id(self) -> int:
        return require(self.id, "asset.id")

    def with_id(self, new_id: int | None) -> Asset:
        return replace(self, id=new_id)


@dataclass
class Series:
    asset: Asset
    calendar: SeriesCalendar

    # identity
    code: str

    # meta-data
    interval: str
    retention: Retention
    retention_period: str | None
    series_type: SeriesType
    bootstrap_history: str
    publication_offset: str | None

    # assigned by backend
    id: int | None = None

    @property
    def name(self) -> str:
        return f"{self.asset.name}:{self.code}"

    @classmethod
    def create(cls, asset: Asset, code: str, config: JsonObject) -> Series:
        """Create a new Series instance. Checks values and can raise ParseError"""

        reader = JsonReader(config)
        # will be empty if filled from yaml config, filled if from database.
        id = reader.get(int, "id")
        raw_interval = reader.require(str, "interval")
        interval = require_duration(raw_interval, "interval")
        is_intraday = Series.is_intraday_interval(interval)
        raw_retention = reader.get(str, "retention")
        # if no retention was specified, then we use long lived if the interval is a day or more
        if raw_retention is None:
            retention = Retention.SHORT_LIVED if is_intraday else Retention.LONG_LIVED
        else:
            retention = Retention.require(raw_retention)  # no context, caller will provide it
        retention_period = validate_duration(reader.get(str, "retention_period"), "retention period")
        bootstrap_history = validate_duration(reader.get(str, "bootstrap_history"), "bootstrap history") or (
            "10y" if retention == Retention.LONG_LIVED else "30d"
        )

        raw_publication_offset = reader.get(str, "publication_offset")
        publication_offset = parse_duration(raw_publication_offset, "publication offset")
        calendar = SeriesCalendar.create(
            interval=interval, publication_offset=publication_offset, meta=asset.effective_metadata
        )

        return cls(
            id=id,
            asset=asset,
            calendar=calendar,
            code=code,
            interval=raw_interval,
            series_type=SeriesType.require(reader.get(str, "series_type", default=str(SeriesType.CANDLE))),
            retention=retention,
            retention_period=retention_period,
            bootstrap_history=bootstrap_history,
            publication_offset=raw_publication_offset,
        )

    @staticmethod
    def is_intraday_interval(interval: timedelta):
        return interval < timedelta(days=1)

    def __repr__(self):
        return f"Series(id={self.id}, name={self.name}, asset={self.asset.name}, retention={self.retention}, series_type={self.series_type}, interval={self.interval})"

    def bootstrap_history_delta(self) -> timedelta:
        return require_duration(self.bootstrap_history, f"bootstrap history for {self.name}")

    def differs_from(self, other: Series) -> bool:
        """
        if classified as the same entity (i.e. one of the identity checks passed),
        check if there are differences. Not checked:
        - asset_name: from the asset identity (via join).
        - name: assembled from asset_name and code
        """
        return self.code != other.code or not self.same_semantics(other)

    def interval_delta(self) -> timedelta:
        return require_duration(self.interval, f"interval for {self.name}")

    def is_daily(self):
        return not self.is_intraday()

    def is_intraday(self):
        return self.is_intraday_interval(self.interval_delta())

    def publication_offset_delta(self) -> timedelta:
        return require_duration(self.publication_offset, f"publication offset for {self.name}")

    def require_id(self) -> int:
        return require(self.id, "series.id")

    def require_ids(self) -> tuple[int, int]:
        id = self.require_id()
        asset_id = self.asset.require_id()
        return id, asset_id

    def retention_delta(self) -> timedelta | None:
        return parse_duration(self.retention_period, f"retention period for {self.name}")

    def same_semantics(self, other: Series) -> bool:
        """check if two series are semantically the same (e.g. indicating a rename of the code)"""
        return (
            self.asset.same_semantics(other.asset)
            and self.interval == other.interval
            and self.series_type == other.series_type
            and self.retention == other.retention
            and self.retention_period == other.retention_period
            and self.bootstrap_history == other.bootstrap_history
            and self.publication_offset == other.publication_offset
        )

    def with_id(self, new_id: int) -> Series:
        return replace(self, id=new_id)


@dataclass
class SeriesState:
    first_point: datetime | None = None
    last_point: datetime | None = None
    next_sweep: datetime | None = None
    sweep_start: datetime | None = None
    needs_save: bool = False

    @staticmethod
    def is_none_or_greater(left: datetime | None, right: datetime):
        return left is None or left > right

    @staticmethod
    def is_none_or_smaller(left: datetime | None, right: datetime):
        return left is None or left < right

    def get_sweep_start(self, sweep: SweepConfig, last: CandleIdentity) -> datetime | None:
        if self.next_sweep is None or self.sweep_start is None:
            self.update_sweep_state(sweep, last)
        if sweep.window <= timedelta(0):
            return None
        if self.next_sweep is not None and self.next_sweep > last.store_label():
            return None
        return self.sweep_start

    def update_point_range(self, first: datetime, last: datetime):
        # update the captured point range
        if self.is_none_or_smaller(self.last_point, last):
            self.last_point = last

        if self.is_none_or_greater(self.first_point, first):
            self.first_point = first

    def update_sweep_state(self, sweep: SweepConfig, last: CandleIdentity):
        store_label = last.store_label()
        self.next_sweep = store_label + sweep.cadence
        self.sweep_start = store_label - sweep.window
        self.needs_save = True
