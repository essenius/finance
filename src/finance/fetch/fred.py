# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/fred.py

from datetime import datetime

from ..common.candle_identity import CandleIdentity
from ..common.json_utils import JsonReader
from ..common.model import Asset, FetchData, FetchResult, Series, SeriesPoint
from ..common.time_utils import UTC
from ..common.types import Failure, ParseError, Success
from .provider import MarketDataProvider

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# check out https://api.stlouisfed.org/fred/series/search?search_text=gold&api_key=...&file_type=json


class FredProvider(MarketDataProvider):
    """FRED daily economic data provider."""

    def fetch(
        self, series: Series, asset: Asset, start: CandleIdentity, end: CandleIdentity, is_incremental: bool
    ) -> FetchResult:
        if not self.provider_config.api_key:
            return Failure(reason="FRED requires an API key")

        start_date = start.date().strftime("%Y-%m-%d")
        end_date = end.date().strftime("%Y-%m-%d")

        params = {
            "series_id": asset.provider_code,
            "api_key": self.provider_config.api_key,
            "file_type": "json",
            "sort_order": "asc",
            "observation_start": start_date,
            "observation_end": end_date,
        }

        return self._safe_call(fn=lambda: self._fetch(series, params), context="FRED fetch")

    # ----------------
    # Private methods
    # ----------------

    def _fetch(self, series: Series, params: dict) -> FetchResult:

        response = self.session.get(BASE_URL, params=params, timeout=self.provider_config.timeout_delta().seconds)
        response.raise_for_status()

        reader = JsonReader(response.json())

        try:
            observations = reader.get_array("observations", allow_missing="no")

            points: list[SeriesPoint] = []

            for observation in observations:
                observation = reader.ensure_type(observation, dict, "observation is no object")
                value_str = observation.get("value")
                date_str = observation.get("date")

                # Skip missing/invalid values
                if value_str in (None, ".", ""):
                    continue

                # FRED date is YYYY-MM-DD. While it isn't in UTC,
                # we interpret it as such anyway, since for daily data,
                # dates are labels, not timestamps.
                try:
                    time = datetime.fromisoformat(str(date_str)).replace(tzinfo=UTC)
                except Exception:
                    continue

                value = float(value_str)
                series_id = series.require_id()
                points.append(SeriesPoint(series_id=series_id, time=time, close=value))

                result = FetchData(series_id=series_id, points=points, metadata=None)

            return Success(result)
        except ParseError as ve:
            return Failure(str(ve))
