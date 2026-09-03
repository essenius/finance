# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/yahoo.py

from datetime import date, datetime, time
from urllib.parse import quote
from zoneinfo import ZoneInfo

from ..common.applogger import AppLogger
from ..common.asset_metadata import AssetMetadata
from ..common.candle_identity import CandleIdentity
from ..common.guards import require
from ..common.json_utils import JsonObject, JsonReader
from ..common.model import FetchData, FetchResult, Series, SeriesPoint, SeriesPointsResult
from ..common.string_enums import Candle
from ..common.time_utils import UTC
from ..common.types import Failure, ParseError, Result, Success
from .provider import MarketDataProvider

logger = AppLogger("yahoo")


class YahooProvider(MarketDataProvider):
    """Unified Yahoo Finance data provider."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    # ----
    # API
    # ----

    def fetch(self, series: Series, start: CandleIdentity, end: CandleIdentity, is_incremental: bool) -> FetchResult:

        def fetch_failure(error: str) -> Failure:
            return Failure(f"Could not parse series '{series.name}' in Yahoo fetch result", error=error)

        start_timestamp = start.start_timestamp()
        end_timestamp = end.end_timestamp()
        # quirk in Yahoo: you don't get anything with daily series if both start and end are in the same day
        if series.is_daily() and start.value.date() == end.value.date():
            id = series.calendar.last_identity_before(start.value)
            start_timestamp = id.end_timestamp()
        url, params = self._build_url(series.asset.provider_code, series.interval, start_timestamp, end_timestamp)
        result = self._safe_call(fn=lambda: self._fetch_impl(url=url, params=params), series=series)

        if result.ok is False:
            return result
        reader = JsonReader(result.payload)
        meta_reader = reader.reader_for("meta")

        metadata_result = self._extract_metadata(meta_reader)
        if metadata_result.ok is False:
            return fetch_failure(error=metadata_result.reason)

        metadata = metadata_result.payload
        points_result = self._extract_candles(series, reader, require(metadata.timezone, "metadata timezone"))
        if points_result.ok is False:
            return fetch_failure(error=points_result.reason)
        result = FetchData(
            series_id=series.require_id(), series=series, points=points_result.payload, metadata=metadata
        )
        return Success(result)

    # ----------------
    # Private methods
    # ----------------

    def _build_candles(
        self, timestamps: list[int], arrays: dict[str, list[float | None]], series: Series, timezone: ZoneInfo
    ) -> tuple[list[SeriesPoint], list[str]]:
        """
        Grab the candle values from the input arrays, optimizing the number of fields read.
        Returns a list of series points and list of warnings.
        """
        candles: list[SeriesPoint] = []
        invalid_count = 0
        incomplete_count = 0

        for i, ts in enumerate(timestamps):
            if len(arrays["close"]) <= i or arrays["close"][i] is None:
                invalid_count += 1
                continue
            values: dict[str, float] = {}
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
            point = SeriesPoint(series_id=series.require_id(), time=identity.store_label(), **values)
            candles.append(point)

        warnings: list[str] = []
        if invalid_count > 0:
            warnings.append(f"Skipped {invalid_count} candles without close value")
        if incomplete_count > 0:
            warnings.append(f"{incomplete_count} incomplete candles")
        if len(candles) > 0:
            logger.debug(f" result[0]: {candles[0].time}")
            if len(candles) > 1:
                logger.debug(f" result[-1]: {candles[-1].time}")

        return candles, warnings

    def _build_url(
        self, provider_code: str, interval_str: str, start_timestamp: int, end_timestamp: int
    ) -> tuple[str, dict[str, int | str]]:
        encoded = quote(provider_code, safe="")
        params: dict[str, int | str] = {
            "interval": interval_str,
            "period1": start_timestamp,
            "period2": end_timestamp,
            "includePrePost": "false",
            "events": "div,splits",
        }
        return f"{self.BASE_URL.format(symbol=encoded)}", params

    def _extract_arrays(self, reader: JsonReader) -> Result[tuple[list[int], dict[str, list[float | None]]] | None]:
        try:
            timestamps = reader.get_array("timestamp", expected_type=int, allow_missing="yes")
            if not timestamps:
                return Success(None, warnings=["no timestamp in result"])

            quote_reader = reader.reader_for(["indicators", "quote", 0])
            arrays = {
                f: quote_reader.get_nullable_array(f, expected_type=float, allow_missing="yes") for f in Candle.values()
            }
            return Success((timestamps, arrays))
        except ParseError as ve:
            return Failure(reason=str(ve))

    def _extract_candles(self, series: Series, reader: JsonReader, timezone: ZoneInfo = UTC) -> SeriesPointsResult:
        arrays_result = self._extract_arrays(reader)
        if arrays_result.ok is False:
            return arrays_result
        if arrays_result.payload is None:
            return Success([], arrays_result.warnings)
        timestamps, arrays = arrays_result.payload
        # remove last element from timestamps and arrays if timestamp not aligned with interval period
        if timestamps != [] and not self._is_aligned(timestamps[-1], series):
            popped = timestamps.pop()
            logger.debug(
                f"Removed last candle as timestamp {datetime.fromtimestamp(popped).astimezone(UTC)} not aligned"
            )
            for key in arrays:
                if arrays[key] != []:
                    arrays[key].pop()
        candles, warnings = self._build_candles(timestamps, arrays, series, timezone)

        return Success(candles, warnings)

    def _extract_metadata(self, meta_reader: JsonReader) -> Result[AssetMetadata]:

        def time_from_timestamp(timestamp: int | None, timezone: ZoneInfo) -> time | None:
            return None if timestamp is None else datetime.fromtimestamp(timestamp, UTC).astimezone(timezone).time()

        def date_from_timestamp(timestamp: int | None, timezone: ZoneInfo) -> date | None:
            return None if timestamp is None else datetime.fromtimestamp(timestamp, UTC).astimezone(timezone).date()

        timezone_name = meta_reader.get(str, "exchangeTimezoneName", default="")
        if not timezone_name:
            return Failure(reason="missing exchangeTimezoneName in meta")

        try:
            timezone = ZoneInfo(timezone_name)
        except Exception as e:
            return Failure(reason=f"invalid exchange timezone '{timezone_name}': {e}")

        first_trade_timestamp = meta_reader.get(int, "firstTradeDate", default=0)
        first_available_date = date_from_timestamp(first_trade_timestamp, timezone)

        market_open = None
        market_close = None

        period_reader = meta_reader.reader_for(["currentTradingPeriod", "regular"], allow_missing="yes")
        if not period_reader.is_empty():
            start = period_reader.get(int, "start")
            end = period_reader.get(int, "end")
            market_open = time_from_timestamp(start, timezone)
            market_close = time_from_timestamp(end, timezone)

        return Success(
            AssetMetadata(
                short_name=meta_reader.get(str, "shortName"),
                long_name=meta_reader.get(str, "longName"),
                instrument=meta_reader.get(str, "instrumentType"),
                exchange=meta_reader.get(str, "exchangeName"),
                currency=meta_reader.get(str, "currency"),
                first_available_date=first_available_date,
                timezone=timezone,
                market_open=market_open,
                market_close=market_close,
            )
        )

    def _fetch_impl(self, url: str, params: dict[str, int | str]) -> Result[JsonObject]:
        """fetch the response from the provider. Is called from a _safe_call wrapper so can throw"""
        headers = {"User-Agent": "Mozilla/5.0"}
        response = self.session.get(url, params=params, headers=headers, timeout=self.config.timeout_delta().seconds)
        response.raise_for_status()
        reader = JsonReader(response.json()).reader_for("chart", allow_missing="yes")
        return self._parse_result(reader)

    def _is_aligned(self, ts: float, series: Series) -> bool:
        # Yahoo's last candle time often isn't aligned, it's the last data so far.
        # for daily series we made sure the candle is complete.
        if series.is_daily():
            return True
        seconds = int(series.interval_delta().total_seconds())
        return int(ts) % seconds == 0

    def _parse_result(self, reader: JsonReader) -> Result[JsonObject]:
        def fail(message: str):
            return Failure(reason="Could not interpret fetch response", error=message)

        try:
            if reader.is_empty():
                return fail("no 'chart' in response")
            error_object = reader.get_object("error", allow_missing="yes")
            if error_object:
                return fail(str(error_object))
            result = reader.get_object(["result", 0], allow_missing="no")
            return Success(result)

        except ParseError as ve:
            return fail(str(ve))
