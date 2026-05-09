#!/usr/bin/env python3

import requests
import time
import json
import os
import ast

from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")

load_dotenv(ENV_PATH)

import datetime

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
        "default_interval": int(config["general"]["interval"])
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

            symbols[measurement] = {
                "symbol": symbol,
                "measurement": measurement.strip(),
                "interval": section_interval,
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
def write_influx(measurement, fields, timestamp, tags=None):
    tag_str = ""
    if tags:
        tag_str = "," + ",".join(f"{k}={v}" for k, v in tags.items())

    # fields is a dict, e.g. {"value": 5.12}
    field_str = ",".join(f"{k}={v}" for k, v in fields.items())
    line = f"{measurement}{tag_str} {field_str} {timestamp}"

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


def with_message(message):
    print(f"{message}")
    return None

# ------------------------------------------------------------
# Get a measurement and store it in Influx
# ------------------------------------------------------------
def process_metric(measurement, fetch_fn, max_age_minutes, state):
    now = int(time.time())

    # Initialize per-symbol state if missing
    if measurement not in state:
        state[measurement] = {
            "last_value": None,
            "last_timestamp": 0
        }

    s = state[measurement]
    # Freshness check before hitting the API
    if s.get("last_try") is not None:
        age = now - s["last_try"]
        if age < max_age_minutes * 60:
            return with_message(f"{measurement}: fresh ({age/60:.1f}m < {max_age_minutes}m) → skip fetch")
        
    # Fetch new value + timestamp
    value, ts = fetch_fn()
    s["last_try"] = now

    if value is None or ts is None:
        return with_message(f"{measurement}: fetch failed")
    
    save = False

    # If this metric has never been written before → accept immediately
    if s["last_value"] is None:
        print(f"{measurement}: first-time write ({value}/{ts})")
        save = True

    # New timestamp → write even if value unchanged
    elif ts != s["last_timestamp"]:
        print(f"{measurement}: new sample ({value}/{ts})")
        save = True

    if save:
        write_influx(measurement, {"value": value}, ts)
        s["last_value"] = value
        s["last_timestamp"] = ts
        return

    # Same timestamp → skip
    return with_message(f"{measurement}: unchanged")

def extract_dependencies(expr: str, candidates):
    """
    Return the set of variable names in `expr` that are also in `candidates`.
    Uses Python's AST, so no substring collisions.
    """
    print(f"candidates: {candidates}")
    tree = ast.parse(expr, mode="eval")
    names = set()

    class NameCollector(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name):
            names.add(node.id)

    NameCollector().visit(tree)
    return [name for name in names if name in candidates]

def evaluate_composites(composites, state, interval):
    """
    Evaluate derived measurements from the fetched data
    """
    computed = {}
    now = int(time.time())

    for measurement, expr in composites.items():
        try:
            entry = state.get(measurement, {})
            last_try = entry.get("last_try")

            # Freshness check BEFORE doing any work
            if last_try and now - last_try < interval:
                print(f"Composite {measurement}: fresh enough → skip evaluation")
                continue

            # Detect dependencies by scanning expression
            deps = extract_dependencies(expr, state.keys())
            print(f"Deps: {deps}")  
            values = {}
            timestamps = []

            for dep in deps:
                dep_state = state.get(dep)
                if not dep_state or dep_state["last_value"] is None:
                    raise Exception(f"missing dependency {dep}")

                values[dep] = dep_state["last_value"]
                timestamps.append(dep_state["last_timestamp"])

            print(f"values({measurement}): {values}")

            # Evaluate composite expression
            value = eval(expr, {}, values)

            # Composite timestamp = newest input timestamp
            ts = max(timestamps) if timestamps else now

            computed[measurement] = (value, ts)

        except Exception as e:
            print(f"Composite {measurement} failed: {e}")
            continue

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
            return None, None

        data = r.json()

        value = float(data["dataSets"][0]["series"]["0:0:0:0:0"]["observations"]["0"][0])
        timestampString = data["structure"]["dimensions"]["observation"][0]["values"][0]["start"]
        timestamp = int(datetime.datetime.fromisoformat(timestampString).timestamp())
        return value, timestamp

    except Exception:
        return None, None

def fetch_yahoo_chart(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1m"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()

        result = data["chart"]["result"][0]
        meta = result["meta"]

        price = meta.get("regularMarketPrice")
        ts = meta.get("regularMarketTime")
        prev_close = meta.get("chartPreviousClose")

        if price is not None:
            return float(price), ts

        # fallback if Yahoo gives no regularMarketPrice (rare)
        if prev_close is not None:
            return float(prev_close), ts

        return None, None

    except Exception as e:
        print(f"Error fetching Yahoo chart for {symbol}: {e}")
        return None, None

def fetch_fred_series(series_id):

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        obs = data["observations"][0]
        value = obs["value"]

        if value in ("", ".", None):
            print(f"FRED {series_id} returned no value")
            return None, None

        timestamp_string = obs["date"]
        timestamp = int(datetime.datetime.strptime(timestamp_string, "%Y-%m-%d").timestamp())
        return float(value), timestamp

    except Exception as e:
        print(f"FRED {series_id} fetch failed:", e)
        return None, None

def fetch_treasury(series_id):
    print("treasury not implemented yet")

FETCHERS = {
    "yahoo": lambda symbol: lambda: fetch_yahoo_chart(symbol),
    "fred": lambda series: lambda: fetch_fred_series(series),
    "ecb": lambda pair: lambda: fetch_ecb(pair),
    # "treasury": lambda series: lambda: fetch_treasury(series)
}

# -----------------------------
# MAIN
# -----------------------------
def main():

    symbol_config, general = load_symbol_config(config)
    default_interval = general["default_interval"]
    print("Fetching macro data...")
    state = load_state()

    for measurement, cfg in symbol_config.items():
        source = cfg["source"]
        symbol = cfg["symbol"]
        measurement = cfg["measurement"]
        interval = cfg["interval"]
        fetch_builder = FETCHERS.get(source)
        if fetch_builder is None:
            print(f"Skipping {source} metric {measurement} - no fetcher")
            continue

        process_metric(measurement, fetch_builder(symbol), interval, state)

    composites = load_composites(config)
    computed = evaluate_composites(composites, state, default_interval)

    for measurement, (value, ts) in computed.items():
        fetch_fn = lambda v=value, t=ts: (v, t)
        process_metric(measurement, fetch_fn, default_interval, state)

    save_state(state)
    print("Done.")

if __name__ == "__main__":
    main()
