# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/fetch/ecb.py

import datetime

import requests

BASE_URL = "https://data-api.ecb.europa.eu/service/data"


def fetch_ecb(symbol, api_keys=None):
    """
    symbol: e.g. 'USD_EUR'
    returns: float or 'use_last'
    """

    if api_keys is None:
        api_keys = {}
    try:
        base, quote = symbol.split("_")
        series = f"EXR/D.{base}.{quote}.SP00.A"
        url = f"{BASE_URL}/{series}?format=jsondata&lastNObservations=1&detail=dataonly"

        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return {"value": None, "timestamp": None}

        data = r.json()

        value = float(data["dataSets"][0]["series"]["0:0:0:0:0"]["observations"]["0"][0])
        timestamp_string = data["structure"]["dimensions"]["observation"][0]["values"][0]["start"]
        timestamp = int(datetime.datetime.fromisoformat(timestamp_string).timestamp())
        return {"value": value, "timestamp": timestamp}

    except Exception:
        return {"value": None, "timestamp": None}
