# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/yahoo.py

from datetime import UTC
from urllib.parse import quote
from zoneinfo import ZoneInfo

from finance.common.applogger import AppLogger
from finance.common.candle_identity import CandleIdentity

from ..common.model import Asset, FetchResult, MeasurementResult, Series, SeriesPoint
from ..common.result import Result
from ..common.string_enums import Candle
from .provider import MarketDataProvider

logger = AppLogger("yahoo")


class YahooProvider(MarketDataProvider):
    """Unified Yahoo Finance data provider."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    # ----
    # API
    # ----

    def fetch(
        self, series: Series, asset: Asset, start: CandleIdentity, end: CandleIdentity, is_incremental: bool
    ) -> FetchResult:
        name = series.name
        start_timestamp = start.start_timestamp()
        end_timestamp = end.end_timestamp()
        url, params = self._build_url(asset.provider_code, series.interval, start_timestamp, end_timestamp)
        result = self._safe_call(
            measurement=name, fn=lambda: self._fetch_impl(url, name, params), context="Yahoo fetch"
        )

        if not result.ok:
            return result

        meta = result.payload.get("meta", {})
        timezone = meta.get("exchangeTimezoneName")
        if timezone is None:
            return FetchResult.fail(
                {series.name},
                f"Could not parse series '{series.name}' in Yahoo fetch result",
                "missing exchangeTimeZoneName in meta",
            )

        return self._extract_candles(series, result.payload, asset.timezone)

    # -----------
    # Fetch data
    # -----------

    def _build_url(self, provider_code, interval_str, start_timestamp, end_timestamp) -> tuple[str, dict]:
        encoded = quote(provider_code, safe="")
        params = {
            "interval": interval_str,
            "period1": int(start_timestamp),
            "period2": int(end_timestamp),
            "includePrePost": "false",
            "events": "div,splits",
        }
        return f"{self.BASE_URL.format(symbol=encoded)}", params

    def _fetch_impl(self, url, name, params) -> MeasurementResult[dict]:
        """fetch the response from the provider. Is called from a _safe_call wrapper so can throw"""
        headers = {"User-Agent": "Mozilla/5.0"}
        response = self.session.get(
            url, params=params, headers=headers, timeout=self.provider_config.timeout_delta().seconds
        )
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

    def is_aligned(self, ts: float, series: Series) -> bool:
        # Yahoo's last candle time isn't aligned, it's the last data so far.
        if series.is_daily():
            return True
        seconds = int(series.interval_delta().total_seconds())
        return int(ts) % seconds == 0

    def _extract_arrays(self, payload: dict) -> Result[tuple[list[int], dict[str, list]] | None]:

        timestamps = payload.get("timestamp")
        if not timestamps:
            return Result.ok_payload(None, warnings=["no timestamp in result"])

        quote_result = self._safe_get(payload, ["indicators", "quote", 0])
        if not quote_result.ok:
            return Result.fail("unexpected quote structure", quote_result.reason)

        quote = quote_result.payload
        arrays = {f: quote.get(f) or [] for f in Candle.values()}
        return Result.ok_payload((timestamps, arrays))

    def _build_candles(
        self, timestamps, arrays, series: Series, timezone: ZoneInfo
    ) -> tuple[list[SeriesPoint], list[str]]:
        """
        Grab the candle values from the input arrays, optimizing the number of fields read.
        Returns a list of series points and list of warnings.
        """
        candles = []
        invalid_count = 0
        incomplete_count = 0

        for i, ts in enumerate(timestamps):
            if len(arrays["close"]) <= i or arrays["close"][i] is None:
                invalid_count += 1
                continue
            values = {}
            identity = CandleIdentity.from_timestamp(ts, timezone, series.interval_delta())

            incomplete = False
            for field in Candle.values():
                arr = arrays[field]
                v = arr[i] if i < len(arr) else None
                if v is None:
                    incomplete = True
                    continue
                values[field] = v

            if incomplete:
                incomplete_count += 1
            point = SeriesPoint(series_id=series.id, time=identity.store_label(), **values)
            candles.append(point)

        warnings = []
        if invalid_count > 0:
            warnings.append(f"Skipped {invalid_count} candles without close value")
        if incomplete_count > 0:
            warnings.append(f"{incomplete_count} incomplete candles")
        result_count = len(candles)
        logger.debug(f"Results: {result_count}")
        if len(candles) > 0:
            logger.debug(f" result[0]: {candles[0].time}")
            if len(candles) > 1:
                logger.debug(f" result[-1]: {candles[-1].time}")

        return candles, warnings

    def _extract_candles(self, series: Series, payload: dict | None = None, timezone: ZoneInfo = UTC) -> FetchResult:
        name = series.name
        arrays_result = self._extract_arrays(payload)
        if not arrays_result.ok or arrays_result.payload is None:
            return FetchResult.from_result(arrays_result, name)

        timestamps, arrays = arrays_result.payload
        if timestamps != [] and not self.is_aligned(timestamps[-1], series):
            # remove last element from timestamps and arrays
            print("Removing last element as not aligned")
            timestamps.pop()
            for key in arrays:
                if arrays[key] != []:
                    arrays[key].pop()
        candles, warnings = self._build_candles(timestamps, arrays, series, timezone)

        return FetchResult.ok_payload(name, candles, warnings)
