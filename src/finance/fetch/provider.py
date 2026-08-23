# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/provider.py

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

import requests

from ..common.candle_identity import CandleIdentity
from ..common.configuration import ProviderConfig
from ..common.model import Asset, FetchResult, Series
from ..common.result import Failure, Result, Success
from ..common.time_utils import now_second_precision


class ResponseProtocol(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...
    def raise_for_status(self) -> None: ...


class SessionProtocol(Protocol):
    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> ResponseProtocol: ...


class MarketDataProvider:
    """Base interface for all market data providers."""

    def __init__(
        self,
        provider_config: ProviderConfig,
        api_key: str | None = None,
        *,
        session: SessionProtocol | None = None,
        now_provider: Callable[[], datetime] = now_second_precision,
    ):
        self.provider_config = provider_config
        self.api_key = api_key
        # not taking requests.session as the default, to avoid unnecessary construction
        self.session = session or requests.Session()
        self.now = now_provider

    def _safe_call[T](self, fn: Callable[[], Result[T]], context: str) -> Result[T]:
        try:
            return fn()
        except Exception as exc:
            return Failure(reason=f"Exception during {context}", error=exc)

    def _safe_get(self, obj: dict | list, path: list[str | int]) -> Result[Any]:

        current = obj
        for i, key in enumerate(path):
            try:
                current = current[key]
            except KeyError:
                return Failure(reason=f"missing key '{key}' at {path[:i]}")
            except IndexError:
                return Failure(reason=f"missing index [{key}] at {path[:i]}")
            except TypeError:
                return Failure(reason=f"cannot index with [{key}] at {path[:i]}")
        return Success(current)

    def fetch(
        self, series: Series, asset: Asset, start: CandleIdentity, end: CandleIdentity, is_incremental: bool
    ) -> FetchResult:
        """
        Fetch data points for the given asset definition between start_time and end_time.
        """
        return Failure(reason="fetch not implemented")

    # CO: @staticmethod
    # CO: def normalize_timestamp(timestamp: int, is_intraday: bool, zone_info: ZoneInfo) -> datetime:
    # CO:     # if we have intraday values, this is a point in time. Convert to UTC
    # CO:     if is_intraday:
    # CO:         return datetime.fromtimestamp(timestamp, tz=UTC)
    # CO:
    # CO:     # if we have lower frequency data, treat it as a day label, by convention at midnight UTC
    # CO:     # (even if the UTC date of the timestamp could be different, as e.g. in Japan)
    # CO:     local = datetime.fromtimestamp(timestamp, tz=zone_info)
    # CO:     return datetime.combine(local.date(), time.min, tzinfo=UTC)
