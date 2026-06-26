# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/config/loader.py

import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

from finance.common.time_utils import parse_duration

from ..common.applogger import LOG_LEVELS
from ..common.introspection import here
from ..common.model import BACKEND, RESOLUTION, Asset, Provider, Result, Series, SeriesType, SupportedProviders
from ..common.paths import resolve_config_path


@dataclass
class EmptyConfig:
    pass


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

        # cannot fail, so not wrapped in result
        env = load_environment_config(raw_cfg.payload.get("environment", {}), self.project_root)
        biz_result = load_business_config(raw_cfg.payload.get("business", {}))
        if not biz_result.ok:
            return biz_result

        return Result.ok_payload(env | biz_result.payload | secrets.payload)

    # -----------------------------
    # Load secrets from .env
    # -----------------------------
    def load_env_secrets(self) -> Result[dict]:
        env_file_values = dotenv_values(self.env_path)
        # .env overrides environ
        merged = {**self.environ, **env_file_values}

        api_keys = {}
        # influx = {}
        timescaledb = {}

        for key, value in merged.items():
            if key.endswith("_API_KEY"):
                provider = key[:-8].lower()  # strip "_API_KEY"
                api_keys[provider] = value

            #            elif key.startswith("INFLUX_"):
            #                influx[key[7:].lower()] = value
            elif key.startswith(f"{BACKEND.upper()}_"):
                timescaledb[key[len(BACKEND) + 1 :].lower()] = value

        return Result.ok_payload({"secrets": {BACKEND: timescaledb, "api_keys": api_keys}})


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


def require(cfg: dict, key: str, context: str) -> str | dict:
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

    logging.basicConfig(level=py_level, format="%(message)s")


# ---------------------------------
# Normalize providers
# ---------------------------------


def check_duration(content, name, default):
    raw_duration = content.get(name, default)
    # validate that the duration is correct
    parse_duration(raw_duration, name)
    return raw_duration


def normalize_providers(raw_providers: dict) -> Result[dict[str, Provider]]:

    providers = {}
    for provider in SupportedProviders.values():
        content = raw_providers.get(provider, {})
        tz_name = content.get("timezone", "UTC")
        try:
            ZoneInfo(tz_name)
        except Exception:
            return Result.fail(f"Could not parse provider '{provider}'", f"Invalid timezone '{tz_name}'")

        try:
            output = Provider(
                name=provider,
                timezone=tz_name,
                daily_interval=check_duration(content, "daily_interval", "1d"),
                intraday_interval=check_duration(content, "intraday_interval", "10m"),
                daily_history_limit=check_duration(content, "daily_history_limit", "10y"),
                intraday_history_limit=check_duration(content, "intraday_history_limit", "5d"),
                daily_series_type=SeriesType.validate(content.get("daily_series_type", "candle")),
            )
        except ValueError as ve:
            return Result.fail(f"Could not parse provider '{provider}'", ve)

        providers[provider] = output

    return Result.ok_payload(providers)


# ---------------------------------
# Normalize field sets definitions
# ---------------------------------

"""
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
        if field not in PRICE and not Candle.contains(field):
            raise ValueError(f"Unknown field '{field}' in field set '{name}'")
"""


# -----------------------------
# Normalize asset definitions
# -----------------------------
def normalize_assets_and_series(
    raw_assets: dict, providers: dict[str, Provider]
) -> Result[tuple[dict[str, Asset], dict[str, Series]]]:
    """
    Expand YAML asset blocks with 'resolution' into asset and series definitions.

    Example:
      gold:
        provider: yahoo
        provider_code: GC=F
        symbol: GOLD
        tags: {...}
        resolution:
          intraday:
            interval: 10m
            history_limit: 5d

    """
    asset_dict = {}
    series_dict = {}
    try:
        for asset_name, cfg in raw_assets.items():
            provider = require(cfg, "provider", f"asset '{asset_name}'")

            provider_config: dict = asdict(providers.get(provider, EmptyConfig()))
            symbol = require(cfg, "symbol", f"asset '{asset_name}'")
            tags = {k.lower(): v for k, v in cfg.get("tags", {}).items()}

            asset = Asset.create(name=asset_name, symbol=symbol, config=cfg, tags=tags)
            asset_dict[asset_name] = asset

            resolution_config = require(cfg, RESOLUTION, f"asset '{asset_name}'")

            for resolution, resolution_def in resolution_config.items():
                # merge provider config with resolution definition to provide defaults
                series = Series.create(asset, resolution, (provider_config | resolution_def))
                series_dict[series.name] = series

        return Result.ok_payload((asset_dict, series_dict))

    except Exception as exc:  # by require()
        return Result.fail("Error parsing assets", exc)


# --------------------------------
# Normalize composite definitions
# --------------------------------


def normalize_composites(raw_composites: dict) -> Result[dict]:
    """
    Composite format is now:

      composites:
        SPREAD:
          expression: "spx_daily - ndx_daily"
          resolution: intraday  # optional, calculated if not specified
          symbol: SPREAD
          tags: {...}
    """

    composites = {}
    context = {"location": here()}

    try:
        for name, cfg in raw_composites.items():
            tags = {k.lower(): v for k, v in cfg.get("tags", {}).items()}
            symbol = require(cfg, "symbol", f"composite '{name}'")
            asset = Asset.create(name=name, symbol=symbol, config={"provider": "composite"}, tags=tags)
            if RESOLUTION in cfg:
                # validate the resolution by creating a series instance
                series = Series.create(asset, cfg[RESOLUTION], None)
                resolution = series.resolution
            else:
                resolution = None
            composites[name] = {
                "expression": require(cfg, "expression", f"composite '{name}'"),
                "asset": asset,
                "resolution": resolution,
            }

        return Result.ok_payload(composites)

    except ValueError as exc:
        return Result.fail("Error parsing composites", exc, meta=context)


def load_environment_config(env_cfg: dict, project_root: Path) -> dict:
    #    context = {"location": here()}

    apply_logging_config(env_cfg)

    paths_cfg = env_cfg.get("paths", {})

    paths = {
        "wal": resolve_config_path(paths_cfg.get("wal"), "wal.jsonl", project_root),
        "state": resolve_config_path(paths_cfg.get("state"), "state.json", project_root),
    }

    timescaledb_cfg = env_cfg.get(BACKEND, {})
    timescaledb_dict = {
        "max_batch_size": timescaledb_cfg.get("max_batch_size"),
        "max_batch_age": timescaledb_cfg.get("max_batch_age_seconds"),
    }

    # buckets = env_cfg.get("buckets", {})

    # allowed = {"daily", "intraday"}
    # invalid = set(buckets.keys()) - allowed
    # if invalid:
    #    return Result.fail(f"Invalid bucket keys: {sorted(invalid)}. Allowed keys: {sorted(allowed)}", meta=context)
    # missing = allowed - set(buckets.keys())
    # if missing:
    #    return Result.fail(f"Missing bucket definitions for: {sorted(missing)}", meta=context)

    return {"paths": paths, BACKEND: timescaledb_dict}


def load_business_config(biz_cfg: dict) -> Result[dict]:
    # raw_field_sets = biz_cfg.get("field_sets", {})

    # field_sets = normalize_field_sets(raw_field_sets)
    # if not field_sets.ok:
    #    return field_sets

    raw_providers = biz_cfg.get("providers", {})
    providers = normalize_providers(raw_providers)
    if not providers.ok:
        return providers

    raw_assets = biz_cfg.get("assets", {})

    # Normalize assets section into assets and series.
    result = normalize_assets_and_series(raw_assets, providers.payload)
    if not result.ok:
        return result
    assets, series = result.payload

    # validate composites
    raw_composites = biz_cfg.get("composites", {})

    composites = normalize_composites(raw_composites)
    if not composites.ok:
        return composites

    return Result.ok_payload(
        {"providers": providers.payload, "assets": assets, "series": series, "composites": composites.payload}
    )
