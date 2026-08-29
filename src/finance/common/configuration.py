# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/configuration.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from ..common.guards import require_duration, validate_required_duration
from ..common.json_utils import JsonObject, JsonReader
from ..common.time_utils import parse_duration
from .types import Failure, Result, Success


@dataclass
class LogConfig:
    level: str
    date_format: str

    @classmethod
    def from_config(cls, config: JsonObject) -> LogConfig:
        reader = JsonReader(config)
        return cls(
            level=reader.get(str, "level", default="info").lower(),
            date_format=reader.get(str, "date_format", default="%Y-%m-%dT%H:%M:%S%z"),
        )


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
    def from_config(cls, config: JsonObject) -> ProviderConfig:
        reader = JsonReader(config)
        name = reader.require(str, "name")
        raw_history_limits = reader.get_object(["constraints", "history_limits"], allow_missing="yes")
        history_limits: dict[timedelta, timedelta | None] = ProviderConfig._parse_duration_table(raw_history_limits)
        sweep_config = reader.get_object("sweep")
        sweep: dict[timedelta, SweepConfig] = ProviderConfig._parse_sweep_table(sweep_config)
        api_key = reader.get(str, "api_key")
        return cls(
            name=name,
            timeout=validate_required_duration(reader.get(str, "timeout", default="10s"), "timeout"),
            api_key=api_key,
            history_limits=history_limits,
            sweep=sweep,
        )

    def get_sweep(self, interval: timedelta) -> SweepConfig:
        return self._get_from_duration_table(interval, self.sweep) or SweepConfig.zero()

    # ----------------
    # Private methods
    # ----------------

    @staticmethod
    def _get_from_duration_table[T](delta: timedelta, table: dict[timedelta, T] | None) -> T | None:
        if not table:
            return None

        chosen = None
        for threshold, limit in table.items():
            if delta >= threshold:
                chosen = limit
            else:
                break

        return chosen

    def _get_history_limit(self, interval: timedelta) -> timedelta | None:
        return self._get_from_duration_table(interval, self.history_limits)

    @staticmethod
    def _parse_duration_table(config: JsonObject) -> dict[timedelta, timedelta | None]:
        limits = {}
        for key, limit in config.items():
            limit_key = timedelta(0) if key == "default" else parse_duration(key, "key")
            limit_value = None if limit is None else parse_duration(str(limit), f"theshold of key '{key}'")
            limits[limit_key] = limit_value
        return limits

    @staticmethod
    def _parse_sweep_table(config: dict) -> dict[timedelta, SweepConfig]:
        sweeps = {}
        for key, sweep_config in config.items():
            sweep_key = timedelta(0) if key == "default" else parse_duration(key, "key")
            sweep = SweepConfig.from_config(sweep_config or {}, f"sweep of key '{key}'")
            sweeps[sweep_key] = sweep
        return sweeps


@dataclass
class SweepConfig:
    window: timedelta
    cadence: timedelta

    @classmethod
    def from_config(cls, config: JsonObject, context: str = "") -> SweepConfig:
        reader = JsonReader(config)
        window = require_duration(reader.get(str, "window", default="0"), context)
        cadence = require_duration(reader.get(str, "cadence", default="0"), context)
        return cls(window=window, cadence=cadence)

    @classmethod
    def zero(cls) -> SweepConfig:
        return cls(window=timedelta(0), cadence=timedelta(0))


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

    def connect_config(self) -> dict:
        return {field: getattr(self, field) for field in self.CONNECTION_FIELDS}

    @classmethod
    def from_config(cls, config: JsonObject) -> TimescaleConfig:
        reader = JsonReader(config)
        return cls(
            host=reader.require(str, "host"),
            port=reader.get(int, "port", default=5432),
            dbname=reader.require(str, "db"),
            user=reader.require(str, "user"),
            password=reader.require(str, "password"),
            sslmode=reader.get(str, "ssl_mode", default="verify-full"),
            sslrootcert=reader.get(str, "ssl_root_cert", default="system"),
            max_batch_size=reader.get(int, "max_batch_size", default=1000),
            max_batch_age=timedelta(seconds=reader.get(float, "max_batch_age_seconds", default=2.0)),
        )

    @classmethod
    def validate(cls, config: JsonObject) -> Result[None]:
        reader = JsonReader(config)
        missing = []
        for field in cls.MANDATORY_FIELDS:
            if not reader.get(str, field):
                missing.append(field)
        if len(missing) == 0:
            return Success(None)
        return Failure(reason="TimescaleDB configuration incomplete", error=f"Missing mandatory fields: {missing}")
