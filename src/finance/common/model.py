# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/model.py

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..common.result import MeasurementResult
from ..common.string_enums import Candle, Retention, SeriesType
from ..common.time_utils import check_duration_in, parse_duration, parse_time, parse_weekday

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
            close=data.get("close"),
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


FetchResult = MeasurementResult[list[SeriesPoint]]
SeriesResult = MeasurementResult[SeriesPoint | None]


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    # timezone: str
    timeout: str = "10s"
    history_limits: dict[timedelta, timedelta | None] = field(default_factory=dict)
    sweep: dict[timedelta, SweepConfig] = field(default_factory=dict)

    def timeout_delta(self) -> timedelta:
        return parse_duration(self.timeout, f"timeout for {self.name}")

    @classmethod
    def create(cls, content: dict) -> ProviderConfig:
        raw_history_limits = content.get("constraints", {}).get("history_limits", {})
        history_limits: dict[timedelta, timedelta | None] = ProviderConfig.parse_duration_table(raw_history_limits)
        sweep: dict[timedelta, SweepConfig] = ProviderConfig.parse_sweep_table(content.get("sweep", {}))

        return cls(
            name=content["name"],
            timeout=check_duration_in(content, "timeout", "10s"),
            # timezone=content.get("timezone", "UTC"),
            history_limits=history_limits,
            sweep=sweep,
        )

    @staticmethod
    def parse_sweep_table(config: dict) -> dict[timedelta, SweepConfig | None]:
        sweeps = {}
        for key, sweep_config in config.items():
            sweep_key = timedelta(0) if key == "default" else parse_duration(key, "key")
            sweep = SweepConfig.from_config(sweep_config or {}, f"sweep of key '{key}'")
            sweeps[sweep_key] = sweep
        return sweeps

    @staticmethod
    def parse_duration_table(config: dict) -> dict[timedelta, timedelta | None]:
        limits = {}
        for key, limit in config.items():
            limit_key = timedelta(0) if key == "default" else parse_duration(key, "key")
            limit_value = None if limit is None else parse_duration(str(limit), f"theshold of key '{key}'")
            limits[limit_key] = limit_value
        return limits

    @staticmethod
    def get_from_duration_table(
        delta: timedelta, table: dict[timedelta, timedelta | SweepConfig] | None
    ) -> timedelta | SweepConfig:
        if not table:
            return None  # unlimited
        chosen = None
        for threshold, limit in table.items():
            if delta >= threshold:
                chosen = limit
            else:
                break
        return chosen

    def get_history_limit(self, interval: timedelta) -> timedelta | None:
        return self.get_from_duration_table(interval, self.history_limits)

    def get_sweep(self, interval: timedelta) -> SweepConfig:
        return self.get_from_duration_table(interval, self.sweep) or SweepConfig(
            window=timedelta(0), cadence=timedelta(0)
        )


@dataclass(frozen=True)
class Asset:
    # identity
    name: str
    symbol: str
    provider: str

    # metadata
    display_name: str
    provider_code: str
    instrument: str | None = None
    exchange: str | None = None
    region: str | None = None
    currency: str | None = None
    unit: str | None = None

    # assigned by the backend
    id: int | None = None

    @classmethod
    def create(cls, name: str, config: dict, tags: dict) -> Asset:
        provider_config = config.get("provider", {})
        return cls(
            name=name,
            symbol=config.get("symbol", name),
            provider=provider_config["name"],
            provider_code=provider_config["code"],
            display_name=config.get("display_name", name),
            instrument=tags.get("instrument"),
            region=tags.get("region"),
            exchange=tags.get("exchange"),
            currency=tags.get("currency"),
            unit=tags.get("unit"),
        )

    def with_id(self, new_id: id) -> Asset:
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
            or self.display_name != other.display_name
            or self.instrument != other.instrument
            or self.region != other.region
            or self.exchange != other.exchange
            or self.currency != other.currency
            or self.unit != other.unit
        )

    def __repr__(self):
        return f"Asset(id={self.id}, name={self.name}, symbol={self.symbol}, provider_code={self.provider_code}, region={self.region})"


@dataclass
class Series:
    # identity
    asset_id: int
    code: str

    # derivative
    asset_name: str  # taken from asset.name
    name: str  # = asset_name:code

    # meta-data
    interval: str
    retention: Retention
    series_type: SeriesType
    bootstrap_history: str
    timezone: ZoneInfo
    market_open: time
    market_close: time
    week_start: str
    week_end: str
    publication_offset: str | None

    # assigned by backend
    id: int | None = None

    def interval_delta(self) -> timedelta:
        return parse_duration(self.interval, f"interval for {self.name}")

    def bootstrap_history_delta(self) -> timedelta:
        return parse_duration(self.bootstrap_history, f"bootstrap history for {self.name}")

    def retention_delta(self) -> timedelta:
        return timedelta(days=30) if self.retention == Retention.SHORT_LIVED else None

    @classmethod
    def create(cls, asset: Asset, code: str, config: dict) -> Series:
        """Create a new Series instance. Checks values and can raise ValueError"""

        name = f"{asset.name}:{code}"

        def context():
            return f"asset:series '{name}'"

        # the caller must take care of validating this exists
        interval = parse_duration(config["interval"], context())
        retention = config.get("retention")
        # if no retention was specified, then we use long lived if the interval is a day or more
        is_intraday = Series.is_intraday_interval(interval)
        if retention is None:
            retention = Retention.SHORT_LIVED if is_intraday else Retention.LONG_LIVED
        else:
            retention = Retention.validate(retention)
        bootstrap_history = check_duration_in(config, "bootstrap_history")
        if bootstrap_history is None:
            bootstrap_history = "10y" if retention == Retention.LONG_LIVED else "30d"

        raw_timezone = config.get("timezone", "UTC")
        try:
            timezone = ZoneInfo(raw_timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Cannot understand timezone '{raw_timezone}'.") from None
        market_open = parse_time(config.get("market_open", "min"))
        market_close = parse_time(config.get("market_close", "max"))

        week_start = config.get("week_start", "mon")
        # check and raise error if wrong, but keep string representation
        parse_weekday(week_start)

        week_end = config.get("week_end", "fri")
        parse_weekday(week_end)
        publication_offset = check_duration_in(config, "publication_offset", None)

        return cls(
            name=name,
            code=code,
            asset_id=asset.id,
            asset_name=asset.name,
            interval=config["interval"],
            series_type=SeriesType.validate(config.get("series_type", SeriesType.CANDLE), context()),
            retention=retention,
            bootstrap_history=bootstrap_history,
            timezone=timezone,
            market_open=market_open,
            market_close=market_close,
            week_start=week_start,
            week_end=week_end,
            publication_offset=publication_offset,
        )

    def with_id(self, new_id: id) -> Series:
        return replace(self, id=new_id)

    def same_semantics(self, other: Series) -> bool:
        """check if two series are semantically the same (e.g. indicating a rename of the code)"""
        return (
            self.asset_id == other.asset_id
            and self.retention == other.retention
            and self.series_type == other.series_type
            and self.interval == other.interval
            and self.bootstrap_history == other.bootstrap_history
            and self.week_start == other.week_start
            and self.week_end == other.week_end
            and self.market_close == other.market_close
            and self.market_open == other.market_open
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
        return f"Series(id={self.id}, name={self.name}, asset_id={self.asset_id}, retention={self.retention}, series_type={self.series_type}, interval={self.interval}, week={self.week_start}-{self.week_end})"

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


@dataclass
class SweepConfig:
    window: timedelta
    cadence: timedelta

    @classmethod
    def from_config(cls, config: dict, context: str = "") -> SweepConfig:
        window = parse_duration(config.get("window", "0"), context)
        cadence = parse_duration(config.get("cadence", "0"), context)
        return cls(window=window, cadence=cadence)
