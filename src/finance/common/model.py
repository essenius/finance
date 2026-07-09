# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/model.py

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Generic, TypeVar

from finance.common.time_utils import check_duration_in, parse_duration

BACKEND = "timescaledb"
BACKEND_UPPER = BACKEND.upper()
BACKEND_LEN = len(BACKEND)
RESOLUTION = "resolution"


class StringEnum(StrEnum):
    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls._value2member_map_

    @classmethod
    def values(cls) -> list[str]:
        return [entry.value for entry in cls]

    @classmethod
    def validate(cls, value: str, context: str = "") -> str:
        if context != "":
            context = f" in {context}"
        try:
            return cls(value).value
        except ValueError:
            raise ValueError(f"Invalid {cls.__name__}{context}: {value!r}. Allowed: {cls.values()}") from None


"""
class Resolution(StringEnum):
    INTRADAY = "intraday"
    DAILY = "daily"


INTRADAY = Resolution.INTRADAY
DAILY = Resolution.DAILY
"""


class Candle(StringEnum):
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"

    @classmethod
    def ordered(cls) -> list[Candle]:
        return [cls.OPEN, cls.HIGH, cls.LOW, cls.CLOSE, cls.VOLUME]


PRICE = ["price"]


class Retention(StringEnum):
    # note: defined in setup.sql too
    SHORT_LIVED = "short_lived"
    LONG_LIVED = "long_lived"


class SeriesType(StringEnum):
    # note: defined in setup.sql too
    CANDLE = "candle"
    VALUE = "value"


class SupportedProviders(StringEnum):
    YAHOO = "yahoo"
    ECB = "ecb"
    FRED = "fred"


class CompletionPolicy(StringEnum):
    INTERVAL_CLOSE = "interval_close"
    NEXT_DAY = "next_day"


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

    # @staticmethod
    # def fields() -> list[str]:
    #    return [Candle.CLOSE]

    # @staticmethod
    # def map(raw_fields: dict):
    #    return {"value": raw_fields.get(Candle.CLOSE)}

    # @classmethod
    # def normalize_time(cls, dt: datetime) -> datetime:
    #    """Snap to midnight UTC. Good for daily points; must be overridden for intraday"""
    #    return datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=UTC)

    # @staticmethod
    # def factory(series: Series) -> Callable[..., SeriesPoint]:
    #    return partial(SeriesPoint, series_id=series.id)

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


'''
@dataclass(frozen=True)
class CandlePoint(SeriesPoint):
    """
    Point for daily candles. The time is the start of the day (UTC) of publication.
    so e.g. 26-Jun-2026T00:00:00Z means the daily value published June 26
    """

    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "type": "candle",
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }

    @staticmethod
    def fields() -> list[str]:
        return Candle.values()

    @staticmethod
    def map(raw_fields: dict):
        return {k: raw_fields[k] for k in raw_fields if k in Candle.values()}

    @classmethod
    def from_base(cls, base: SeriesPoint, data: dict) -> CandlePoint:
        return cls(
            series_id=base.series_id,
            time=base.time,
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
        )

    def __repr__(self):
        parent = super().__repr__()
        return f"{parent[:-1]}, open={self.open}, high={self.high}, low={self.low}, close={self.close}, volume={self.volume})"


@dataclass(frozen=True)
class DailyValuePoint(SeriesPoint):
    """
    Point for daily values. The time is the start of the day (UTC) of publication.
    so e.g. 26-Jun-2026T00:00:00Z means the daily value published June 26
    """

    value: float

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "type": "daily_value",
            "value": self.value,
        }

    @classmethod
    def from_base(cls, base: SeriesPoint, data: dict) -> DailyValuePoint:
        return cls(
            series_id=base.series_id,
            time=base.time,
            value=data["value"],
        )

    def __repr__(self):
        parent = super().__repr__()
        return f"{parent[:-1]}, value={self.value})"


@dataclass(frozen=True)
class IntradayPoint(SeriesPoint):
    """
    Point for intraday values. The time is the published time of the value.
    """

    value: float

    @classmethod
    def normalize_time(cls, dt: datetime) -> datetime:
        """round to seconds"""
        return datetime.fromtimestamp(round(dt.timestamp()), tz=dt.tzinfo)

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "type": "intraday",
            "value": self.value,
        }

    @classmethod
    def from_base(cls, base: SeriesPoint, data: dict) -> IntradayPoint:
        return cls(
            series_id=base.series_id,
            time=base.time,
            value=data["value"],
        )

    def __repr__(self):
        parent = super().__repr__()
        return f"{parent[:-1]}, value={self.value})"

'''
T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    ok: bool
    payload: T | None = None
    reason: str | None = None
    error: str | None = None
    warnings: list[str] | None = None
    meta: dict | None = None

    @staticmethod
    def parse_warnings(warnings: list[str]) -> str | None:
        if warnings is None or warnings == []:
            return None
        return warnings

    @staticmethod
    def ok_payload(payload: T, warnings: list[str] | None = None, meta: dict | None = None) -> Result[T]:
        return Result(ok=True, payload=payload, warnings=Result.parse_warnings(warnings), meta=meta)

    @staticmethod
    def fail(
        reason: str, error: str | None = None, warnings: list[str] | None = None, meta: dict | None = None
    ) -> Result[None]:
        return Result(
            ok=False,
            reason=reason,
            error=None if error is None else str(error),
            meta=meta,
            warnings=Result.parse_warnings(warnings),
        )

    def with_measurement(self, measurement: str) -> MeasurementResult[T]:
        return MeasurementResult.from_result(self, measurement)

    def with_meta(self, meta: dict) -> Result:
        return replace(self, meta=meta)


@dataclass
class MeasurementResult(Result[T]):
    # Python quirk: this cannot be non-defaulted as there are defaults in the parent
    series_name: str | None = None

    @staticmethod
    def from_result(result: Result[T], series_name: str) -> MeasurementResult[T]:
        return MeasurementResult(
            ok=result.ok,
            series_name=series_name,
            payload=result.payload,
            reason=result.reason,
            error=result.error,
            warnings=result.warnings,
            meta=result.meta,
        )

    @staticmethod
    def ok_payload(
        series_name: str, payload: T, warnings: list[str] | None = None, meta: dict | None = None
    ) -> MeasurementResult[T]:
        return Result.ok_payload(payload, warnings, meta).with_measurement(series_name)

    @staticmethod
    def fail(
        series_name: str,
        reason: str,
        error: str | None = None,
        warnings: list[str] | None = None,
        meta: dict | None = None,
    ) -> MeasurementResult[None]:
        return Result.fail(reason, error, warnings, meta).with_measurement(series_name)


FetchResult = MeasurementResult[list[SeriesPoint]]
SeriesResult = MeasurementResult[SeriesPoint | None]


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    timezone: str
    timeout: str = "10s"
    history_limits: dict[timedelta, timedelta | None] = field(default_factory=dict)
    overlap: dict[timedelta, timedelta | None] = field(default_factory=dict)

    def timeout_delta(self) -> timedelta:
        return parse_duration(self.timeout, f"timeout for {self.name}")

    @classmethod
    def create(cls, content: dict) -> ProviderConfig:
        raw_history_limits = content.get("constraints", {}).get("history_limits", {})
        history_limits: dict[timedelta, timedelta | None] = ProviderConfig.parse_duration_table(raw_history_limits)
        raw_overlap = content.get("overlap", {})
        overlap: dict[timedelta, timedelta | None] = ProviderConfig.parse_duration_table(raw_overlap)

        return cls(
            name=content["name"],
            timeout=check_duration_in(content, "timeout", "10s"),
            timezone=content.get("timezone", "UTC"),
            history_limits=history_limits,
            overlap=overlap,
        )

    @staticmethod
    def parse_duration_table(config: dict) -> dict[timedelta, timedelta | None]:
        limits = {}
        for key, limit in config.items():
            limit_key = timedelta(0) if key == "default" else parse_duration(key, "key")
            limit_value = None if limit is None else parse_duration(str(limit), f"theshold of key '{key}'")
            limits[limit_key] = limit_value
        return limits

    @staticmethod
    def get_from_duration_table(delta: timedelta, table: dict[timedelta, timedelta] | None) -> timedelta:
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

    def get_overlap(self, interval: timedelta) -> timedelta | None:
        return self.get_from_duration_table(interval, self.overlap) or timedelta(0)


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
    completion_policy: CompletionPolicy

    # assigned by backend
    id: int | None = None

    def interval_delta(self) -> timedelta:
        return parse_duration(self.interval, f"interval for {self.name}")

    def bootstrap_history_delta(self) -> timedelta:
        return parse_duration(self.bootstrap_history, f"bootstrap history for {self.name}")

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

        completion_policy = config.get("completion_policy")
        if completion_policy is None:
            completion_policy = CompletionPolicy.INTERVAL_CLOSE if is_intraday else CompletionPolicy.NEXT_DAY
        else:
            completion_policy = CompletionPolicy.validate(completion_policy)

        return cls(
            name=name,
            code=code,
            asset_id=asset.id,
            asset_name=asset.name,
            interval=config["interval"],
            series_type=SeriesType.validate(config.get("series_type", SeriesType.CANDLE), context()),
            retention=retention,
            bootstrap_history=bootstrap_history,
            completion_policy=completion_policy,
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
            and self.completion_policy == other.completion_policy
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


@dataclass
class SeriesState:
    first_time: datetime | None = None
    last_time: datetime | None = None
    last_try: datetime | None = None

    def to_dict(self):
        def serialize(s: datetime | None) -> str | None:
            return None if s is None else s.isoformat(timespec="seconds")

        return {
            "first_time": serialize(self.first_time),
            "last_time": serialize(self.last_time),
            "last_try": serialize(self.last_try),
        }

    @classmethod
    def from_dict(cls, input: dict):
        def parse(s: str) -> datetime | None:
            return datetime.fromisoformat(s) if s is not None else None

        return cls(
            first_time=parse(input.get("first_time")),
            last_time=parse(input.get("last_time")),
            last_try=parse(input.get("last_try")),
        )
