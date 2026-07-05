# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/config/loader.py

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

from finance.common.time_utils import check_duration_in

from ..common.applogger import LOG_LEVELS
from ..common.introspection import here
from ..common.model import BACKEND, Asset, ProviderConfig, Result, Retention, Series, SeriesType, SupportedProviders
from ..common.paths import resolve_config_path


@dataclass
class EmptyConfig:
    pass


class ConfigLoader:
    def __init__(self, *, cwd: Path, config_path: Path | None = None, environ=os.environ):
        self.cwd = cwd
        self.env_path = (cwd / ".env").resolve()
        self.environ = environ
        self.config_path = config_path

    def load(self) -> Result[dict]:

        env_vars = self.load_env_variables().payload
        # can't fail so no need to check for that

        cfg_path = self.config_path
        if not cfg_path and env_vars.get("config") is not None:
            cfg_path = env_vars["config"]
        if not cfg_path:
            cfg_path = "config.yaml"

        yaml_path = cfg_path if Path(cfg_path).is_absolute() else (self.cwd / cfg_path).resolve()
        raw_cfg = load_yaml_config(yaml_path)
        if not raw_cfg.ok:
            return raw_cfg

        # cannot fail, so not wrapped in result
        env = load_environment_config(raw_cfg.payload.get("environment", {}), self.cwd)
        biz_result = load_business_config(raw_cfg.payload.get("business", {}))
        if not biz_result.ok:
            return biz_result

        return Result.ok_payload(env | biz_result.payload | env_vars)

    # -----------------------------
    # Load secrets from .env
    # -----------------------------

    def load_env_variables(self) -> Result[dict]:
        env_file_values = dotenv_values(self.env_path)
        # .env overrides environ
        merged = {**self.environ, **env_file_values}

        api_keys = {}
        # influx = {}
        timescaledb = {}
        config = None

        for key, value in merged.items():
            if key.endswith("_API_KEY"):
                provider = key[:-8].lower()  # strip "_API_KEY"
                api_keys[provider] = value

            #            elif key.startswith("INFLUX_"):
            #                influx[key[7:].lower()] = value
            elif key.startswith(f"{BACKEND.upper()}_"):
                timescaledb[key[len(BACKEND) + 1 :].lower()] = value
            elif key == "FINANCE_CONFIG":
                config = value

        return Result.ok_payload({"secrets": {BACKEND: timescaledb, "api_keys": api_keys}, "config": config})


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
        raise ValueError(f"Missing required field '{key}'")
    return cfg[key]


def apply_logging_config(config: dict) -> None:

    level_name = config.get("logging", {}).get("level", "info").lower()

    py_level = LOG_LEVELS.get(level_name, logging.INFO)

    logging.basicConfig(level=py_level, format="%(message)s")


# ---------------------------------
# Normalize providers
# ---------------------------------


def normalize_providers(raw_providers: dict) -> Result[dict[str, ProviderConfig]]:

    def fail(error):
        return Result.fail(f"Could not parse provider '{provider}'", error)

    providers: dict[str, ProviderConfig] = {}
    for provider in SupportedProviders.values():
        content = raw_providers.get(provider, {})
        content["name"] = provider
        tz_name = content.get("timezone", "UTC")
        try:
            ZoneInfo(tz_name)
        except Exception:
            return fail(f"Invalid timezone '{tz_name}'")

        try:
            config = ProviderConfig.create(content)
        except ValueError as ve:
            return fail(ve)

        providers[provider] = config

    return Result.ok_payload(providers)


# ---------------------------------
# Normalize series templates
# ---------------------------------


def check_template(name: str, input: dict) -> None:
    """Check the values early so of there are errors, it's clear where they are
    (i.e. in the template and not in the asset definition)
    """
    require(input, "interval", f"template '{name}'")
    check_duration_in(input, "interval")
    check_duration_in(input, "bootstrap_history")
    series_type = input.get("series_type")
    if series_type is not None:
        SeriesType.validate(series_type)
    retention = input.get("retention")
    if retention is not None:
        Retention.validate(retention)


def check_series_templates(raw_templates: dict | None) -> Result[dict[str, dict]]:
    if raw_templates is None:
        return Result.ok_payload({})
    for name, template in raw_templates.items():
        try:
            check_template(name, template)
        except ValueError as exc:
            return Result.fail(f"Could not parse series template '{name}'", str(exc))
    return Result.ok_payload(raw_templates)


# -----------------------------
# Normalize asset definitions
# -----------------------------


def normalize_assets_and_series(
    raw_assets: dict, series_template: dict[str, dict]
) -> Result[tuple[list[Asset], list[Series]]]:
    asset_list = []
    series_list = []

    def asset_parse_error(asset_name: str, error: str) -> Result[int]:
        return Result.fail(f"Could not parse asset '{asset_name}'", error)

    for asset_name, cfg in raw_assets.items():
        try:
            provider_section = require(cfg, "provider", f"asset '{asset_name}'")
            if not isinstance(provider_section, dict):
                return asset_parse_error(asset_name, "malformed provider section.")

            context = f"asset '{asset_name}' provider"
            require(provider_section, "name", context)
            require(provider_section, "code", context)

            tags = {k.lower(): v for k, v in cfg.get("tags", {}).items()}
            asset = Asset.create(name=asset_name, config=cfg, tags=tags)
            asset_list.append(asset)

            series_config = require(cfg, "series", context)

            for code, series_def in series_config.items():
                if isinstance(series_def, str):
                    template = series_template.get(series_def)
                    if not template:
                        return asset_parse_error(asset_name, f"Could not find series template '{series_def}'")
                    config = template
                else:
                    config = series_def
                require(config, "interval", context)
                series = Series.create(asset=asset, code=code, config=config)
                series_list.append(series)

        except Exception as exc:  # by require()
            return asset_parse_error(asset_name, exc)

    return Result.ok_payload((asset_list, series_list))


# --------------------------------
# Normalize composite definitions
# --------------------------------

'''
TODO re-introduce in v2
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
'''


def load_environment_config(env_cfg: dict, project_root: Path) -> dict:
    #    context = {"location": here()}

    apply_logging_config(env_cfg)

    paths_cfg = env_cfg.get("paths", {})
    paths = {key: resolve_config_path(value, key, project_root) for key, value in paths_cfg.items()}
    timescaledb_cfg = env_cfg.get(BACKEND, {})
    return {"paths": paths, BACKEND: timescaledb_cfg}


def load_business_config(biz_cfg: dict) -> Result[dict]:

    raw_providers = biz_cfg.get("providers", {})
    providers = normalize_providers(raw_providers)
    if not providers.ok:
        return providers

    raw_series_templates = biz_cfg.get("series_templates")

    template_result = check_series_templates(raw_series_templates)
    if not template_result.ok:
        return template_result
    series_templates = template_result.payload
    raw_assets = biz_cfg.get("assets", {})

    # Normalize assets section into assets and series.
    result = normalize_assets_and_series(raw_assets, series_templates)
    if not result.ok:
        return result
    assets, series = result.payload

    # validate composites
    """
    raw_composites = biz_cfg.get("composites", {})

    #composites = normalize_composites(raw_composites)
    if not composites.ok:
        return composites
    """

    return Result.ok_payload(
        {"providers": providers.payload, "assets": assets, "series": series}  # , "composites": composites.payload}
    )
