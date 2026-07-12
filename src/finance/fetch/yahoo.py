# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/yahoo.py

from collections.abc import Callable
from datetime import UTC, datetime, time
from functools import partial
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from ..common.model import Asset, Candle, FetchResult, MeasurementResult, Result, Series, SeriesPoint
from .provider import MarketDataProvider


class YahooProvider(MarketDataProvider):
    """Unified Yahoo Finance data provider."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    # ----
    # API
    # ----

    def fetch(
        self, series: Series, asset: Asset, start_time: datetime, end_time: datetime, is_incremental: bool
    ) -> FetchResult:
        name = series.name
        url, params = self._build_url(asset.provider_code, series.interval, start_time, end_time)
        result = self._safe_call(measurement=name, fn=lambda: self._fetch_impl(url, name, params), context="Yahoo fetch")

        if not result.ok:
            return result

        def normalize_yahoo(timestamp: int, is_intraday: bool, zone_info: ZoneInfo) -> datetime | None:
            result = self.normalize_timestamp(timestamp, is_intraday, zone_info)
            # invalidate timestamps for today with daily intervals or less frequently (day not done yet)
            today_midnight = datetime.combine(self.now().date(), time.min, tzinfo=UTC)
            if not is_intraday and result >= today_midnight:
                return None
            return result

        def bind_normalizer(is_intraday: bool, timezone: str):
            zone_info = ZoneInfo(timezone)
            return partial(normalize_yahoo, is_intraday=is_intraday, zone_info=zone_info)

        meta = result.payload.get("meta", {})
        timezone = meta.get("exchangeTimezoneName")
        if timezone is None:
            return FetchResult.fail(
                {series.name},
                f"Could not parse series '{series.name}' in Yahoo fetch result",
                "missing exchangeTimeZoneName in meta",
            )

        normalize = bind_normalizer(series.is_intraday(), timezone)
        return self._extract_candles(series, normalize, result.payload)

    # -----------
    # Fetch data
    # -----------

    def _build_url(self, provider_code, interval_str, start_time, end_time) -> tuple[str, dict]:
        encoded = quote(provider_code, safe="")
        params = {
            "interval": interval_str,
            "period1": int(start_time.timestamp()),
            "period2": int(end_time.timestamp()),
            "includePrePost": "false",
            "events": "div,splits",
        }
        return f"{self.BASE_URL.format(symbol=encoded)}", params

    def _fetch_impl(self, url, name, params) -> MeasurementResult[dict]:
        """fetch the response from the provider. Is called from a _safe_call wrapper so can throw"""
        headers = {"User-Agent": "Mozilla/5.0"}
        response = self.session.get(url, params=params, headers=headers, timeout=self.provider_config.timeout_delta().seconds)
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

    def _extract_arrays(self, payload: dict) -> Result[tuple[list[int], dict[str, list]]]:

        timestamps = payload.get("timestamp")
        if not timestamps:
            return Result.fail("no timestamp in result")

        quote_result = self._safe_get(payload, ["indicators", "quote", 0])
        if not quote_result.ok:
            return Result.fail("unexpected quote structure", quote_result.reason)

        quote = quote_result.payload
        arrays = {f: quote.get(f) or [] for f in Candle.values()}
        return Result.ok_payload((timestamps, arrays))

    def _build_candles(
        self, timestamps, arrays, point_factory: Callable[..., SeriesPoint], normalize
    ) -> tuple[list[SeriesPoint], list[str]]:
        """
        Grab the candle values from the input arrays, optimizing the number of fields read.
        The callable is a partially resolved constructor for a SeriesPoint subclass, which also delivers the required candle fields,
        and a mapping to its field name(s)
        """
        candles = []
        invalid_count = 0
        incomplete_count = 0

        for i, ts in enumerate(timestamps):
            if len(arrays["close"]) <= i or arrays["close"][i] is None:
                invalid_count += 1
                continue
            values = {}
            time = normalize(ts)
            # including today for daily candles (day not done yet)
            if time is None:
                continue
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
            point = point_factory(time=time, **values)
            candles.append(point)

        warnings = []
        if invalid_count > 0:
            warnings.append(f"Skipped {invalid_count} candles without close value")
        if incomplete_count > 0:
            warnings.append(f"{incomplete_count} incomplete candles")
        return candles, warnings

    def _extract_candles(self, series: Series, normalize, payload: dict | None = None) -> FetchResult:
        name = series.name
        point_factory = partial(SeriesPoint, series_id=series.id)
        arrays_result = self._extract_arrays(payload)
        if not arrays_result.ok:
            return FetchResult.from_result(arrays_result, name)

        timestamps, arrays = arrays_result.payload
        candles, warnings = self._build_candles(timestamps, arrays, point_factory, normalize)

        return FetchResult.ok_payload(name, candles, warnings)
