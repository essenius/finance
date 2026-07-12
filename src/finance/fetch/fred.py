# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/fred.py

from datetime import UTC, datetime

from ..common.model import Asset, FetchResult, Series, SeriesPoint
from .provider import MarketDataProvider

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# check out https://api.stlouisfed.org/fred/series/search?search_text=gold&api_key=...&file_type=json


class FredProvider(MarketDataProvider):
    """FRED daily economic data provider."""

    def fetch(
        self, series: Series, asset: Asset, start_time: datetime, end_time: datetime, is_incremental: bool
    ) -> FetchResult:
        if not self.api_key:
            return FetchResult.fail(series.name, "FRED requires an API key")

        start_date = start_time.date().strftime("%Y-%m-%d")
        end_date = end_time.date().strftime("%Y-%m-%d")

        params = {
            "series_id": asset.provider_code,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "asc",
            "observation_start": start_date,
            "observation_end": end_date,
        }

        return self._safe_call(measurement=series.name, fn=lambda: self._fetch(series, params), context="FRED fetch")

    def _fetch(self, series: Series, params: dict) -> FetchResult:

        response = self.session.get(BASE_URL, params=params, timeout=self.provider_config.timeout_delta().seconds)
        response.raise_for_status()

        data = response.json()
        observations = data.get("observations", [])
        if not observations:
            return FetchResult.fail(series.name, "no 'observations' in response")

        points: list[SeriesPoint] = []

        for observation in observations:
            value_str = observation.get("value")
            date_str = observation.get("date")

            # Skip missing/invalid values
            if value_str in (None, ".", ""):
                continue

            # FRED date is YYYY-MM-DD. While it isn't in UTC,
            # we interpret it as such anyway, since for daily data,
            # dates are labels, not timestamps.
            try:
                time = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except Exception:
                continue

            value = float(value_str)
            points.append(SeriesPoint(series_id=series.id, time=time, close=value))

        return FetchResult.ok_payload(series.name, points)
