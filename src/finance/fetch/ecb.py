# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/ecb.py

from datetime import UTC, datetime

from ..common.model import Asset, DailyValuePoint, FetchResult, MeasurementResult, Series
from .provider import MarketDataProvider

BASE_URL = "https://data-api.ecb.europa.eu/service/data"

# example: https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=jsondata&startPeriod=2020-01-01&endPeriod=2020-02-01&detail=dataonly


class EcbProvider(MarketDataProvider):
    """ECB daily FX provider (no intraday)."""

    def fetch(self, series: Series, asset: Asset, start_timestamp: int, end_timestamp: int) -> FetchResult:
        start_date = datetime.fromtimestamp(start_timestamp, tz=UTC).date().isoformat()
        end_date = datetime.fromtimestamp(end_timestamp, tz=UTC).date().isoformat()

        params = {"format": "jsondata", "startPeriod": start_date, "endPeriod": end_date, "detail": "dataonly"}
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

    def _extract_observations(self, series: Series, data: dict) -> MeasurementResult[dict]:
        series_result = self._safe_get(data, ["dataSets", 0, "series"])
        if not series_result.ok:
            return MeasurementResult.fail(series.name, "Could not find ECB series in response", series_result.reason)

        raw_series = series_result.payload

        try:
            first_key = next(iter(raw_series))
        except StopIteration:
            return MeasurementResult.fail(series.name, "Could not find ECB series entry in response")

        observations_result = self._safe_get(raw_series, [first_key, "observations"])
        if not observations_result.ok:
            return MeasurementResult.fail(series.name, "Could not find ECB observations", observations_result.reason)

        return MeasurementResult.ok_payload(series.name, observations_result.payload)

    def _extract_dates(self, name: str, data: dict) -> MeasurementResult[list]:
        date_values_result = self._safe_get(data, ["structure", "dimensions", "observation", 0, "values"])
        if not date_values_result.ok:
            return MeasurementResult.fail(name, "Could not find ECB date metadata", date_values_result.reason)

        return MeasurementResult.ok_payload(name, date_values_result.payload)

    def _parse_points(self, series: Series, observations: dict, date_values: list) -> list[DailyValuePoint]:
        points = []

        for obs_index, obs_value in observations.items():
            try:
                # we use the id field as we only need the date.
                date_str = date_values[int(obs_index)]["id"]
                value = float(obs_value[0])
            except Exception:
                continue

            try:
                # synchronize timestamps to UTC (ECB uses CET)
                ts = int(datetime.fromisoformat(date_str).replace(tzinfo=UTC).timestamp())
            except Exception:
                continue

            points.append(DailyValuePoint(series_id=series.id, timestamp=ts, value=value))

        return points

    def _fetch(self, series: Series, provider_code: str, params: dict) -> FetchResult:
        """
        provider_code: e.g. 'USD_EUR'
        """

        name = series.name
        url = self._make_url(provider_code)
        if url is None:
            return FetchResult.fail(name, f"Could not split provider code '{provider_code}' into base_quote for url")

        # was ?format=jsondata&lastNObservations=1&detail=dataonly"

        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extract series
        observations_result = self._extract_observations(series, data)
        if not observations_result.ok:
            return observations_result
        observations = observations_result.payload

        # Extract date metadata
        dates_result = self._extract_dates(name, data)
        if not dates_result.ok:
            return dates_result
        date_values = dates_result.payload

        # Convert to DailyValuePoints
        points = self._parse_points(series, observations, date_values)

        return FetchResult.ok_payload(name, points)
