# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/yahoo.py

import math
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

import requests

from ..common.model import FetchPoint, FetchResult, MeasurementResult
from .parser import parse_duration
from .provider import MarketDataProvider

SUPPORTED_FIELDS = ["open", "high", "low", "close", "volume"]


class YahooProvider(MarketDataProvider):
    """Unified Yahoo Finance data provider."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def fetch(self, name: str, asset: dict, last_timestamp: int | None = None) -> FetchResult:
        symbol = asset["symbol"]
        timeseries = asset["timeseries"]
        fields = asset["fields"]

        if timeseries == "intraday":
            return self._fetch_intraday(name, symbol, last_timestamp)
        else:
            # we don't have other options than "daily" now - enforced in config
            return self._fetch_daily(name, symbol, fields, last_timestamp)

    # ----------------------------------------------------------------------
    # Helper methods
    # ----------------------------------------------------------------------

    def _get_intraday_range(self, last_timestamp: int | None, history_limit_text: str) -> str:

        # Case 1: no history yet
        if last_timestamp is None:
            return history_limit_text

        # Case 2: gap larger than history limit
        history_limit_seconds = parse_duration(history_limit_text)
        now = int(self.now().timestamp())
        gap = now - last_timestamp
        if gap > history_limit_seconds:
            return history_limit_text

        # Case 3: request just the gap
        gap_minutes = math.ceil(gap / 60)
        return f"{gap_minutes}m"

    def _fetch_intraday(self, name: str, symbol: str, last_timestamp: int) -> FetchResult:
        """
        Fetch intraday prices for a symbol.
        Payload can contain multiple results in case last_timestamp is old (initial load).
        It can also contain an empty list if nothing was found or the call failed
        """

        fields = ["price"]
        mapped_field = "close"
        history_limit_text = self.config.get("intraday_history_limit", "5d")
        range_str = self._get_intraday_range(last_timestamp, history_limit_text)
        result = self._fetch(name=name, symbol=symbol, interval_str="1m", range_str=range_str)

        if not result.ok:
            # A failing MeasurementResult is semantically identical to a failing FetchResult
            return result

        candles = self._extract_candles(result, mapped_field)
        # if we don't have candles, fall back to meta data
        if not candles.ok or candles.payload == []:
            meta = result.payload.get("meta", {})
            return self._get_from_meta(name, fields, meta)
        else:
            # we do have candles. Pass back the close values.
            return FetchResult.ok_payload(
                name,
                [
                    FetchPoint(
                        timestamp=candle.timestamp,
                        fields={fields[0]: candle.fields[mapped_field]},
                    )
                    for candle in candles.payload
                ],
            )

    def _get_from_meta(self, name: str, fields: list[str], meta: dict) -> FetchResult:
        timestamp = meta.get("regularMarketTime")
        reason = "Cannot synthesize from metadata"
        # Only use fallback if timestamp exists
        if timestamp is None:
            return FetchResult.fail(name, reason, "timestamp missing")

        # Build synthetic fields
        synthetic = {}
        base_error = "Fallback failed: "
        warnings = []
        error = None
        # Candle subset mode
        for f in fields:
            if f in ("price", "close"):
                v = meta.get("regularMarketPrice")
            elif f == "high":
                v = meta.get("regularMarketDayHigh")
            elif f == "low":
                v = meta.get("regularMarketDayLow")
            elif f == "volume":
                v = meta.get("regularMarketVolume")
            elif f == "open":
                error = f"{base_error}cannot synthesize 'open' from metadata"
                continue
            else:
                error = f"{base_error}unknown field '{f}'"
                continue
            if v is None:
                warnings.append(f"{base_error}missing value for '{f}'")
                continue

            synthetic[f] = float(v)

        if error or not synthetic:
            return FetchResult.fail(name, reason, error, warnings)

        return FetchResult.ok_payload(name, [FetchPoint(fields=synthetic, timestamp=timestamp)], warnings)

    def _get_daily_range(self, missing_days: int | None, history_limit_text: str) -> str:

        #  we already know that missing days is positive here, so we can ignore the case of 0 or negative missing days

        # Case 1: initial load
        if missing_days is None:
            return history_limit_text

        history_limit_days = int(round(parse_duration(history_limit_text) / (24 * 3600) + 1e-12))
        if missing_days > history_limit_days:
            return history_limit_text

        return f"{missing_days}d"

    def _fetch_daily(self, name, symbol, fields, last_timestamp) -> FetchResult:
        """
        Fetch daily candles from Yahoo Finance.
        """
        now = self.now()
        today = now.date()
        missing_days = self._compute_missing_days(today, last_timestamp)
        if missing_days is not None and missing_days <= 0:
            return FetchResult.ok_payload(name, [])

        history_limit = self.config.get("daily_history_limit", "10y")
        range_str = self._get_daily_range(missing_days, history_limit)

        results = self._fetch(name, symbol, "1d", range_str)
        if not results.ok:
            return results
        return self._extract_candles(results, fields, today)

    def _fetch(self, name, symbol, interval_str, range_str) -> MeasurementResult[dict]:
        url = self._build_url(symbol, interval_str, range_str)
        return self._safe_call(measurement=name, fn=lambda: self._fetch_impl(url, name), context="fetch")

    def _fetch_impl(self, url, name) -> MeasurementResult[dict]:
        """fetch the response from the provider. Is called from a _safe_call wrapper so can throw"""
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
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

    def _compute_missing_days(self, today, last_timestamp) -> int | None:
        if last_timestamp is None:
            return None

        last_date = datetime.fromtimestamp(last_timestamp, tz=UTC).date()
        return (today - last_date).days

    def _build_url(self, symbol: str, interval_str, range_str: str) -> str:
        encoded_symbol = quote(symbol, safe="")

        params = {
            "interval": interval_str,
            "range": range_str,
            "includePrePost": "false",
            "events": "div,splits",
        }

        base = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        return f"{base}?{urlencode(params)}"

    def _extract_candles(
        self, results: MeasurementResult[dict], fields: list[str] | None = None, today=None
    ) -> FetchResult:

        name = results.measurement
        payload = results.payload

        if fields is None:
            selected_fields = SUPPORTED_FIELDS
        else:
            unknown = [f for f in fields if f not in SUPPORTED_FIELDS]
            if unknown:
                return FetchResult.fail(name, f"Unknown fields requested: {unknown}. Supported: {SUPPORTED_FIELDS}")
            selected_fields = fields

        timestamps = payload.get("timestamp")
        if not timestamps:
            return FetchResult.fail(name, "no timestamp in result")

        quote_result = self._safe_get(payload, ["indicators", "quote", 0])
        # empty quote list can happen, use meta instead then
        if not quote_result.ok:
            return FetchResult.fail(name, "unexpected quote structure", quote_result.reason)

        quote = quote_result.payload
        # create arrays for all the fields we need
        arrays = {f: quote.get(f) or [] for f in selected_fields}

        # for daily we might need to skip entries for days that haven't finished yet
        today_midnight_timestamp = (
            int(datetime(today.year, today.month, today.day, tzinfo=UTC).timestamp()) if today is not None else None
        )

        candles = []
        invalid_count = 0

        for i, ts in enumerate(timestamps):
            values = {}

            # Make a dict of the fields we need
            for field in selected_fields:
                arr = arrays[field]
                values[field] = arr[i] if i < len(arr) else None

            # Skip incomplete candles
            if any(value is None for value in values.values()):
                invalid_count += 1
                continue

            # Skip today's incomplete candles (only for daily, when today is set)
            if today_midnight_timestamp is not None and ts >= today_midnight_timestamp:
                continue

            candles.append(FetchPoint(fields=values, timestamp=ts))

        warnings = []

        if invalid_count:
            warnings.append(f"Skipped {invalid_count} invalid candles")

        return FetchResult.ok_payload(name, candles, warnings)


"""    def _map_fields(self, candle, fields):
        if set(fields).issubset(self.VALID_CANDLE_FIELDS):
            return {f: float(candle["fields"][f]) for f in fields}

        raise ValueError(
            "Yahoo provider only supports fields=['price'] or fields=['open','high','low','close','volume']"
        )
"""
