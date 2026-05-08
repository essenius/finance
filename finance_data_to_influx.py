#!/usr/bin/env python3

import requests
import time
import json
import os

from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")

load_dotenv(ENV_PATH)

from datetime import datetime, timedelta, timezone

# -----------------------------
# CONFIGURATION
# -----------------------------

import configparser

INFLUX_USER = os.getenv("INFLUX_USER")
INFLUX_PASS = os.getenv("INFLUX_PASS")
INFLUX_BASE = os.getenv("INFLUX_BASE").rstrip("/")
INFLUX_DB = os.getenv("INFLUX_DB")
INFLUX_URL = f"{INFLUX_BASE}/write?db={INFLUX_DB}&precision=s"

CA_CERT = os.getenv("CA_CERT")
FRED_API_KEY = os.getenv("FRED_API_KEY")

CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.ini")
config = configparser.ConfigParser(interpolation=None)
config.optionxform = str  # preserve case of keys
config.read(CONFIG_PATH)

STATE_FILE = config["general"]["state_file"]

def load_symbol_config(config):

    general = {
        "default_interval": int(config["general"]["interval"]),
        "default_decimals": int(config["general"]["decimals"]),
        "default_decimals_fx": int(config["general"]["decimals_fx"]),
    }
    symbols = {}

    for section in ("yahoo", "ecb", "fred", "treasury"):
        if section not in config:
            continue

        section_interval = int(config[section].get("interval", general["default_interval"]))

        for measurement, provider_symbol in config[section].items():
            if measurement == "interval":
                continue

            symbol = provider_symbol.strip()

            # FX detection
            if symbol.endswith("=X") or "/" in symbol:
                decimals = general["default_decimals_fx"]
            else:
                decimals = general["default_decimals"]

            symbols[measurement] = {
                "symbol": symbol,
                "measurement": measurement.strip(),
                "interval": section_interval,
                "decimals": decimals,
                "source": section
            }

    return symbols, general

def load_composites(config):
    if "composite" not in config:
        return {}

    composites = {}
    for name, expr in config["composite"].items():
        composites[name] = expr.strip()
    return composites

EPSILON = 0.005

# -----------------------------
# HELPERS
# -----------------------------

# ------------------------------------------------------------
# Write a measurement to Influx
# ------------------------------------------------------------
def write_influx(measurement, fields, tags=None):
    tag_str = ""
    if tags:
        tag_str = "," + ",".join(f"{k}={v}" for k, v in tags.items())

    field_str = ",".join(f"{k}={v}" for k, v in fields.items())
    line = f"{measurement}{tag_str} {field_str}"

    print(INFLUX_URL)
    r = requests.post(INFLUX_URL, auth=(INFLUX_USER, INFLUX_PASS), data=line, verify=CA_CERT)
    if r.status_code != 204:
        print("Influx write error:", r.text)

# ------------------------------------------------------------
# Load state from JSON (or initialize empty)
# ------------------------------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

# ------------------------------------------------------------
# Save state to JSON
# ------------------------------------------------------------
def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ------------------------------------------------------------
# Float comparison with tolerance
# ------------------------------------------------------------
def is_same(a, b):
    if a is None or b is None:
        return False
    return abs(a - b) < EPSILON

# ------------------------------------------------------------
# Get a measurement and store it in Influx
# ------------------------------------------------------------
def process_metric(measurement, fetch_fn, max_age_minutes):
    print(f"processing {measurement}")
    now = int(time.time())
    state = load_state()


    # Initialize per-symbol state if missing
    if measurement not in state:
        state[measurement] = {
            "last_value": None,
            "last_change_time": 0,
            "last_write_time": 0,
            "unchanged_count": 0
        }

    s = state[measurement]

    # Add missing key with safe default
    if "last_write_time" not in s:
        s["last_write_time"] = s["last_change_time"]

    # Freshness check based on last_write_time
    age = now - s["last_write_time"]
    if age < max_age_minutes * 60:
        print(f"{measurement}: fresh ({age/60}m < {max_age_minutes}m) → skip fetch")
        return s.get("last_value", "use_last")

    # Fetch new value
    print(f"{now}: Fetching {measurement}...")
    value = fetch_fn()

    # Hard failure → skip metric entirely
    if value is None:
        print(f"{measurement}: failed to read")
        save_state(state)
        return None

    # Soft failure → treat as unchanged
    if value == "use_last":
        value = s["last_value"]

    # Enforce interval
    if now - s["last_write_time"] < max_age_minutes * 60:
        print("{measurement} still fresh");
        save_state(state)
        return s.get("last_value", "use_last")

    # Compare with epsilon
    if is_same(value, s["last_value"]):
        s["unchanged_count"] += 1
    else:
        # Real change detected or first-ever → write immediately
        write_influx(measurement, {"value": value})
        s["last_value"] = value
        s["last_change_time"] = now
        s["last_write_time"] = now
        s["unchanged_count"] = 0
        print(f"{measurement}: updated to {value}")
        save_state(state)
        return value

    # No change detected → check closure condition
    time_since_change = now - s["last_change_time"]

    closed_threshold = max_age_minutes * 60 * 3;
    if time_since_change >= closed_threshold:
        # Market is effectively closed → skip write
        print(f"{measurement}: market closed")
        save_state(state)
        return s.get("last_value", "use_last")


    # Market is open → write unchanged value to maintain continuity
    write_influx(measurement, {"value": value})
    s["last_write_time"] = now
    print(f"{measurement}: same at {value}")
    save_state(state)
    return value

# ------------------------------------------------------------
# Evaluate derived measurements from the fetched data
# ------------------------------------------------------------

def evaluate_composites(composites, results):
    computed = {}

    for measurement, expr in composites.items():
        try:
            value = eval(expr, {}, results)
            computed[measurement] = value
        except Exception:
            computed[measurement] = "use_last"

    return computed

# -----------------------------
# FETCHERS
# -----------------------------

def fetch_ecb(symbol):
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
            return "use_last"

        data = r.json()

        try:
            value = float(
                data["dataSets"][0]["series"]["0:0:0:0:0"]["observations"]["0"][0]
            )
            return value
        except Exception:
            return "use_last"

    except Exception:
        return "use_last"

def fetch_yahoo_chart(symbol, decimals=2):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    print(f"URL: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()

        result = data["chart"]["result"][0]
        prices = result["indicators"]["quote"][0]["close"]

        for price in reversed(prices):
            if price is not None:
                print(f"Price for {symbol}: {price}")
                return round(float(price), decimals)

        return None

    except Exception as e:
        print(f"Error fetching Yahoo chart for {symbol}: {e}")
        return None

def fetch_fred_series(series_id):

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
        "observation_start": datetime.date.today().isoformat(),
        "observation_end": datetime.date.today().isoformat()
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        obs = data["observations"][0]
        value = obs["value"]

        if value in ("", ".", None):
            print(f"FRED {series_id} returned no value — using last known")
            return "use_last"

        return float(value)

    except Exception as e:
        print(f"FRED {series_id} fetch failed:", e)
        return "use_last"

def fetch_treasury():
    print("treasury not implemented yet")

# -----------------------------
# MAIN
# -----------------------------
def main():

    symbol_config, general = load_symbol_config(config)
    default_interval = general["default_interval"]
    print("Fetching macro data...")

    results = {}
    for measurement, cfg in symbol_config.items():
        symbol = cfg["symbol"]
        source = cfg["source"]
        measurement = cfg["measurement"]
        interval = cfg["interval"]
        decimals = cfg["decimals"]

        if source == "yahoo":
            fetch_fn = lambda s=symbol, d=decimals: fetch_yahoo_chart(s, d)
        elif source == "ecb":
            fetch_fn = lambda s=symbol: fetch_ecb(s)
        elif source == "fred":
            fetch_fn = lambda s=symbol: fetch_fred_series(s)
        elif source == "treasury":
            print(f"Skipping treasury metric {measurement}")
            continue
            # fetch_fn = lambda: fetch_treasury()
        else:
            continue

        results[measurement] = process_metric( measurement, fetch_fn, interval)

    print(f"Results: {results}")
    composites = load_composites(config)
    computed = evaluate_composites(composites, results)

    for measurement, value in computed.items():
        fetch_fn = lambda v=value: v
        process_metric(measurement, fetch_fn, default_interval)

    print("Done.")

if __name__ == "__main__":
    main()
