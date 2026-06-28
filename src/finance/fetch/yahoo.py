# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/yahoo.py

from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from ..common.model import Asset, FetchResult, MeasurementResult, Result, Series, SeriesPoint
from .provider import MarketDataProvider


class YahooProvider(MarketDataProvider):
    """Unified Yahoo Finance data provider."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    # ----
    # API
    # ----

    def fetch(self, series: Series, asset: Asset, start_time: datetime, end_time: datetime) -> FetchResult:
        name = series.name
        url = self._build_url(asset.provider_code, series.interval, start_time, end_time)
        result = self._safe_call(measurement=name, fn=lambda: self._fetch_impl(url, name), context="Yahoo fetch")

        if not result.ok:
            return result

        candles = self._extract_candles(series, result.payload)

        # Fallback to metadata if no candles
        if not candles.payload:
            meta = result.payload.get("meta", {})
            return self._get_from_meta(series, meta, start_time, end_time)

        return candles

    # -----------
    # Fetch data
    # -----------

    def _build_url(self, provider_code, interval_str, start_time, end_time):
        encoded = quote(provider_code, safe="")
        params = {
            "interval": interval_str,
            "period1": int(start_time.timestamp()),
            "period2": int(end_time.timestamp()),
            "includePrePost": "false",
            "events": "div,splits",
        }
        return f"{self.BASE_URL.format(symbol=encoded)}?{urlencode(params)}"

    def _fetch_impl(self, url, name) -> MeasurementResult[dict]:
        """fetch the response from the provider. Is called from a _safe_call wrapper so can throw"""
        headers = {"User-Agent": "Mozilla/5.0"}
        response = self.session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        error_response = self._error_response(data)
        if error_response:
            return MeasurementResult.fail(name, "Could not interpret fetch response", error_response)

        # must work since is_error_response checks for it
        value = data["chart"]["result"][0]
        return MeasurementResult.ok_payload(name, value)

    def _error_response(self, data) -> str | None:
        chart = data.get("chart", {})
        if chart == {}:
            return "no 'chart' in response"
        if chart.get("error"):
            return str(chart["error"])
        result = chart.get("result")
        if result is None or result == []:
            return "result empty"
        return None

    # -----------------------------
    # Extract candles with helpers
    # -----------------------------

    def _extract_arrays(self, payload: dict, selected_fields: list[str]) -> Result[tuple[list[int], dict[str, list]]]:

        timestamps = payload.get("timestamp")
        if not timestamps:
            return Result.fail("no timestamp in result")

        quote_result = self._safe_get(payload, ["indicators", "quote", 0])
        if not quote_result.ok:
            return Result.fail("unexpected quote structure", quote_result.reason)

        quote = quote_result.payload
        arrays = {f: quote.get(f) or [] for f in selected_fields}
        return Result.ok_payload((timestamps, arrays))

    def _build_candles(
        self, timestamps, arrays, point_factory: Callable[..., SeriesPoint]
    ) -> tuple[list[SeriesPoint], int]:
        """
        Grab the candle values from the input arrays, optimizing the number of fields read.
        The callable is a partially resolved constructor for a SeriesPoint subclass, which also delivers the required candle fields,
        and a mapping to its field name(s)
        """
        candles = []
        invalid_count = 0

        factory_class = point_factory.func
        for i, ts in enumerate(timestamps):
            values = {}
            raw_dt = datetime.fromtimestamp(ts, tz=UTC)
            time = factory_class.normalize_time(raw_dt)

            for field in factory_class.fields():
                arr = arrays[field]
                v = arr[i] if i < len(arr) else None
                if v is None:
                    invalid_count += 1
                    break
                values[field] = v

            else:
                mapped = factory_class.map(values)
                point = point_factory(time=time, **mapped)
                candles.append(point)

        return candles, invalid_count

    def _extract_candles(self, series: Series, payload: dict | None = None) -> FetchResult:
        name = series.name
        point_factory = SeriesPoint.factory(series)
        fields = point_factory.func.fields()

        arrays_result = self._extract_arrays(payload, fields)
        if not arrays_result.ok:
            return FetchResult.from_result(arrays_result, name)

        timestamps, arrays = arrays_result.payload
        candles, invalid_count = self._build_candles(timestamps, arrays, point_factory)

        warnings = []
        if invalid_count:
            warnings.append(f"Skipped {invalid_count} invalid candles")

        return FetchResult.ok_payload(name, candles, warnings)

    # --------------
    # Get from meta
    # --------------

    META_FIELD_MAP = {
        "open": None,  # cannot synthesize
        "close": "regularMarketPrice",
        "high": "regularMarketDayHigh",
        "low": "regularMarketDayLow",
        "volume": "regularMarketVolume",
    }

    def _get_from_meta(self, series: Series, meta: dict, start_time: datetime, end_time: datetime) -> FetchResult:

        name = series.name
        timestamp = meta.get("regularMarketTime")
        reason = "Cannot synthesize from metadata"
        # Only use fallback if timestamp exists
        if timestamp is None:
            return FetchResult.fail(name, reason, "timestamp missing")

        time = datetime.fromtimestamp(timestamp, UTC)

        # Reject metadata outside requested window
        if not (start_time <= time <= end_time):
            return FetchResult.fail(name, reason, "metadata timestamp outside requested range")

        factory = SeriesPoint.factory(series)
        fields = factory.func.fields()
        synthetic = {field: None for field in fields}
        warnings = []
        found_value = False
        for field in fields:
            meta_key = self.META_FIELD_MAP.get(field)
            if meta_key is None:
                continue
            v = meta.get(meta_key)
            if v is None:
                warnings.append(f"Missing value for '{field}'")
                continue

            found_value = True
            synthetic[field] = float(v)

        if not found_value:
            return FetchResult.fail(name, reason, "No fields synthesized", warnings)

        mapped = factory.func.map(synthetic)
        return FetchResult.ok_payload(name, [factory(time=time, **mapped)], warnings)
