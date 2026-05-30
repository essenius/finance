# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/config/loader.py

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from finance.common.log_mixin import LOG_LEVELS, LogMixin
from finance.common.paths import get_project_root


class Logger(LogMixin):
    pass


logger = Logger()


# -----------------------------
# Load secrets from .env
# -----------------------------
def load_env_secrets(env_path: Path):
    load_dotenv(env_path, override=True)

    influx = {
        "url": os.getenv("INFLUX_URL"),
        "cert": os.getenv("INFLUX_SSL_CERT"),
        "ssl_verify": os.getenv("INFLUX_SSL_VERIFY"),
    }

    if not influx["url"]:
        raise RuntimeError("InfluxDB requires URL in INFLUX_URL")

    # if we have an org variable, we have Influx 2 so we need a token
    org = os.getenv("INFLUX_ORG")
    if org:
        # influxDB 2
        influx["org"] = org
        influx["token"] = os.getenv("INFLUX_WRITE_TOKEN") or os.getenv("INFLUX_TOKEN")

        if not influx["token"]:
            raise RuntimeError("InfluxDB 2.x requires INFLUX_WRITE_TOKEN or INFLUX_TOKEN")
    else:
        # InfluxDB 1
        influx["db"] = os.getenv("INFLUX_DB")
        if not influx["db"]:
            raise RuntimeError("InfluxDB 1.x requires database name in INFLUX_DB")
        influx["user"] = os.getenv("INFLUX_USER")
        influx["password"] = os.getenv("INFLUX_PASSWORD")

    return {
        "influx": influx,
        "api_keys": {
            "fred": os.getenv("FRED_API_KEY"),
            "yahoo": os.getenv("YAHOO_API_KEY"),
            "ecb": os.getenv("ECB_API_KEY"),
            "treasury": os.getenv("TREASURY_API_KEY"),
        },
    }


# -----------------------------
# Load YAML config
# -----------------------------
def load_yaml_config(yaml_path: Path):
    if not yaml_path.exists():
        raise FileNotFoundError(f"Config file not found: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def require(cfg: dict, key: str, context: str):
    """
    Return cfg[key] if present, otherwise raise a clear ValueError.
    """
    if key not in cfg:
        raise ValueError(f"Missing required field '{key}' in {context}")
    return cfg[key]


def apply_logging_config(config):

    level_name = config.get("logging", {}).get("level", "info").lower()

    LogMixin.min_level = LOG_LEVELS.get(level_name, LOG_LEVELS["info"])


# -----------------------------
# Normalize asset definitions
# -----------------------------
def normalize_assets(raw_assets: dict, field_sets: dict = None, buckets: dict = None):
    """
    Expand YAML asset blocks with 'timeseries' into flat metric definitions.

    Example:
      gold:
        provider: yahoo
        symbol: "GC=F"
        tags: {...}
        timeseries:
          intraday:
            interval: 10m

    Produces:
      gold_intraday: { ... }
    """

    metrics = {}

    for asset_name, cfg in raw_assets.items():
        provider = require(cfg, "provider", f"asset '{asset_name}'")
        symbol = require(cfg, "symbol", f"asset '{asset_name}'")
        tags = {k.lower(): v for k, v in cfg.get("tags", {}).items()}

        timeseries_config = require(cfg, "timeseries", f"asset '{asset_name}'")

        for series_name, series_def in timeseries_config.items():
            metric_name = f"{asset_name}_{series_name}"

            if (series_name == "intraday") or ("fields" not in series_def):
                fields = ["price"]
            else:
                # Resolve field set
                fields = series_def["fields"]
                if isinstance(fields, str):
                    if field_sets is None or fields not in field_sets:
                        raise ValueError(f"Unknown field set '{fields}' in asset '{asset_name}'")
                    fields = field_sets[fields]

            metrics[metric_name] = {
                "asset": asset_name,
                "timeseries": series_name,
                "fields": fields,
                "interval": require(series_def, "interval", f"timeseries '{series_name}' in asset '{asset_name}'"),
                # inherited from asset
                "provider": provider,
                "symbol": symbol,
                "tags": tags.copy(),
            }

            if buckets:
                bucket_name = require(buckets, series_name, "buckets")
                metrics[metric_name]["bucket"] = bucket_name

    return metrics


# -----------------------------
# Normalize composite definitions
# -----------------------------
def normalize_composites(raw_composites: dict, buckets: dict = None):
    """
    Composite format is now:

      composites:
        SPREAD:
          expression: "spx_daily - ndx_daily"
          timeseries: intraday  # optional, calculated if not specified
          tags: {...}
    """

    composites = {}

    for name, cfg in raw_composites.items():
        composites[name] = {
            "expression": require(cfg, "expression", f"composite '{name}'"),
            "tags": {k.lower(): v for k, v in cfg.get("tags", {}).items()},
        }

        if "timeseries" in cfg:
            composites[name]["timeseries"] = cfg["timeseries"]
            if buckets:
                bucket_name = require(buckets, cfg["timeseries"], "buckets")
                composites[name]["bucket"] = bucket_name

    return composites


# -----------------------------
# Main config loader
# -----------------------------
def load_config(yaml_path=None, env_path=None):

    root = get_project_root()
    yaml_path = yaml_path or (root / "config.yaml")
    env_path = env_path or (root / ".env")

    secrets = load_env_secrets(env_path)
    raw_cfg = load_yaml_config(yaml_path)

    apply_logging_config(raw_cfg)

    logger.debug(f"Loaded config from {yaml_path} and secrets from {env_path}")

    buckets = raw_cfg.get("buckets", {})
    field_sets = raw_cfg.get("field_sets", {})
    providers = raw_cfg.get("providers", {})
    raw_assets = raw_cfg.get("assets", {})
    raw_composites = raw_cfg.get("composites", {})

    # Normalize and validate assets/composites.
    assets = normalize_assets(raw_assets, field_sets, buckets)
    # we cannot always flatten buckets in composites since we don't always know the timeseries upfront.
    composites = normalize_composites(raw_composites, buckets)

    return {
        "buckets": buckets,
        "providers": providers,
        "assets": assets,
        "composites": composites,
        "secrets": secrets,
    }
