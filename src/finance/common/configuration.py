# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/configuration.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from finance.common.result import Failure, Result, Success

from ..common.guards import require_duration, validate_required_duration
from ..common.time_utils import parse_duration

type JsonValue = str | int | float | bool | None
type JsonObject = dict[str, JsonLike]
type JsonArray = list[JsonLike]
type JsonContainer = dict[str, JsonLike] | list[JsonLike]
type JsonLike = JsonValue | JsonContainer


class ConfigReader:
    def __init__(self, config: JsonObject):
        self.config = config

    def get[T: JsonLike](self, key: str, expected_type: type[T], default: T) -> T:
        value = self.config.get(key, default)
        return self._validate(key, value, expected_type)

    def get_object(self, key: str, default: JsonObject | None = None) -> JsonObject:
        value = self.config.get(key, default)

        if not isinstance(value, dict):
            raise ValueError(f"'{key}' must be an object")

        return value

    def require[T: JsonLike](self, key: str, expected_type: type[T]) -> T:
        value = self.config.get(key)
        if value is None:
            raise ValueError(f"Missing required key '{key}'")

        return self._validate(key, value, expected_type)

    def _validate[T: JsonLike](self, key: str, value: JsonLike, expected_type: type[T]) -> T:
        if type(value) is expected_type:
            return cast(T, value)

        if expected_type is float and type(value) is int:
            return cast(T, float(value))

        raise ValueError(f"'{key}' must be {expected_type.__name__}")

    def reader_for(self, key: str) -> ConfigReader:
        value = self.get_object(key)
        return ConfigReader(value)


@dataclass
class LoggingConfig:
    level: str
    use_json: bool
    date_format: str

    @classmethod
    def from_config(cls, config: JsonObject) -> LoggingConfig:
        reader = ConfigReader(config)
        return cls(
            level=reader.get("level", str, "info"),
            use_json=reader.get("use_json", bool, True),
            date_format=reader.get("date_format", str, "%Y-%m-%dT%H:%M:%S%z"),
        )


@dataclass
class TimescaleConfig:
    host: str
    dbname: str
    user: str
    password: str
    port: int
    sslmode: str
    sslrootcert: str

    max_batch_size: int
    max_batch_age: timedelta

    CONNECTION_FIELDS = ("host", "port", "dbname", "user", "password", "sslmode", "sslrootcert")
    MANDATORY_FIELDS = ("host", "db", "user", "password")

    @classmethod
    def validate(cls, config: JsonObject) -> Result[None]:
        reader = ConfigReader(config)
        missing = []
        for field in cls.MANDATORY_FIELDS:
            if not reader.get(field, str, ""):
                missing.append(field)
        if len(missing) == 0:
            return Success(None)
        return Failure(reason="TimescaleDB configuration incomplete", error=f"Missing mandatory fields: {missing}")

    @classmethod
    def from_config(cls, config: JsonObject) -> TimescaleConfig:
        reader = ConfigReader(config)
        return cls(
            host=reader.require("host", str),
            port=reader.get("port", int, 5432),
            dbname=reader.require("db", str),
            user=reader.require("user", str),
            password=reader.require("password", str),
            sslmode=reader.get("ssl_mode", str, "verify-full"),
            sslrootcert=reader.get("ssl_root_cert", str, "system"),
            max_batch_size=reader.get("max_batch_size", int, 1000),
            max_batch_age=timedelta(seconds=reader.get("max_batch_age_seconds", float, 2.0)),
        )

    def connect_config(self) -> dict:
        return {field: getattr(self, field) for field in self.CONNECTION_FIELDS}


@dataclass
class SweepConfig:
    window: timedelta
    cadence: timedelta

    @classmethod
    def from_config(cls, config: JsonObject, context: str = "") -> SweepConfig:
        reader = ConfigReader(config)
        window = require_duration(reader.get("window", str, "0"), context)
        cadence = require_duration(reader.get("cadence", str, "0"), context)
        return cls(window=window, cadence=cadence)

    @classmethod
    def zero(cls) -> SweepConfig:
        return cls(window=timedelta(0), cadence=timedelta(0))


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    timeout: str
    history_limits: dict[timedelta, timedelta | None]
    sweep: dict[timedelta, SweepConfig]
    api_key: str | None = None

    def timeout_delta(self) -> timedelta:
        return require_duration(self.timeout, f"timeout for {self.name}")

    @classmethod
    def from_config(cls, config: JsonObject, api_keys: JsonObject) -> ProviderConfig:
        reader = ConfigReader(config)
        key_reader = ConfigReader(api_keys)
        name = reader.require("name", str)
        raw_history_limits = reader.get_object("constraints", {}).get("history_limits", {})
        history_limits: dict[timedelta, timedelta | None] = ProviderConfig.parse_duration_table(raw_history_limits)
        sweep_config = reader.get_object("sweep", {})
        sweep: dict[timedelta, SweepConfig] = ProviderConfig.parse_sweep_table(sweep_config)
        api_key = key_reader.get(name, str, "")
        if api_key == "":
            api_key = None
        return cls(
            name=name,
            timeout=validate_required_duration(reader.get("timeout", str, "10s"), "timeout"),
            api_key=api_key,
            history_limits=history_limits,
            sweep=sweep,
        )

    @staticmethod
    def parse_sweep_table(config: dict) -> dict[timedelta, SweepConfig]:
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
    def get_from_duration_table[T](delta: timedelta, table: dict[timedelta, T] | None) -> T | None:
        if not table:
            return None

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
        return self.get_from_duration_table(interval, self.sweep) or SweepConfig.zero()
