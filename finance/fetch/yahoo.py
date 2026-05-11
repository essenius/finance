# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/fetch/yahoo.py

import requests

def fetch_yahoo_chart(symbol, api_keys={}):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1m"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        print(f"Yahoo response for {symbol}: {data}")  

        result = data["chart"]["result"][0]
        meta = result["meta"]

        price = meta.get("regularMarketPrice")
        ts = meta.get("regularMarketTime")

        if price is not None and ts is not None:
            return {"value": float(price), "timestamp": ts}

        # fallback if Yahoo gives no regularMarketPrice (rare)

        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]

        if timestamps and closes:
            ts = timestamps[-1]
            price = closes[-1]
            return {"value": float(price), "timestamp": ts}

        return {"value": None, "timestamp": None}

    except Exception as e:
        print(f"Error fetching Yahoo chart for {symbol}: {e}")
        return {"value": None, "timestamp": None}
