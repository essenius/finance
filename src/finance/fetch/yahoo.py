# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/yahoo.py

from urllib.parse import quote, urlencode

from ..common.model import FetchPoint, FetchResult, MeasurementResult, Result
from .provider import MarketDataProvider

SUPPORTED_FIELDS = ["open", "high", "low", "close", "volume"]


class YahooProvider(MarketDataProvider):
    """Unified Yahoo Finance data provider."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    # ----
    # API
    # ----

    def fetch(self, name: str, asset: dict, start_timestamp: int, end_timestamp: int) -> FetchResult:
        symbol: str = asset["symbol"]
        fields: list[str] = asset["fields"]
        interval: str = asset["interval"]

        url = self._build_url(symbol, interval, start_timestamp, end_timestamp)
        result = self._safe_call(measurement=name, fn=lambda: self._fetch_impl(url, name), context="Yahoo fetch")

        if not result.ok:
            return result

        candles = self._extract_candles(result, fields)

        # Fallback to metadata if no candles
        if not candles.payload:
            meta = result.payload.get("meta", {})
            return self._get_from_meta(name, fields, meta, start_timestamp, end_timestamp)

        return candles

    # -----------
    # Fetch data
    # -----------

    def _build_url(self, symbol, interval_str, start_ts, end_ts):
        encoded = quote(symbol, safe="")
        params = {
            "interval": interval_str,
            "period1": int(start_ts),
            "period2": int(end_ts),
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

    def _resolve_field_mapping(self, requested_fields: list[str]) -> Result[tuple[list[str], list[str]]]:
        if requested_fields is None:
            requested_fields = SUPPORTED_FIELDS

        if all(f in SUPPORTED_FIELDS for f in requested_fields):
            return Result.ok_payload((requested_fields[:], requested_fields[:]))

        if len(requested_fields) != 1:
            return Result.fail(f"Unsupported field combination: {requested_fields}")

        return Result.ok_payload((["close"], [requested_fields[0]]))

    def _extract_arrays(self, payload: dict, selected_fields: list[str]) -> Result[tuple[list[int], dict[str, list]]]:
        """
        returns (result, error) where
        """
        timestamps = payload.get("timestamp")
        if not timestamps:
            return Result.fail("no timestamp in result")

        quote_result = self._safe_get(payload, ["indicators", "quote", 0])
        if not quote_result.ok:
            return Result.fail("unexpected quote structure", quote_result.reason)

        quote = quote_result.payload
        arrays = {f: quote.get(f) or [] for f in selected_fields}
        return Result.ok_payload((timestamps, arrays))

    def _build_candles(self, timestamps, arrays, selected_fields, mapped_fields):
        candles = []
        invalid_count = 0

        for i, ts in enumerate(timestamps):
            values = {}

            for src, dst in zip(selected_fields, mapped_fields, strict=True):
                arr = arrays[src]
                v = arr[i] if i < len(arr) else None
                if v is None:
                    invalid_count += 1
                    break
                values[dst] = v

            else:
                candles.append(FetchPoint(fields=values, timestamp=ts))

        return candles, invalid_count

    def _extract_candles(
        self, results: MeasurementResult[dict], requested_fields: list[str] | None = None
    ) -> FetchResult:
        name = results.measurement
        payload = results.payload

        mapping = self._resolve_field_mapping(requested_fields)
        if not mapping.ok:
            return FetchResult.from_result(mapping, name)
        selected_fields, mapped_fields = mapping.payload

        arrays_result = self._extract_arrays(payload, selected_fields)
        if not arrays_result.ok:
            return FetchResult.from_result(arrays_result, name)

        timestamps, arrays = arrays_result.payload
        candles, invalid_count = self._build_candles(timestamps, arrays, selected_fields, mapped_fields)

        warnings = []
        if invalid_count:
            warnings.append(f"Skipped {invalid_count} invalid candles")

        return FetchResult.ok_payload(name, candles, warnings)

    # --------------
    # Get from meta
    # --------------

    META_FIELD_MAP = {
        "close": "regularMarketPrice",
        "high": "regularMarketDayHigh",
        "low": "regularMarketDayLow",
        "volume": "regularMarketVolume",
        # "open" is intentionally excluded — cannot synthesize
    }

    def _get_from_meta(
        self, name: str, fields: list[str], meta: dict, start_timestamp: int, end_timestamp: int
    ) -> FetchResult:

        timestamp = meta.get("regularMarketTime")
        reason = "Cannot synthesize from metadata"
        # Only use fallback if timestamp exists
        if timestamp is None:
            return FetchResult.fail(name, reason, "timestamp missing")

        # Reject metadata outside requested window
        if not (start_timestamp <= timestamp <= end_timestamp):
            return FetchResult.fail(name, reason, "metadata timestamp outside requested range")
        # Build synthetic fields
        synthetic = {}
        warnings = []
        error = None
        # Candle subset mode
        for field in fields:
            if field in SUPPORTED_FIELDS:
                if field == "open":
                    error = "Cannot synthesize 'open'"
                    continue

                meta_key = self.META_FIELD_MAP[field]
                v = meta.get(meta_key)

            else:
                # mapped field → use regularMarketPrice
                v = meta.get("regularMarketPrice")

            if v is None:
                warnings.append(f"Missing value for '{field}'")
                continue

            synthetic[field] = float(v)

        if error or not synthetic:
            return FetchResult.fail(name, reason, error or "No fields synthesized", warnings)

        return FetchResult.ok_payload(name, [FetchPoint(fields=synthetic, timestamp=timestamp)], warnings)
