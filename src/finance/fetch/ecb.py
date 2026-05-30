# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/ecb.py

from datetime import datetime

import requests

from finance.fetch.provider import MarketDataProvider

BASE_URL = "https://data-api.ecb.europa.eu/service/data"


class EcbProvider(MarketDataProvider):
    """ECB daily FX provider (no intraday)."""

    def fetch(self, asset, last_timestamp):
        symbol = asset["symbol"]
        field = asset["fields"][0]
        return self._safe(symbol, lambda: self._fetch(symbol, field))

    def _fetch(self, symbol, field):
        """
        symbol: e.g. 'USD_EUR'
        returns: [{"timestamp": int, "fields": {field: float}}] or []
        """

        base, quote = symbol.split("_")
        series = f"EXR/D.{base}.{quote}.SP00.A"
        url = f"{BASE_URL}/{series}?format=jsondata&lastNObservations=1&detail=dataonly"

        response = requests.get(url, timeout=10)

        if not self._check_status(symbol, response):
            return []

        data = response.json()

        value, err = self._safe_get(data, ["dataSets", 0, "series", "0:0:0:0:0", "observations", "0", 0])

        if err:
            self.error(f"{err} in path for {field}", symbol)
            return []

        timestamp_string, err = self._safe_get(
            data, ["structure", "dimensions", "observation", 0, "values", 0, "start"]
        )

        if err:
            self.error(f"{err} in path for timestamp", symbol)
            return []

        timestamp = int(datetime.fromisoformat(timestamp_string).timestamp())

        return [{"timestamp": timestamp, "fields": {field: value}}]
