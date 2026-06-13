# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/config/loader.py

import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

from finance.common.time_utils import parse_duration

from ..common.applogger import LOG_LEVELS
from ..common.introspection import here
from ..common.model import Result
from ..common.paths import resolve_config_path


class ConfigLoader:
    def __init__(self, project_root: Path, environ=os.environ):
        self.project_root = project_root
        self.yaml_path = project_root / "config.yaml"
        self.env_path = project_root / ".env"
        self.environ = environ

    def load(self) -> Result[dict]:

        secrets = self.load_env_secrets()
        # can't fail so no need to check for that

        raw_cfg = load_yaml_config(self.yaml_path)
        if not raw_cfg.ok:
            return raw_cfg
        env_result = load_environment_config(raw_cfg.payload.get("environment", {}), self.project_root)
        if not env_result.ok:
            return env_result
        biz_result = load_business_config(raw_cfg.payload.get("business", {}), env_result.payload["buckets"])
        if not biz_result.ok:
            return biz_result

        return Result.ok_payload(env_result.payload | biz_result.payload | secrets.payload)

    # -----------------------------
    # Load secrets from .env
    # -----------------------------
    def load_env_secrets(self) -> Result[dict]:
        env_file_values = dotenv_values(self.env_path)
        # .env overrides environ
        merged = {**self.environ, **env_file_values}

        api_keys = {}
        influx = {}

        for key, value in merged.items():
            if key.endswith("_API_KEY"):
                provider = key[:-8].lower()  # strip "_API_KEY"
                api_keys[provider] = value

            elif key.startswith("INFLUX_"):
                influx[key[7:].lower()] = value

        return Result.ok_payload(
            {
                "secrets": {"influx": influx, "api_keys": api_keys},
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


# ---------------------------------
# Normalize providers
# ---------------------------------


PROVIDERS = ["ecb", "fred", "yahoo"]


def normalize_providers(raw_providers: dict) -> Result[dict]:

    providers = {}
    for provider in PROVIDERS:
        content = raw_providers.get(provider, {})
        output = {}
        tz_name = content.get("timezone", "UTC")
        try:
            ZoneInfo(tz_name)
        except Exception:
            return Result.fail(f"Invalid timezone '{tz_name}' for provider '{provider}'")
        output["timezone"] = tz_name
        output["daily_history_limit"] = content.get("daily_history_limit", "10y")
        output["intraday_history_limit"] = content.get("intraday_history_limit", "5d")
        providers[provider] = output
    return Result.ok_payload(providers)


# ---------------------------------
# Normalize field sets definitions
# ---------------------------------

CANDLE = ["open", "high", "low", "close", "volume"]
PRICE = ["price"]


def normalize_field_sets(raw_field_sets: dict | None) -> Result[dict]:
    try:
        field_sets = dict(raw_field_sets or {})
        if field_sets.get("candle") is not None:
            raise ValueError("Cannot redefine field set 'candle'")
        if field_sets.get("price") is not None:
            raise ValueError("Cannot redefine field set 'price'")
        for name, field_set in field_sets.items():
            check_field_set(field_set, name)
        field_sets["candle"] = CANDLE
        field_sets["price"] = PRICE
        return Result.ok_payload(field_sets)
    except ValueError as exc:
        return Result.fail(str(exc))


def check_field_set(field_set: list[str], name: str):
    for field in field_set:
        if field not in PRICE and field not in CANDLE:
            raise ValueError(f"Unknown field '{field}' in field set '{name}'")


# -----------------------------
# Normalize asset definitions
# -----------------------------
def normalize_assets(raw_assets: dict, field_sets: dict, buckets: dict, providers: dict) -> Result[dict]:
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
            history_limit: 5d

    Produces:
      gold_intraday: { ... }
    """

    metrics = {}
    try:
        for asset_name, cfg in raw_assets.items():
            provider = require(cfg, "provider", f"asset '{asset_name}'")

            provider_config = providers.get(provider, {})
            symbol = require(cfg, "symbol", f"asset '{asset_name}'")
            tags = {k.lower(): v for k, v in cfg.get("tags", {}).items()}

            timeseries_config = require(cfg, "timeseries", f"asset '{asset_name}'")

            for series_name, series_def in timeseries_config.items():
                if series_name not in ["intraday", "daily"]:
                    raise ValueError(f"Unknown timeseries name '{series_name}' in asset '{asset_name}'")
                metric_name = f"{asset_name}_{series_name}"
                fields = get_fields(series_def.get("fields"), series_name, field_sets, asset_name)

                history_limit = series_def.get("history_limit")
                if not history_limit:
                    history_limit = provider_config.get(f"{series_name}_history_limit")

                interval = require(series_def, "interval", f"timeseries '{series_name}' in asset '{asset_name}'")
                metrics[metric_name] = {
                    "name": metric_name,
                    "asset": asset_name,
                    "timeseries": series_name,
                    "fields": fields,
                    "interval": interval,
                    "interval_seconds": parse_duration(interval, f"interval for {metric_name}"),
                    "history_limit": history_limit,
                    "history_limit_seconds": parse_duration(history_limit, f"history_limit for {metric_name}"),
                    "provider": provider,
                    "symbol": symbol,
                    "tags": tags.copy(),
                }

                if buckets:
                    bucket_name = require(buckets, series_name, "buckets")
                    metrics[metric_name]["bucket"] = bucket_name

        return Result.ok_payload(metrics)

    except ValueError as exc:  # by require()
        return Result.fail(str(exc))


def get_fields(fields: list[str] | str | None, timeseries: str, field_sets: dict | None, asset_name: str) -> list[str]:
    if timeseries == "intraday":
        if fields is not None:
            raise ValueError(
                f"Cannot redefine field set for intraday timeseries (is always 'price') in asset '{asset_name}'"
            )
        return PRICE
    if isinstance(fields, list):
        check_field_set(fields, f"in {asset_name}")
        return fields

    key = fields or "candle"
    if field_sets is None or key not in field_sets:
        raise ValueError(f"Unknown field set '{key}' in asset '{asset_name}'")
    return field_sets[key]


# --------------------------------
# Normalize composite definitions
# --------------------------------


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


def load_environment_config(env_cfg: dict, project_root: Path) -> Result[dict]:
    context = {"location": here()}

    apply_logging_config(env_cfg)

    paths_cfg = env_cfg.get("paths", {})

    paths = {
        "wal": resolve_config_path(paths_cfg.get("wal"), "wal.jsonl", project_root),
        "state": resolve_config_path(paths_cfg.get("state"), "state.json", project_root),
    }

    influx_cfg = env_cfg.get("influx", {})
    flush_cfg = influx_cfg.get("flush", {})
    influx_dict = {
        "max_batch_size": flush_cfg.get("max_batch_size"),
        "max_batch_age": flush_cfg.get("max_batch_age_seconds"),
    }

    buckets = env_cfg.get("buckets", {})

    allowed = {"daily", "intraday"}
    invalid = set(buckets.keys()) - allowed
    if invalid:
        return Result.fail(f"Invalid bucket keys: {sorted(invalid)}. Allowed keys: {sorted(allowed)}", meta=context)
    missing = allowed - set(buckets.keys())
    if missing:
        return Result.fail(f"Missing bucket definitions for: {sorted(missing)}", meta=context)

    return Result.ok_payload({"paths": paths, "buckets": buckets, "influx": influx_dict})


def load_business_config(biz_cfg: dict, buckets: dict) -> Result[dict]:
    raw_field_sets = biz_cfg.get("field_sets", {})

    field_sets = normalize_field_sets(raw_field_sets)
    if not field_sets.ok:
        return field_sets

    raw_providers = biz_cfg.get("providers", {})
    providers = normalize_providers(raw_providers)
    if not providers.ok:
        return providers

    raw_assets = biz_cfg.get("assets", {})

    # Normalize and validate assets/composites.
    assets = normalize_assets(raw_assets, field_sets.payload, buckets, providers.payload)
    if not assets.ok:
        return assets

    raw_composites = biz_cfg.get("composites", {})

    # we cannot always flatten buckets in composites since we don't always know the timeseries upfront.
    composites = normalize_composites(raw_composites, buckets)
    if not composites.ok:
        return composites

    return Result.ok_payload(
        {"providers": providers.payload, "assets": assets.payload, "composites": composites.payload}
    )
