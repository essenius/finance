# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/ecb.py

from datetime import UTC, datetime

from ..common.model import FetchPoint, FetchResult
from .provider import MarketDataProvider

BASE_URL = "https://data-api.ecb.europa.eu/service/data"

# example: https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=jsondata&startPeriod=2020-01-01&endPeriod=2020-02-01&detail=dataonly


class EcbProvider(MarketDataProvider):
    """ECB daily FX provider (no intraday)."""

    def fetch(self, name: str, asset: dict, start_timestamp: int, end_timestamp: int) -> FetchResult:
        symbol = asset["symbol"]
        field = asset["fields"][0]
        start_date = datetime.fromtimestamp(start_timestamp, tz=UTC).date().isoformat()
        end_date = datetime.fromtimestamp(end_timestamp, tz=UTC).date().isoformat()

        params = {"format": "jsondata", "startPeriod": start_date, "endPeriod": end_date, "detail": "dataonly"}
        return self._safe_call(
            measurement=name, fn=lambda: self._fetch(name, symbol, field, params), context=f"ECB fetch of {symbol}"
        )

    def _make_url(self, symbol) -> str | None:
        parts = symbol.split("_")
        if len(parts) != 2:
            return None
        base, quote = parts
        if not base or not quote:
            return None
        return f"{BASE_URL}/EXR/D.{base}.{quote}.SP00.A"

    def _extract_observations(self, name: str, data: dict) -> FetchResult:
        series_result = self._safe_get(data, ["dataSets", 0, "series"])
        if not series_result.ok:
            return FetchResult.fail(name, "Could not find ECB series in response", series_result.reason)

        series = series_result.payload

        try:
            first_key = next(iter(series))
        except StopIteration:
            return FetchResult.fail(name, "Could not find ECB series entry in response")

        observations_result = self._safe_get(series, [first_key, "observations"])
        if not observations_result.ok:
            return FetchResult.fail(name, "Could not find ECB observations", observations_result.reason)

        return FetchResult.ok_payload(name, observations_result.payload)

    def _extract_dates(self, name: str, data: dict) -> FetchResult:
        date_values_result = self._safe_get(data, ["structure", "dimensions", "observation", 0, "values"])
        if not date_values_result.ok:
            return FetchResult.fail(name, "Could not find ECB date metadata", date_values_result.reason)

        return FetchResult.ok_payload(name, date_values_result.payload)

    def _parse_points(self, observations: dict, date_values: list, field: str) -> list[FetchPoint]:
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

            points.append(FetchPoint(timestamp=ts, fields={field: value}))

        return points

    def _fetch(self, name: str, symbol: str, field: str, params: dict) -> FetchResult:
        """
        symbol: e.g. 'USD_EUR'
        returns: [{"timestamp": int, "fields": {field: float}}] or []
        """

        url = self._make_url(symbol)
        if url is None:
            return FetchResult.fail(name, f"Could not split symbol '{symbol}' into base_quote for url")

        # was ?format=jsondata&lastNObservations=1&detail=dataonly"

        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extract series
        observations_result = self._extract_observations(name, data)
        if not observations_result.ok:
            return observations_result
        observations = observations_result.payload

        # Extract date metadata
        dates_result = self._extract_dates(name, data)
        if not dates_result.ok:
            return dates_result
        date_values = dates_result.payload

        # Convert to FetchPoints
        points = self._parse_points(observations, date_values, field)

        return FetchResult.ok_payload(name, points)
