# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/model.py

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import partial
from typing import Generic, TypeVar

from finance.common.time_utils import parse_duration

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


class Resolution(StringEnum):
    INTRADAY = "intraday"
    DAILY = "daily"


INTRADAY = Resolution.INTRADAY
DAILY = Resolution.DAILY


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


class SeriesType(StringEnum):
    CANDLE = "candle"
    VALUE = "value"


class SupportedProviders(StringEnum):
    YAHOO = "yahoo"
    ECB = "ecb"
    FRED = "fred"


@dataclass(frozen=True)
class SeriesPoint:
    series_id: int
    timestamp: int

    @abstractmethod
    def to_dict(self) -> dict: ...

    @staticmethod
    def fields() -> list[str]:
        return [Candle.CLOSE]

    @staticmethod
    def map(raw_fields: dict):
        return {"value": raw_fields.get(Candle.CLOSE)}

    @staticmethod
    def factory(series: Series) -> Callable[..., SeriesPoint]:
        if series.resolution == Resolution.INTRADAY:
            return partial(IntradayPoint, series_id=series.id)
        if series.series_type == SeriesType.CANDLE:
            return partial(CandlePoint, series_id=series.id)
        return partial(DailyValuePoint, series_id=series.id)

    @staticmethod
    def from_dict(data: dict) -> SeriesPoint:
        point_type = data["type"]
        match point_type:
            case "candle":
                return CandlePoint.from_dict(data)
            case "daily_value":
                return DailyValuePoint.from_dict(data)
            case "intraday":
                return IntradayPoint.from_dict(data)
            case _:
                raise ValueError(f"Unknown point type: {point_type}")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.series_id}, ts={self.timestamp})"


@dataclass(frozen=True)
class CandlePoint(SeriesPoint):
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None

    def to_dict(self) -> dict:
        return {
            "type": "candle",
            "series_id": self.series_id,
            "timestamp": self.timestamp,
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

    @staticmethod
    def from_dict(d: dict) -> CandlePoint:
        return CandlePoint(
            series_id=d["series_id"],
            timestamp=d["timestamp"],
            open=d["open"],
            high=d["high"],
            low=d["low"],
            close=d["close"],
            volume=d["volume"],
        )

    def __repr__(self):
        parent = super().__repr__()
        return f"{parent[:-1]}, open={self.open}, high={self.high}, low={self.low}, close={self.close}, volume={self.volume})"


@dataclass(frozen=True)
class DailyValuePoint(SeriesPoint):
    value: float

    def to_dict(self) -> dict:
        return {
            "type": "daily_value",
            "series_id": self.series_id,
            "timestamp": self.timestamp,
            "value": self.value,
        }

    @staticmethod
    def from_dict(d: dict) -> DailyValuePoint:
        return DailyValuePoint(
            series_id=d["series_id"],
            timestamp=d["timestamp"],
            value=d["value"],
        )

    def __repr__(self):
        parent = super().__repr__()
        return f"{parent[:-1]}, value={self.value})"


@dataclass(frozen=True)
class IntradayPoint(SeriesPoint):
    value: float

    def to_dict(self) -> dict:
        return {
            "type": "intraday",
            "series_id": self.series_id,
            "timestamp": self.timestamp,
            "value": self.value,
        }

    @staticmethod
    def from_dict(d: dict) -> IntradayPoint:
        return IntradayPoint(
            series_id=d["series_id"],
            timestamp=d["timestamp"],
            value=d["value"],
        )

    def __repr__(self):
        parent = super().__repr__()
        return f"{parent[:-1]}, value={self.value})"


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
class Provider:
    name: str
    timezone: str

    daily_interval: str
    intraday_interval: str

    daily_history_limit: str
    intraday_history_limit: str

    daily_series_type: str  # "candle" or "value"


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
    def create(cls, name: str, symbol: str, config: dict, tags: dict) -> Asset:
        return cls(
            name=name,
            symbol=symbol,
            provider=config.get("provider"),
            provider_code=config.get("provider_code", symbol),
            display_name=config.get("display_name", name),
            instrument=tags.get("instrument"),
            region=tags.get("region"),
            exchange=tags.get("exchange"),
            currency=tags.get("currency"),
            unit=tags.get("unit"),
        )

    def with_id(self, new_id: id) -> Asset:
        return replace(self, id=new_id)

    def differs_from(self, other: Asset) -> bool:
        return (
            self.symbol != other.symbol
            or self.provider != other.provider
            or self.provider_code != other.provider_code
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
    resolution: Resolution

    # derivative
    name: str
    asset_name: str

    # meta-data
    series_type: SeriesType
    interval: str | None = None
    interval_seconds: int = 0
    history_limit: str | None = None
    history_limit_seconds: int = 0

    # assigned by backend
    id: int | None = None

    @classmethod
    def create(cls, asset: Asset, resolution: str, config: dict | None = None) -> Series:
        """Create a new Series instance. Checks values and can raise ValueError"""
        Resolution.validate(resolution, f"asset '{asset.name}'")

        name = f"{asset.name}_{resolution}"
        # composites don't have a resolution config section, just a key
        if config is None:
            return cls(
                name=name,
                asset_id=asset.id,
                asset_name=asset.name,
                resolution=Resolution(resolution),
                series_type=SeriesType.VALUE,
            )

        # provider_config is normalized, so values are always there (merged in)

        if resolution == Resolution.INTRADAY:
            # intraday is always VALUE, other settings ignored
            series_type = SeriesType.VALUE
        else:
            series_type = SeriesType.validate(
                config.get("series_type", config.get("daily_series_type")), f"series '{name}'"
            )

        interval = config.get("interval", config.get(f"{resolution}_interval"))
        history_limit = config.get("history_limit", config.get(f"{resolution}_history_limit"))

        return cls(
            name=name,
            asset_id=asset.id,
            asset_name=asset.name,
            resolution=Resolution(resolution),
            series_type=series_type,
            interval=interval,
            interval_seconds=parse_duration(interval, f"interval for {name}"),
            history_limit=history_limit,
            history_limit_seconds=parse_duration(history_limit, f"history limit for {name}"),
        )

    def with_id(self, new_id: id) -> Series:
        return replace(self, id=new_id)

    def differs_from(self, other: Series) -> bool:
        # only include things not in the identity (like resolution and name) or linked
        # asset_id is here as it is only assigned after storing in the database
        # asset_name is the asset identity and is therefore also not checked.
        return (
            self.asset_id != other.asset_id
            or self.series_type != other.series_type
            or self.interval != other.interval
            or self.history_limit != other.history_limit
        )

    def __repr__(self):
        return f"Series(id={self.id}, name={self.name}, asset_name={self.asset_name}, asset_id={self.asset_id}, resolution={self.resolution}, series_type={self.series_type})"


@dataclass
class SeriesState:
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    last_try: int | None = None
