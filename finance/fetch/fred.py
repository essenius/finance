# finance/fetch/fred.py

import datetime
import requests

def fetch_fred_series(series_id, api_keys):

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_keys.get("fred"),
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        obs = data["observations"]
        if not obs:
            return {"value": None, "timestamp": None}
        
        value = obs[0]["value"]
        if value in ("", ".", None):
            print(f"FRED {series_id} returned no value")
            return {"value": None, "timestamp": None}

        timestamp = int(datetime.datetime.strptime(obs[0]["date"], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp())
        return {"value": float(value), "timestamp": timestamp}

    except Exception as e:
        print(f"FRED {series_id} fetch failed:", e)
        return {"value": None, "timestamp": None}