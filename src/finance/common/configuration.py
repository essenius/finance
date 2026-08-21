# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/configuration.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ..common.guards import require_duration
from ..common.time_utils import parse_duration, validate_duration


@dataclass
class LoggingConfig:
    level: str = "info"
    use_json: bool = True


@dataclass
class TimescaleConfig:
    host: str
    dbname: str
    user: str | None = None
    password: str | None = None
    port: int = 5432
    sslmode: str = "verify-full"
    sslrootcert: str = "system"

    max_batch_size: int = 1000
    max_batch_age: str = "2s"

    CONNECTION_FIELDS = ("host", "port", "dbname", "user", "password", "sslmode", "sslrootcert")

    def connect_config(self) -> dict:
        return {field: getattr(self, field) for field in self.CONNECTION_FIELDS}


@dataclass
class SweepConfig:
    window: timedelta
    cadence: timedelta

    @classmethod
    def from_config(cls, config: dict, context: str = "") -> SweepConfig:
        window = require_duration(config.get("window", "0"), context)
        cadence = require_duration(config.get("cadence", "0"), context)
        return cls(window=window, cadence=cadence)

    @classmethod
    def zero(cls) -> SweepConfig:
        return cls(window=timedelta(0), cadence=timedelta(0))


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    timeout: str = "10s"
    api_key: str | None = None
    history_limits: dict[timedelta, timedelta | None] = field(default_factory=dict)
    sweep: dict[timedelta, SweepConfig] = field(default_factory=dict)

    def timeout_delta(self) -> timedelta:
        return require_duration(self.timeout, f"timeout for {self.name}")

    @classmethod
    def create(cls, content: dict) -> ProviderConfig:
        raw_history_limits = content.get("constraints", {}).get("history_limits", {})
        history_limits: dict[timedelta, timedelta | None] = ProviderConfig.parse_duration_table(raw_history_limits)
        sweep: dict[timedelta, SweepConfig] = ProviderConfig.parse_sweep_table(content.get("sweep", {}))

        return cls(
            name=content["name"],
            timeout=validate_duration(content.get("timeout"), "timeout") or "10s",
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
