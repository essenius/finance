# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/config/loader.py

import os
from configparser import ConfigParser
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# -----------------------------
# Load secrets from .env
# -----------------------------
def load_env_secrets(env_path: Path):
    load_dotenv(env_path, override=True)

    return {
        "influx": {
            "url": os.getenv("INFLUX_URL"),
            "db": os.getenv("INFLUX_DB"),
            "user": os.getenv("INFLUX_USER"),
            "password": os.getenv("INFLUX_PASSWORD"),
            "cert": os.getenv("INFLUX_CERT"),
            "verify": os.getenv("INFLUX_VERIFY"),
        },
        "api_keys": {
            "fred": os.getenv("FRED_API_KEY"),
            "yahoo": os.getenv("YAHOO_API_KEY"),
            "ecb": os.getenv("ECB_API_KEY"),
            "treasury": os.getenv("TREASURY_API_KEY"),
        },
    }


# -----------------------------
# Parse symbol sections
# -----------------------------
def load_symbols(parser: ConfigParser, general: dict):
    symbols = {}

    for section in ("yahoo", "ecb", "fred", "treasury"):
        if section not in parser:
            continue

        raw_interval = parser[section].get("interval")  # this is in minutes in the config

        interval_seconds = int(general["default_interval"]) if raw_interval is None else int(raw_interval) * 60

        for measurement, provider_symbol in parser[section].items():
            if measurement == "interval":
                continue

            symbols[measurement] = {
                "symbol": provider_symbol.strip(),
                "measurement": measurement,
                "interval": interval_seconds,
                "source": section,
            }

    return symbols


# -----------------------------
# Parse composite expressions
# -----------------------------
def load_composites(parser: ConfigParser):
    composites = {}

    if "composites" in parser:
        for name, expr in parser["composites"].items():
            composites[name] = expr.strip()

    return composites


# -----------------------------
# Main config loader
# -----------------------------
def load_config(ini_path: Path = PROJECT_ROOT / "config.ini", env_path: Path = PROJECT_ROOT / ".env"):
    print(f"Loading config from {ini_path} and secrets from {env_path}")
    secrets = load_env_secrets(env_path)

    # Load config.ini
    parser = ConfigParser()
    parser.optionxform = str
    parser.read(ini_path)

    general = {
        "default_interval": int(parser["general"].get("interval", 1440)) * 60,  # convert minutes to seconds
    }

    # Parse symbols + composites
    symbols = load_symbols(parser, general)
    composites = load_composites(parser)

    return {
        "general": general,
        "symbols": symbols,
        "composites": composites,
        "secrets": secrets,
    }
