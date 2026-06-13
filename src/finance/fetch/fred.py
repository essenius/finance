# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/fred.py

from datetime import UTC, datetime

from finance.common.time_utils import to_utc_midnight

from ..common.model import FetchPoint, FetchResult
from .provider import MarketDataProvider

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredProvider(MarketDataProvider):
    """FRED daily economic data provider."""

    def fetch(self, name: str, asset: dict, start_timestamp: int, end_timestamp: int) -> FetchResult:
        symbol = asset["symbol"]
        field = asset["fields"][0]

        if not self.api_key:
            return FetchResult.fail(name, "FRED requires an API key")

        start_date = datetime.fromtimestamp(start_timestamp, tz=UTC).date().strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(end_timestamp, tz=UTC).date().strftime("%Y-%m-%d")

        params = {
            "series_id": symbol,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "observation_start": start_date,
            "observation_end": end_date,
        }

        return self._safe_call(measurement=name, fn=lambda: self._fetch(name, field, params), context="FRED fetch")

    def _fetch(self, name: str, field: str, params: dict) -> FetchResult:

        response = self.session.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        observations = data.get("observations", [])
        if not observations:
            return FetchResult.fail(name, "no 'observations' in response")

        points: list[FetchPoint] = []

        for observation in observations:
            value_str = observation.get("value")
            date_str = observation.get("date")

            # Skip missing/invalid values
            if value_str in (None, ".", ""):
                continue

            # FRED date is YYYY-MM-DD
            try:
                local_datetime = datetime.fromisoformat(date_str).replace(tzinfo=self.timezone)
            except Exception:
                continue

            ts = to_utc_midnight(local_datetime)
            value = float(value_str)
            points.append(FetchPoint(timestamp=ts, fields={field: value}))

        return FetchResult.ok_payload(name, points)
