# finance/fetch/ecb.py

import requests
import datetime

def fetch_ecb(symbol, api_keys={}):
    """
    symbol: e.g. 'USD_EUR'
    returns: float or 'use_last'
    """

    try:
        base, quote = symbol.split("_")
        series = f"EXR/D.{base}.{quote}.SP00.A"
        url = f"https://data-api.ecb.europa.eu/service/data/{series}?format=jsondata&lastNObservations=1&detail=dataonly"

        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return {"value": None, "timestamp": None}

        data = r.json()

        value = float(data["dataSets"][0]["series"]["0:0:0:0:0"]["observations"]["0"][0])
        timestampString = data["structure"]["dimensions"]["observation"][0]["values"][0]["start"]
        timestamp = int(datetime.datetime.fromisoformat(timestampString).timestamp())
        return {"value": value, "timestamp": timestamp}

    except Exception:
        return {"value": None, "timestamp": None}