# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/model.py

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..common.candle_identity import CandleIdentity
from ..common.configuration import SweepConfig
from ..common.guards import require, require_duration
from ..common.string_enums import Candle, Retention, SeriesType
from ..common.time_utils import UTC, parse_duration, parse_time, parse_weekday, validate_duration
from ..common.types import ParseError
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


@dataclass(frozen=True)
class AssetMetadata:
    short_name: str | None = None
    long_name: str | None = None
    instrument: str | None = None
    exchange: str | None = None
    region: str | None = None
    currency: str | None = None
    unit: str | None = None

    timezone: ZoneInfo | None = None
    first_trade_date: date | None = None
    market_open: time | None = None
    market_close: time | None = None
    week_start: str | None = None
    week_end: str | None = None

    @classmethod
    def from_config(cls, config: dict) -> AssetMetadata:
        raw_timezone = config.get("timezone")
        timezone = None
        if raw_timezone is not None:
            try:
                timezone = ZoneInfo(raw_timezone)
            except ZoneInfoNotFoundError:
                raise ParseError(f"Cannot understand timezone '{raw_timezone}'.") from None

        week_start = config.get("week_start")
        # check and raise error if filled and wrong, but keep string representation
        parse_weekday(week_start)

        week_end = config.get("week_end")
        parse_weekday(week_end)

        return cls(
            long_name=config.get("long_name"),
            short_name=config.get("short_name"),
            instrument=config.get("instrument"),
            region=config.get("region"),
            exchange=config.get("exchange"),
            currency=config.get("currency"),
            unit=config.get("unit"),
            timezone=timezone,
            first_trade_date=config.get("first_trade_date"),
            week_start=week_start,
            week_end=week_end,
            market_open=parse_time(config.get("market_open")),
            market_close=parse_time(config.get("market_close")),
        )

    def __repr__(self):
        return f"AssetMetadata(short={self.short_name}, currency={self.currency}, timezone={None if self.timezone is None else self.timezone.key})"


SeriesPoints = list[SeriesPoint]


@dataclass(frozen=True)
class FetchData:
    series_id: int
    points: SeriesPoints
    metadata: AssetMetadata | None = None


FetchResult = Result[FetchData]
SeriesResult = Result[SeriesPoint | None]
SeriesPointsResult = Result[SeriesPoints]


@dataclass
class Asset:
    # identity
    name: str
    symbol: str
    provider: str
    provider_code: str

    # metadata
    config_metadata: AssetMetadata | None = None
    provider_metadata: AssetMetadata | None = None
    effective_metadata: AssetMetadata | None = None

    # assigned by the backend
    id: int | None = None

    @classmethod
    def from_config(cls, name: str, config: dict) -> Asset:
        provider_config = config.get("provider", {})
        config_meta = AssetMetadata.from_config(config)

        return cls(
            name=name,
            symbol=config.get("symbol", name),
            provider=provider_config["name"],
            provider_code=provider_config["code"],
            config_metadata=config_meta,
        )

    def with_id(self, new_id: int) -> Asset:
        return replace(self, id=new_id)

    def same_semantics(self, other: Asset) -> bool:
        """check if two assets are semantically the same (e.g. indicating a rename)"""
        return self.provider == other.provider and self.provider_code == other.provider_code

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

    def __repr__(self):
        return f"Asset(id={self.id}, name={self.name}, symbol={self.symbol}, provider_code={self.provider_code}, metadata={self.effective_metadata})"


@dataclass
class Series:
    # identity
    asset_id: int | None
    code: str

    # derivative
    asset_name: str  # taken from asset.name
    name: str  # = asset_name:code

    # meta-data
    interval: str
    retention: Retention
    retention_period: str | None
    series_type: SeriesType
    bootstrap_history: str
    publication_offset: str | None

    # assigned by backend
    id: int | None = None

    def interval_delta(self) -> timedelta:
        return require_duration(self.interval, f"interval for {self.name}")

    def bootstrap_history_delta(self) -> timedelta:
        return require_duration(self.bootstrap_history, f"bootstrap history for {self.name}")

    def retention_delta(self) -> timedelta | None:
        return parse_duration(self.retention_period, f"retention period for {self.name}")

    @classmethod
    def create(cls, asset: Asset, code: str, config: dict) -> Series:
        """Create a new Series instance. Checks values and can raise ParseError"""

        name = f"{asset.name}:{code}"

        # the caller must take care of validating this exists
        interval = require_duration(config["interval"], f"interval for {name}")
        is_intraday = Series.is_intraday_interval(interval)
        raw_retention = config.get("retention")
        # if no retention was specified, then we use long lived if the interval is a day or more
        if raw_retention is None:
            retention = Retention.SHORT_LIVED if is_intraday else Retention.LONG_LIVED
        else:
            retention = Retention.require(raw_retention)  # no context, caller will provide it
        retention_period = validate_duration(config.get("retention_period"), "retention period")
        bootstrap_history = validate_duration(config.get("bootstrap_history"), "bootstrap history") or (
            "10y" if retention == Retention.LONG_LIVED else "30d"
        )

        publication_offset = validate_duration(config.get("publication_offset"), "publication offset")
        return cls(
            name=name,
            code=code,
            asset_id=asset.id,
            asset_name=asset.name,
            interval=config["interval"],
            series_type=SeriesType.require(config.get("series_type", SeriesType.CANDLE)),
            retention=retention,
            retention_period=retention_period,
            bootstrap_history=bootstrap_history,
            publication_offset=publication_offset,
        )

    def with_id(self, new_id: int) -> Series:
        return replace(self, id=new_id)

    def require_id(self) -> int:
        return require(self.id, "series.id")

    def require_ids(self) -> tuple[int, int]:
        id = self.require_id()
        asset_id = require(self.asset_id, "series.asset_id")
        return id, asset_id

    def same_semantics(self, other: Series) -> bool:
        """check if two series are semantically the same (e.g. indicating a rename of the code)"""
        return (
            self.asset_id == other.asset_id
            and self.interval == other.interval
            and self.series_type == other.series_type
            and self.retention == other.retention
            and self.retention_period == other.retention_period
            and self.bootstrap_history == other.bootstrap_history
            and self.publication_offset == other.publication_offset
        )

    def differs_from(self, other: Series) -> bool:
        """
        if classified as the same entity (i.e. one of the identity checks passed),
        check if there are differences. Not checked:
        - asset_name: from the asset identity (via join).
        - name: assembled from asset_name and code
        """
        return self.code != other.code or not self.same_semantics(other)

    def __repr__(self):
        return f"Series(id={self.id}, name={self.name}, asset_id={self.asset_id}, retention={self.retention}, series_type={self.series_type}, interval={self.interval})"

    @staticmethod
    def is_intraday_interval(interval: timedelta):
        return interval < timedelta(days=1)

    def is_intraday(self):
        return self.is_intraday_interval(self.interval_delta())

    def is_daily(self):
        return not self.is_intraday()


@dataclass
class SeriesState:
    first_point: datetime | None = None
    last_point: datetime | None = None
    next_sweep: datetime | None = None
    sweep_start: datetime | None = None
    needs_save: bool = False

    @staticmethod
    def is_none_or_smaller(left, right):
        return left is None or left < right

    @staticmethod
    def is_none_or_greater(left, right):
        return left is None or left > right

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
