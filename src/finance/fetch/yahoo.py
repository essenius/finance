# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/fetch/yahoo.py

from datetime import UTC, datetime
from urllib.parse import quote, urlencode

import requests

from .model import Candle
from .parser import parse_duration
from .provider import MarketDataProvider


class CandleSeries:
    def __init__(self, timestamps, opens, highs, lows, closes, volumes):
        self.timestamps = timestamps
        self.opens = opens
        self.highs = highs
        self.lows = lows
        self.closes = closes
        self.volumes = volumes

    def __iter__(self):
        for ts, open, high, low, close, volume in zip(
            self.timestamps,
            self.opens,
            self.highs,
            self.lows,
            self.closes,
            self.volumes,
            strict=False,
        ):
            yield Candle(ts, open, high, low, close, volume)


class YahooProvider(MarketDataProvider):
    """Unified Yahoo Finance data provider."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    VALID_CANDLE_FIELDS = {"open", "high", "low", "close", "volume"}

    def fetch(self, asset, last_timestamp=None):
        symbol = asset["symbol"]
        timeseries = asset["timeseries"]
        fields = asset["fields"]

        if timeseries == "intraday":
            return self._fetch_intraday(symbol, fields, last_timestamp)
        elif timeseries == "daily":
            return self._fetch_daily(symbol, fields, last_timestamp)
        else:
            raise ValueError(f"Cannot handle timeseries '{timeseries}'")

    # ----------------------------------------------------------------------
    # Helper methods
    # ----------------------------------------------------------------------

    def _get_intraday_range(self, last_timestamp: int | None, history_limit_text: str) -> str:

        # Case 1: initial load
        if last_timestamp is None:
            return history_limit_text

        # Case 2: gap larger than history limit
        history_limit_seconds = parse_duration(history_limit_text)
        now_timestamp = int(self.now().timestamp())
        if now_timestamp - last_timestamp > history_limit_seconds:
            return history_limit_text

        # Case 3: incremental update (ask one minute)
        return "1m"

    def _fetch_intraday(self, symbol, fields, last_timestamp):
        """
        Fetch intraday prices for a symbol. Always returns a list,
        can contain multiple results in case last_timestamp is old (initial load).
        Can return empty list if nothing was found or the call failed
        Returns:
        [
            {
                "timestamp": <unix_seconds>,
                "fields": {
                    fields[0]: <value>,
                }
            }
        ]
        """

        history_limit_text = self.config.get("intraday_history_limit", "5d")
        range_str = self._get_intraday_range(last_timestamp, history_limit_text)
        results = self._fetch(symbol=symbol, interval_str="1m", range_str=range_str)
        return_value = []

        if results is None:
            return return_value

        candles = self._extract_candles(results, symbol)
        # if we don't have candles, fall back to meta data
        if candles == []:
            meta = results.get("meta", {})
            return self._get_from_meta(fields, meta, symbol)
        else:
            # we do have candles. Pass back the close values.
            for candle in candles:
                mapped = self._map_fields(candle, fields)
                return_value.append({"timestamp": candle["timestamp"], "fields": mapped})

        return return_value

    def _get_from_meta(self, fields, meta, symbol=None):
        timestamp = meta.get("regularMarketTime")

        # Only fallback if timestamp exists
        if timestamp is None:
            self.error("timestamp missing in metadata", symbol)
            return []

        # Build synthetic fields
        synthetic = {}
        fatal_config_error = False
        base_error = "Fallback failed: "

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
                self.error(f"{base_error}cannot synthesize 'open' from metadata", symbol)
                fatal_config_error = True
                continue
            else:
                self.error(f"{base_error}unknown field '{f}'", symbol)
                fatal_config_error = True
                continue
            if v is None:
                self.error(f"{base_error}metadata missing value for '{f}'", symbol)
                continue

            synthetic[f] = float(v)

        # If config error or nothing found → return empty list
        if fatal_config_error or not synthetic:
            return []

        return [{"timestamp": timestamp, "fields": synthetic}]

    def _get_daily_range(self, missing_days: int | None, history_limit_text: str) -> bool:

        #  we already know that missing days is positive here, so we can ignore the case of 0 or negative missing days

        # Case 1: initial load
        if missing_days is None:
            return history_limit_text

        history_limit_days = int(round(parse_duration(history_limit_text) / (24 * 3600) + 1e-12))
        if missing_days > history_limit_days:
            return history_limit_text

        return f"{missing_days}d"

    def _fetch_daily(self, symbol, fields, last_timestamp):
        """
        Fetch daily candles from Yahoo Finance.
        [
            {
                "timestamp": <unix_seconds>,
                "fields": {
                    <field>: <value>,
                    ...
                }
            }
            ...
        ]
        """
        now = self.now()
        today = now.date()
        missing_days = self._compute_missing_days(today, last_timestamp)
        if missing_days is not None and missing_days <= 0:
            return []

        history_limit = self.config.get("daily_history_limit", "10y")
        range_str = self._get_daily_range(missing_days, history_limit)

        results = self._fetch(symbol, "1d", range_str)
        if results is None:
            return []
        candles = self._extract_candles(results, symbol, today)

        return [{"timestamp": c["timestamp"], "fields": self._map_fields(c, fields)} for c in candles]

    def _fetch(self, symbol, interval_str, range_str):
        url = self._build_url(symbol, interval_str, range_str)
        return self._safe(symbol, lambda: self._fetch_impl(url, symbol))

    def _fetch_impl(self, url, symbol):
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if self._is_error_response(data, symbol):
            return []

        # must work since is_error_response checks for it
        value = data["chart"]["result"][0]
        return value

    def _is_error_response(self, data, symbol):
        chart = data.get("chart", {})
        if chart == {}:
            self.error("no 'chart' in response", symbol)
            return True
        if chart.get("error"):
            self.error(chart["error"], symbol)
            return True
        result = chart.get("result")
        result_empty = result is None or result == []
        if result_empty:
            self.error("result empty", symbol)
        return result_empty

    def _compute_missing_days(self, today, last_timestamp):
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

    def _extract_candles(self, results, symbol, today=None):

        timestamps = results.get("timestamp") or []
        if not timestamps:
            self.error("no timestamp in result", symbol)
            return []

        quote, err = self._safe_get(results, ["indicators", "quote", 0])
        if err:
            self.error(f"{err} in path for quote list", symbol)
            return []

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        today_midnight_timestamp = (
            int(datetime(today.year, today.month, today.day, tzinfo=UTC).timestamp()) if today is not None else None
        )

        candles = []

        series = CandleSeries(timestamps, opens, highs, lows, closes, volumes)

        for candle in series:
            if not candle.is_valid():
                self.error(f"invalid candle: {candle.to_dict()}", symbol)
                continue

            if today_midnight_timestamp is not None and candle.timestamp >= today_midnight_timestamp:
                continue

            candles.append(candle.to_dict())

        return candles

    def _map_fields(self, candle, fields):
        if fields == ["price"]:
            return {"price": float(candle["fields"]["close"])}

        # Candle subset mode
        if set(fields).issubset(self.VALID_CANDLE_FIELDS):
            return {f: float(candle["fields"][f]) for f in fields}

        raise ValueError(
            "Yahoo provider only supports fields=['price'] or fields=['open','high','low','close','volume']"
        )
