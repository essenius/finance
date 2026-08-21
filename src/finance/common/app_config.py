# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/app_config.py

from dataclasses import dataclass
from pathlib import Path

from ..common.configuration import LoggingConfig, ProviderConfig, TimescaleConfig
from ..common.model import Asset, Series


@dataclass
class AppConfig:
    paths: dict[str, Path]
    timescaledb: TimescaleConfig
    logging: LoggingConfig
    providers: dict[str, ProviderConfig]
    assets: list[Asset]
    series: list[Series]
