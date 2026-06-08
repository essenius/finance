# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/provider.py

from collections.abc import Callable
from datetime import UTC, datetime

from ..common.model import FetchResult, MeasurementResult, Result, T


class MarketDataProvider:
    """Base interface for all market data providers."""

    def __init__(self, config: dict = None, now_provider: Callable[[], datetime] = None):

        self.config = config or {}
        self.now = now_provider or (lambda: datetime.now(UTC))

    """
    TODO: delete
    def _check_status(self, symbol, response) -> tuple[bool, str | None]:
        if response.status_code == 200:
            return True, None
        message = f"status {response.status_code}"
        if response.text:
            message += f" ({response.text})"
        return False, message

    TODO: delete
    def error(self, message, symbol=None):
        provider = self.__class__.__name__.replace("Provider", "")
        msg = f"Error fetching {symbol} from {provider}: {message}"
        super().error(msg)


    TODO: delete
    def _require_api_key(self, symbol) -> str | None:
        key = self.config.get("api_key")
        if not key:
            self.error("API key missing", symbol)
            return None
        return key
    """

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

    def fetch(self, name: str, asset: dict, last_timestamp: int) -> FetchResult:
        """
        Fetch data points for the given asset definition since the last timestamp.
        """
        return FetchResult.fail(name, "fetch not implemented")
