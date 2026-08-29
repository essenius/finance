# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/ecb.py

from datetime import datetime

from ..common.candle_identity import CandleIdentity
from ..common.json_utils import JsonArray, JsonObject, JsonReader
from ..common.model import Asset, FetchData, FetchResult, Series, SeriesPoint
from ..common.time_utils import UTC
from ..common.types import Failure, ParseError, Success
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
            fn=lambda: self._fetch(series, asset.provider_code, params), context=f"ECB fetch of {series.name}"
        )

    # ----------------
    # Private methods
    # ----------------

    def _fetch(self, series: Series, provider_code: str, params: dict) -> FetchResult:
        """provider_code: e.g. 'USD_EUR'"""

        url = self._make_url(provider_code)
        if url is None:
            return Failure(reason=f"Could not split provider code '{provider_code}' into base_quote for url")

        response = self.session.get(url, params=params, timeout=self.provider_config.timeout_delta().seconds)
        response.raise_for_status()
        reader = JsonReader(response.json())

        # Extract series values

        try:
            # go into the "0:0:0:0:0" key, which might have other numbers in it
            series_obj = reader.get_first_object_value(["dataSets", 0, "series"])
        except ParseError as ve:
            return Failure(reason="Could not find ECB series", error=str(ve))

        series_reader = JsonReader(series_obj)
        try:
            observations = series_reader.get_object("observations", allow_missing="no")
        except ParseError as ve:
            return Failure(reason="Could not find ECB observations", error=str(ve))

        # Extract date structures for series

        try:
            date_values = reader.get_array(["structure", "dimensions", "observation", 0, "values"])
        except ParseError as ve:
            return Failure(reason="Could not find ECB date metadata", error=str(ve))

        # Extract data points

        points = self._parse_points(series, observations, date_values)
        result = FetchData(series_id=series.require_id(), points=points, metadata=None)
        return Success(result)

    def _make_url(self, provider_code: str) -> str | None:
        parts = provider_code.split("_")
        if len(parts) != 2:
            return None
        base, quote = parts
        if not base or not quote:
            return None
        return f"{BASE_URL}/EXR/D.{base}.{quote}.SP00.A"

    def _parse_points(self, series: Series, observations: JsonObject, date_values: JsonArray) -> list[SeriesPoint]:
        points: list[SeriesPoint] = []

        date_reader = JsonReader(date_values)
        for obs_index, obs_value in observations.items():
            try:
                # we use the id field as we only need the date.
                date_str = date_reader.require(str, [int(obs_index), "id"])

                value_reader = JsonReader(obs_value)
                value = value_reader.get_array(expected_type=float)[0]
            except Exception:
                continue

            try:
                # synchronize timestamps to UTC (ECB uses CET).
                # this is OK, since for daily data, dates are labels. We always
                # express them in UTC midnight so we can compare different series.
                time = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except Exception:
                continue

            points.append(SeriesPoint(series_id=series.require_id(), time=time, close=value))

        return points
