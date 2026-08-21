# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/config/loader.py

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

from ..common.configuration import ProviderConfig
from ..common.dict_utils import deep_merge
from ..common.guards import require_key
from ..common.introspection import here
from ..common.model import BACKEND, Asset, Series
from ..common.paths import resolve_config_path
from ..common.result import Failure, Result, Success
from ..common.string_enums import Retention, SeriesType, SupportedProviders
from ..common.time_utils import validate_duration


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

        env_vars = self.load_env_variables().payload  # always Success, so no test needed

        cfg_path = self.config_path
        if not cfg_path and env_vars.get("config") is not None:
            cfg_path = env_vars["config"]
        if not cfg_path:
            cfg_path = "config.yaml"

        cfg_path = Path(cfg_path)
        yaml_path = cfg_path if cfg_path.is_absolute() else (self.cwd / cfg_path).resolve()
        raw_cfg = load_yaml_config(yaml_path)
        if raw_cfg.ok is False:
            return raw_cfg

        # cannot fail, so not wrapped in result
        env = load_environment_config(raw_cfg.payload.get("environment", {}), self.cwd)
        biz_result = load_business_config(raw_cfg.payload.get("business", {}))
        if biz_result.ok is False:
            return biz_result

        return Success(env | biz_result.payload | env_vars)

    # -----------------------------
    # Load secrets from .env
    # -----------------------------

    def load_env_variables(self) -> Success[dict]:
        env_file_values = dotenv_values(self.env_path)
        # .env overrides environ
        merged = {**self.environ, **env_file_values}

        api_keys = {}
        timescaledb = {}
        config = None

        for key, value in merged.items():
            if key.endswith("_API_KEY"):
                provider = key[:-8].lower()  # strip "_API_KEY"
                api_keys[provider] = value
            elif key.startswith(f"{BACKEND.upper()}_"):
                timescaledb[key[len(BACKEND) + 1 :].lower()] = value
            elif key == "FINANCE_CONFIG":
                config = value

        return Success({"secrets": {BACKEND: timescaledb, "api_keys": api_keys}, "config": config})


# -----------------------------
# Load YAML config
# -----------------------------


def load_yaml_config(yaml_path: Path) -> Result[dict]:
    context = {"location": here()}
    if not yaml_path.exists():
        return Failure(reason=f"Config file not found: {yaml_path}", meta=context)

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
            return Success(result)
    except yaml.YAMLError as exc:
        return Failure(reason="Invalid YAML", error=exc, meta=context)


# ---------------------------------
# Normalize providers
# ---------------------------------


def normalize_providers(raw_providers: dict) -> Result[dict[str, ProviderConfig]]:

    def fail(error):
        return Failure(reason=f"Could not parse provider '{provider}'", error=error)

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

    return Success(providers)


# ---------------------------------
# Normalize series templates
# ---------------------------------


def check_template(name: str, input: dict) -> None:
    """Check the values early so of there are errors, it's clear where they are
    (i.e. in the template and not in the asset definition)
    """
    validate_duration(input.get("interval"), "interval")
    validate_duration(input.get("bootstrap_history"), "bootstrap history")
    series_type = input.get("series_type")
    if series_type is not None:
        SeriesType.require(series_type)
    retention = input.get("retention")
    if retention is not None:
        Retention.require(retention)
    validate_duration(input.get("publication_offset"), "publication offset")


def check_series_templates(raw_templates: dict | None) -> Result[dict[str, dict]]:
    if raw_templates is None:
        return Success({})
    for name, template in raw_templates.items():
        try:
            check_template(name, template)
        except ValueError as exc:
            return Failure(reason=f"Could not parse series template '{name}'", error=exc)
    return Success(raw_templates)


# -----------------------------
# Normalize asset definitions
# -----------------------------


def _parse_metadata(
    meta: dict | list | str | None, metadata_template: dict[str, dict], config: dict[str, dict]
) -> dict:
    if meta is None:
        return config
    if isinstance(meta, dict):
        config |= dict(meta)
        return config

    template_list = meta if isinstance(meta, list) else [meta]
    for name in template_list:
        template = metadata_template.get(name)
        if template is None:
            raise ValueError(f"Could not find metadata template '{name}'")
        config = deep_merge(config, template)
    return config


def normalize_assets_and_series(
    raw_assets: dict, metadata_template: dict[str, dict]
) -> Result[tuple[list[Asset], list[Series]]]:
    asset_list = []
    series_list = []

    for asset_name, cfg in raw_assets.items():
        try:
            provider_section = require_key(cfg, "provider", f"asset '{asset_name}'")
            if not isinstance(provider_section, dict):
                raise ValueError("malformed provider section.")

            context = f"asset '{asset_name}' provider"
            require_key(provider_section, "name", context)
            require_key(provider_section, "code", context)

            meta_def = cfg.get("metadata")
            cfg = _parse_metadata(meta_def, metadata_template, cfg)
            # CO: if isinstance(meta_def, dict):
            # CO:     cfg |= meta_def
            # CO: else:
            # CO:     template_list = meta_def if isinstance(meta_def, list) else [meta_def]
            # CO:     for name in template_list:
            # CO:         template = metadata_template.get(name)
            # CO:         if template is None:
            # CO:             return asset_parse_error(asset_name, f"Could not find metadata template '{name}'")
            # CO:         cfg = deep_merge(cfg, template)

            tags = {k.lower(): v for k, v in cfg.get("tags", {}).items()}
            cfg |= tags
            asset = Asset.from_config(name=asset_name, config=cfg)
            asset_list.append(asset)

            series_config = require_key(cfg, "series", context)
            assert isinstance(series_config, dict)

            for code, series_def in series_config.items():
                config = _parse_metadata(series_def, metadata_template, {})
                # CO: if isinstance(series_def, dict):
                # CO:     config = dict(series_def)
                # CO: else:
                # CO:     config = {}
                # CO:     template_list = series_def if isinstance(series_def, list) else [series_def]
                # CO:     for name in template_list:
                # CO:         template = metadata_template.get(name)
                # CO:         if template is None:
                # CO:             return asset_parse_error(asset_name, f"Could not find metadata template '{name}'")
                # CO:         config = deep_merge(config, template)
                require_key(config, "interval", context)
                series = Series.create(asset=asset, code=code, config=config)
                series_list.append(series)

        except Exception as exc:  # also by require()
            return Failure(reason=f"Could not parse asset '{asset_name}'", error=exc)

    return Success((asset_list, series_list))


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
    paths_cfg = env_cfg.get("paths", {})
    paths = {key: resolve_config_path(value, key, project_root) for key, value in paths_cfg.items()}
    timescaledb_cfg = env_cfg.get(BACKEND, {})
    logging_cfg = env_cfg.get("logging", {})
    return {"paths": paths, BACKEND: timescaledb_cfg, "logging": logging_cfg}


def load_business_config(biz_cfg: dict) -> Result[dict]:

    raw_providers = biz_cfg.get("providers", {})
    providers = normalize_providers(raw_providers)
    if providers.ok is False:
        return providers

    raw_series_templates = biz_cfg.get("series_templates")

    template_result = check_series_templates(raw_series_templates)
    if template_result.ok is False:
        return template_result
    series_templates = template_result.payload
    raw_assets = biz_cfg.get("assets", {})

    # Normalize assets section into assets and series.
    result = normalize_assets_and_series(raw_assets, series_templates)
    if result.ok is False:
        return result
    assets, series = result.payload

    # validate composites
    """
    raw_composites = biz_cfg.get("composites", {})

    #composites = normalize_composites(raw_composites)
    if composites.ok is False:
        return composites
    """

    return Success({"providers": providers.payload, "assets": assets, "series": series})
    # , "composites": composites.payload}
