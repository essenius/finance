# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/provider.py

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import requests

from ..common.model import Asset, FetchResult, MeasurementResult, Result, Series, T


class MarketDataProvider:
    """Base interface for all market data providers."""

    def __init__(self, provider_config: dict, api_key: str | None = None, **kwargs):
        self.provider_config = provider_config
        self.api_key = api_key
        self.session = kwargs.pop("session", None) or requests.Session()
        self.now = kwargs.pop("now_provider", None) or (lambda: datetime.now(UTC))
        self.timezone = ZoneInfo(provider_config["timezone"])

    def _safe_call(
        self, measurement: str, fn: Callable[[], MeasurementResult[T]], context: str
    ) -> MeasurementResult[T]:
        try:
            return fn()
        except Exception as exc:
            return MeasurementResult.fail(measurement, f"Exception during {context}", exc)

    def _safe_get(self, obj: dict | list, path: list[str | int]) -> Result[any]:
        """
        Walk nested dict/list structures safely.
        Returns (value, None) on success.
        Returns (None, error_message) on failure.
        """
        current = obj
        for i, key in enumerate(path):
            try:
                current = current[key]
            except KeyError:
                return Result.fail(f"missing key '{key}' at {path[:i]}")
            except IndexError:
                return Result.fail(f"missing index [{key}] at {path[:i]}")
            except TypeError:
                return Result.fail(f"cannot index with [{key}] at {path[:i]}")
        return Result.ok_payload(current)

    def fetch(self, series: Series, asset: Asset, start_timestamp: int, end_timestamp: int) -> FetchResult:
        """
        Fetch data points for the given asset definition between start_timestamp and end_timestamp.
        """
        return FetchResult.fail(series.name, "fetch not implemented")
