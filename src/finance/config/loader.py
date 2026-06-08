# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/config/loader.py

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ..common.applogger import LOG_LEVELS
from ..common.introspection import here
from ..common.model import Result
from ..common.paths import get_project_root, resolve_config_path


# -----------------------------
# Load secrets from .env
# -----------------------------
def load_env_secrets(env_path: Path) -> Result[dict]:
    load_dotenv(env_path, override=True)

    influx = {
        "url": os.getenv("INFLUX_URL"),
        "cert": os.getenv("INFLUX_SSL_CERT"),
        "ssl_verify": os.getenv("INFLUX_SSL_VERIFY"),
    }

    context = {"location": here()}
    if not influx["url"]:
        return Result.fail("InfluxDB requires URL in INFLUX_URL", meta=context)

    # if we have an org variable, we have Influx 2 so we need a token
    org = os.getenv("INFLUX_ORG")
    if org:
        # influxDB 2
        influx["org"] = org
        influx["write-token"] = os.getenv("INFLUX_WRITE_TOKEN") or os.getenv("INFLUX_TOKEN")
        influx["read-token"] = os.getenv("INFLUX_READ_TOKEN") or os.getenv("INFLUX_TOKEN")

        if not influx["write-token"]:
            message = "InfluxDB 2.x requires INFLUX_WRITE_TOKEN and INFLUX_READ_TOKEN, or INFLUX_TOKEN"
            return Result.fail(message, meta=context)
    else:
        # InfluxDB 1
        influx["db"] = os.getenv("INFLUX_DB")
        if not influx["db"]:
            return Result.fail("InfluxDB 1.x requires database name in INFLUX_DB", meta=context)
        influx["user"] = os.getenv("INFLUX_USER")
        influx["password"] = os.getenv("INFLUX_PASSWORD")

    return Result.ok_payload(
        {
            "secrets": {
                "influx": influx,
                "api_keys": {
                    "fred": os.getenv("FRED_API_KEY"),
                    "yahoo": os.getenv("YAHOO_API_KEY"),
                    "ecb": os.getenv("ECB_API_KEY"),
                    "treasury": os.getenv("TREASURY_API_KEY"),
                },
            },
        },
    )


# -----------------------------
# Load YAML config
# -----------------------------
def load_yaml_config(yaml_path: Path) -> Result[dict]:
    context = {"location": here()}
    if not yaml_path.exists():
        return Result.fail(f"Config file not found: {yaml_path}", meta=context)

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
            return Result.ok_payload(result)
    except yaml.YAMLError as exc:
        return Result.fail("Invalid YAML", str(exc), meta=context)


def require(cfg: dict, key: str, context: str) -> str:
    """
    Return cfg[key] if present, otherwise raise a ValueError.
    This has to be caught in the function it is used in.
    """
    if key not in cfg:
        raise ValueError(f"Missing required field '{key}' in {context}")
    return cfg[key]


def apply_logging_config(config: dict) -> None:

    level_name = config.get("logging", {}).get("level", "info").lower()

    py_level = LOG_LEVELS.get(level_name, logging.INFO)

    logging.basicConfig(
        level=py_level,
        format="%(message)s",
    )


# -----------------------------
# Normalize asset definitions
# -----------------------------
def normalize_assets(raw_assets: dict, field_sets: dict = None, buckets: dict = None) -> Result[dict]:
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
    context = {"location": here()}

    try:
        for asset_name, cfg in raw_assets.items():
            provider = require(cfg, "provider", f"asset '{asset_name}'")
            symbol = require(cfg, "symbol", f"asset '{asset_name}'")
            tags = {k.lower(): v for k, v in cfg.get("tags", {}).items()}

            timeseries_config = require(cfg, "timeseries", f"asset '{asset_name}'")

            for series_name, series_def in timeseries_config.items():
                if series_name not in ["intraday", "daily"]:
                    raise ValueError(f"Unknown timeseries name '{series_name}' in asset '{asset_name}'")
                metric_name = f"{asset_name}_{series_name}"

                if series_name == "intraday":
                    fields = ["price"]
                else:
                    # Resolve field set
                    fields = series_def.get("fields", ["price"])
                    if isinstance(fields, str):
                        if field_sets is None or fields not in field_sets:
                            raise ValueError(f"Unknown field set '{fields}' in asset '{asset_name}'")
                        fields = field_sets[fields]

                metrics[metric_name] = {
                    "name": metric_name,
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

        return Result.ok_payload(metrics)

    except ValueError as exc:  # by require()
        return Result.fail(str(exc), meta=context)


# -----------------------------
# Normalize composite definitions
# -----------------------------
def normalize_composites(raw_composites: dict, buckets: dict = None) -> Result[dict]:
    """
    Composite format is now:

      composites:
        SPREAD:
          expression: "spx_daily - ndx_daily"
          timeseries: intraday  # optional, calculated if not specified
          tags: {...}
    """

    composites = {}
    context = {"location": here()}

    try:
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

        return Result.ok_payload(composites)

    except ValueError as exc:
        return Result.fail(str(exc), meta=context)


def load_environment_config(env_cfg: dict) -> Result[dict]:
    context = {"location": here()}

    apply_logging_config(env_cfg)

    paths_cfg = env_cfg.get("paths", {})

    paths = {
        "wal": resolve_config_path(paths_cfg.get("wal"), "wal.jsonl"),
        "state": resolve_config_path(paths_cfg.get("state"), "state.json"),
    }

    buckets = env_cfg.get("buckets", {})

    allowed = {"daily", "intraday"}
    invalid = set(buckets.keys()) - allowed
    if invalid:
        return Result.fail(f"Invalid bucket keys: {sorted(invalid)}. Allowed keys: {sorted(allowed)}", meta=context)
    missing = allowed - set(buckets.keys())
    if missing:
        return Result.fail(f"Missing bucket definitions for: {sorted(missing)}", meta=context)

    return Result.ok_payload({"paths": paths, "buckets": buckets})


def load_business_config(biz_cfg: dict, buckets: dict) -> Result[dict]:
    field_sets = biz_cfg.get("field_sets", {})
    providers = biz_cfg.get("providers", {})
    raw_assets = biz_cfg.get("assets", {})
    raw_composites = biz_cfg.get("composites", {})

    # Normalize and validate assets/composites.
    assets = normalize_assets(raw_assets, field_sets, buckets)
    if not assets.ok:
        return assets

    # we cannot always flatten buckets in composites since we don't always know the timeseries upfront.
    composites = normalize_composites(raw_composites, buckets)
    if not composites.ok:
        return composites

    return Result.ok_payload({"providers": providers, "assets": assets.payload, "composites": composites.payload})


# -----------------------------
# Main config loader
# -----------------------------
def load_config(yaml_path: Path | None = None, env_path: Path | None = None) -> Result[dict]:

    root = get_project_root()
    yaml_path = yaml_path or (root / "config.yaml")
    env_path = env_path or (root / ".env")

    secrets = load_env_secrets(env_path)
    if not secrets.ok:
        return secrets
    raw_cfg = load_yaml_config(yaml_path)
    if not raw_cfg.ok:
        return raw_cfg
    env_result = load_environment_config(raw_cfg.payload.get("environment", {}))
    if not env_result.ok:
        return env_result
    biz_result = load_business_config(raw_cfg.payload.get("business", {}), env_result.payload["buckets"])
    if not biz_result.ok:
        return biz_result

    return Result.ok_payload(env_result.payload | biz_result.payload | secrets.payload)
