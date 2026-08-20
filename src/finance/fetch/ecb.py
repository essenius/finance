# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/ecb.py

from datetime import UTC, datetime

from ..common.candle_identity import CandleIdentity
from ..common.model import Asset, FetchData, FetchResult, Series, SeriesPoint
from ..common.result import Failure, Result, Success
from .provider import MarketDataProvider

BASE_URL = "https://data-api.ecb.europa.eu/service/data"

# example: https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=jsondata&startPeriod=2020-01-01&endPeriod=2020-02-01&detail=dataonly


class EcbProvider(MarketDataProvider):
    """ECB daily FX provider (no intraday)."""

    def fetch(
        self, series: Series, asset: Asset, start: CandleIdentity, end: CandleIdentity, is_incremental: bool
    ) -> FetchResult:
        start_date = start.date().isoformat()
        end_date = end.date().isoformat()

        params = {"updatedAfter": start_date} if is_incremental else {"startPeriod": start_date, "endPeriod": end_date}
        params = params | {"format": "jsondata", "detail": "dataonly"}

        return self._safe_call(
            measurement=series.name,
            fn=lambda: self._fetch(series, asset.provider_code, params),
            context=f"ECB fetch of {series.name}",
        )

    def _make_url(self, provider_code) -> str | None:
        parts = provider_code.split("_")
        if len(parts) != 2:
            return None
        base, quote = parts
        if not base or not quote:
            return None
        return f"{BASE_URL}/EXR/D.{base}.{quote}.SP00.A"

    def _extract_observations(self, series: Series, data: dict) -> Result[dict]:
        series_result = self._safe_get(data, ["dataSets", 0, "series"])
        if series_result.ok is False:
            return Failure(reason="Could not find ECB series in response", error=series_result.reason)

        raw_series = series_result.payload

        try:
            first_key = next(iter(raw_series))
        except StopIteration:
            return Failure(reason="Could not find ECB series entry in response")

        observations_result = self._safe_get(raw_series, [first_key, "observations"])
        if observations_result.ok is False:
            return Failure(reason="Could not find ECB observations", error=observations_result.reason)

        return Success(observations_result.payload)

    def _extract_dates(self, name: str, data: dict) -> Result[list]:
        date_values_result = self._safe_get(data, ["structure", "dimensions", "observation", 0, "values"])
        if date_values_result.ok is False:
            return Failure(reason="Could not find ECB date metadata", error=date_values_result.reason)

        return Success(date_values_result.payload)

    def _parse_points(self, series: Series, observations: dict, date_values: list) -> list[SeriesPoint]:
        points: list[SeriesPoint] = []

        for obs_index, obs_value in observations.items():
            try:
                # we use the id field as we only need the date.
                date_str = date_values[int(obs_index)]["id"]
                value = float(obs_value[0])
            except Exception:
                continue

            try:
                # synchronize timestamps to UTC (ECB uses CET).
                # this is OK, since for daily data, dates are labels. We always
                # express them in UTC midnight so we can compare different series.
                time = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except Exception:
                continue

            points.append(SeriesPoint(series_id=series.id, time=time, close=value))

        return points

    def _fetch(self, series: Series, provider_code: str, params: dict) -> FetchResult:
        """provider_code: e.g. 'USD_EUR'"""

        name = series.name
        url = self._make_url(provider_code)
        if url is None:
            return Failure(reason=f"Could not split provider code '{provider_code}' into base_quote for url")

        response = self.session.get(url, params=params, timeout=self.provider_config.timeout_delta().seconds)
        response.raise_for_status()
        data = response.json()

        # Extract series
        observations_result = self._extract_observations(series, data)
        if observations_result.ok is False:
            return observations_result
        observations = observations_result.payload

        # Extract date metadata
        dates_result = self._extract_dates(name, data)
        if dates_result.ok is False:
            return dates_result
        date_values = dates_result.payload

        points = self._parse_points(series, observations, date_values)

        result = FetchData(series_id=series.id, points=points, metadata=None)

        return Success(result)
