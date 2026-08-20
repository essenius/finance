# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/yahoo.py

from datetime import UTC, date, datetime, time
from urllib.parse import quote
from zoneinfo import ZoneInfo

from finance.common.applogger import AppLogger
from finance.common.candle_identity import CandleIdentity

from ..common.model import Asset, AssetMetadata, FetchData, FetchResult, Series, SeriesPoint, SeriesPointsResult
from ..common.result import Failure, Result, Success
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

        def FetchFailure(error: str) -> Failure:

            return Failure(f"Could not parse series '{series.name}' in Yahoo fetch result", error=error)

        name = series.name
        start_timestamp = start.start_timestamp()
        end_timestamp = end.end_timestamp()
        url, params = self._build_url(asset.provider_code, series.interval, start_timestamp, end_timestamp)
        result = self._safe_call(
            measurement=name, fn=lambda: self._fetch_impl(url, name, params), context="Yahoo fetch"
        )

        if result.ok is False:
            return result

        meta = result.payload.get("meta", {})

        metadata_result = self._extract_metadata(meta)
        if metadata_result.ok is False:
            return FetchFailure(error=metadata_result.reason)

        metadata = metadata_result.payload
        points_result = self._extract_candles(series, result.payload, metadata.timezone)
        if points_result.ok is False:
            return FetchFailure(error=points_result.reason)
        result = FetchData(series_id=series.id, points=points_result.payload, metadata=metadata)
        return Success(result)

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

    def _fetch_impl(self, url, name, params) -> Result[dict]:
        """fetch the response from the provider. Is called from a _safe_call wrapper so can throw"""
        headers = {"User-Agent": "Mozilla/5.0"}
        response = self.session.get(
            url, params=params, headers=headers, timeout=self.provider_config.timeout_delta().seconds
        )
        response.raise_for_status()
        data = response.json()

        error_response = self._error_response(data)
        if error_response:
            return Failure(reason="Could not interpret fetch response", error=error_response)

        # must work since is_error_response checks for it
        value = data["chart"]["result"][0]
        return Success(value)

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
    # Extract metadata
    # -----------------------------

    def _extract_metadata(self, meta: dict) -> Result[AssetMetadata]:

        def time_from_timestamp(timestamp: int | None, timezone: ZoneInfo) -> time | None:
            return None if timestamp is None else datetime.fromtimestamp(timestamp, UTC).astimezone(timezone).time()

        def date_from_timestamp(timestamp: int | None, timezone: ZoneInfo) -> date | None:
            return None if timestamp is None else datetime.fromtimestamp(timestamp, UTC).astimezone(timezone).date()

        timezone_name = meta.get("exchangeTimezoneName")
        if timezone_name is None:
            return Failure(reason="missing exchangeTimezoneName in meta")

        try:
            timezone = ZoneInfo(timezone_name)
        except Exception as e:
            return Failure(reason=f"invalid exchange timezone '{timezone_name}': {e}")

        first_trade_date = None
        first_trade_timestamp = meta.get("firstTradeDate")
        first_trade_date = date_from_timestamp(first_trade_timestamp, timezone)

        market_open = None
        market_close = None

        regular_period = meta.get("currentTradingPeriod", {}).get("regular", {})
        if regular_period:
            start = regular_period.get("start")
            end = regular_period.get("end")
            market_open = time_from_timestamp(start, timezone)
            market_close = time_from_timestamp(end, timezone)

        return Success(
            AssetMetadata(
                short_name=meta.get("shortName"),
                long_name=meta.get("longName"),
                instrument=meta.get("instrumentType"),
                exchange=meta.get("exchangeName"),
                currency=meta.get("currency"),
                first_trade_date=first_trade_date,
                timezone=timezone,
                market_open=market_open,
                market_close=market_close,
            )
        )

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
            return Success(None, warnings=["no timestamp in result"])

        quote_result = self._safe_get(payload, ["indicators", "quote", 0])
        if quote_result.ok is False:
            return Failure(reason=quote_result.reason)

        quote = quote_result.payload
        arrays = {f: quote.get(f) or [] for f in Candle.values()}
        return Success((timestamps, arrays))

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

    def _extract_candles(
        self, series: Series, payload: dict | None = None, timezone: ZoneInfo = UTC
    ) -> SeriesPointsResult:
        arrays_result = self._extract_arrays(payload)
        if arrays_result.ok is False:
            return arrays_result
        if arrays_result.payload is None:
            return Success([], arrays_result.warnings)
        timestamps, arrays = arrays_result.payload
        if timestamps != [] and not self.is_aligned(timestamps[-1], series):
            # remove last element from timestamps and arrays
            print("Removing last element as not aligned")
            timestamps.pop()
            for key in arrays:
                if arrays[key] != []:
                    arrays[key].pop()
        candles, warnings = self._build_candles(timestamps, arrays, series, timezone)

        return Success(candles, warnings)
