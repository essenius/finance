# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/provider.py

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

import requests

from ..common.candle_identity import CandleIdentity
from ..common.configuration import ProviderConfig
from ..common.json_utils import JsonLike
from ..common.model import FetchResult, Series
from ..common.time_utils import now_second_precision
from ..common.types import Failure, Result


class ResponseProtocol(Protocol):
    status_code: int
    text: str

    def json(self) -> JsonLike: ...
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

    config: ProviderConfig

    @property
    def name(self) -> str:
        return self.config.name

    def __init__(
        self,
        provider_config: ProviderConfig,
        *,
        session: SessionProtocol | None = None,
        now_provider: Callable[[], datetime] = now_second_precision,
    ):
        self.config = provider_config
        # not taking requests.session as the default, to avoid unnecessary construction
        self.session = session or requests.Session()
        self.now = now_provider

    def fetch(self, series: Series, start: CandleIdentity, end: CandleIdentity, is_incremental: bool) -> FetchResult:
        """
        Fetch data points for the given asset definition between start_time and end_time.
        """
        return Failure(reason="fetch not implemented")

    def _safe_call[T](self, fn: Callable[[], Result[T]], *, series: Series) -> Result[T]:
        try:
            return fn()
        except Exception as exc:
            return Failure(reason=f"Exception during {self.name} fetch of {series.name} ({series.id})", error=str(exc))

    def sweep_config(self, interval: timedelta):
        return self.config.get_sweep(interval)
