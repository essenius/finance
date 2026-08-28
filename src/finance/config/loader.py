# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/config/loader.py

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import dotenv_values

from ..common.configuration import LogConfig, ProviderConfig, TimescaleConfig
from ..common.dict_utils import deep_merge
from ..common.json_utils import JsonObject, JsonReader
from ..common.model import BACKEND, Asset, Series
from ..common.paths import resolve_config_path
from ..common.string_enums import Retention, SeriesType, SupportedProviders
from ..common.time_utils import validate_duration
from ..common.types import Failure, ParseError, Result, Success

# ---------------
# Helper classes
# ---------------


@dataclass
class YamlEnvironmentConfig:
    timescaledb: JsonObject
    logging: JsonObject
    paths: dict[str, Path]


@dataclass
class EnvironmentConfig(YamlEnvironmentConfig):
    api_keys: JsonObject

    def merge(self, yaml: YamlEnvironmentConfig) -> EnvironmentConfig:
        timescaledb = self.timescaledb | yaml.timescaledb
        logging = self.logging | yaml.logging
        paths = self.paths | yaml.paths
        return EnvironmentConfig(timescaledb=timescaledb, api_keys=self.api_keys, logging=logging, paths=paths)


@dataclass
class BusinessConfig:
    providers: dict[str, ProviderConfig]
    assets: list[Asset]
    series: list[Series]


# ----------------
# Exposed classes
# ----------------


@dataclass
class AppConfig(BusinessConfig):
    paths: dict[str, Path]
    timescaledb: TimescaleConfig
    logging: LogConfig


class ConfigLoader:
    providers: dict[str, ProviderConfig]

    def __init__(self, *, cwd: Path, config_path: Path | None = None, environ=os.environ):
        self.cwd = cwd
        self.env_path = (cwd / ".env").resolve()
        self.environ = environ
        self.config_path = config_path

    def load(self) -> Result[AppConfig]:
        config_env = self.load_env_variables()

        cfg_path = self.config_path or config_env.paths.get("config") or Path("config.yaml")

        yaml_path = cfg_path if cfg_path.is_absolute() else (self.cwd / cfg_path).resolve()
        reader_result = load_yaml_config(yaml_path)
        if reader_result.ok is False:
            return reader_result
        reader = reader_result.payload
        env_reader = reader.reader_for("environment", allow_missing="yes")
        yaml_config = load_environment_config(env_reader, self.cwd)
        config = config_env.merge(yaml_config)
        # TODO: look at improving this idiom VV
        result = TimescaleConfig.validate(config.timescaledb)
        if result.ok is False:
            return result
        timescale_cfg = TimescaleConfig.from_config(config.timescaledb)
        log_cfg = LogConfig.from_config(config.logging)
        biz_result = load_business_config(reader.reader_for("business", allow_missing="no"), config.api_keys)
        if biz_result.ok is False:
            return biz_result
        app_config = AppConfig(
            **vars(biz_result.payload),
            paths=config.paths,
            timescaledb=timescale_cfg,
            logging=log_cfg,
        )
        return Success(app_config)

    # -----------------------------
    # Load secrets from .env
    # -----------------------------

    def load_env_variables(self) -> EnvironmentConfig:
        env_file_values = dotenv_values(self.env_path)
        # .env overrides environ
        merged = {**self.environ, **env_file_values}

        api_keys = {}
        timescaledb = {}
        logging = {}
        paths = {}

        for key, value in merged.items():
            key = key.lower()
            if key.endswith("_api_key"):
                provider = key[:-8]  # strip "_API_KEY"
                api_keys[provider] = value
            elif key.startswith(f"{BACKEND}_"):
                timescaledb[key[len(BACKEND) + 1 :]] = value
            elif key.startswith("log_"):
                logging[key[4:]] = value
            elif key.endswith("_path"):
                paths[key[:-5]] = Path(value)

        return EnvironmentConfig(timescaledb=timescaledb, api_keys=api_keys, logging=logging, paths=paths)


# -----------------------------
# Load YAML config
# -----------------------------

# TODO check if integrating into config loader makes sense


def load_yaml_config(yaml_path: Path) -> Result[JsonReader]:
    if not yaml_path.exists():
        return Failure(reason=f"Config file not found: {yaml_path}")

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            result = yaml.safe_load(f) or {}
            return Success(JsonReader(result))
    except yaml.YAMLError as exc:
        return Failure(reason="Invalid YAML", error=exc)


# ---------------------------------
# Normalize providers
# ---------------------------------


def normalize_providers(reader: JsonReader, api_keys: JsonObject) -> Result[dict[str, ProviderConfig]]:

    providers: dict[str, ProviderConfig] = {}
    for provider in SupportedProviders.values():
        try:
            content = reader.get_object(provider, allow_missing="yes")
            content["name"] = provider
            tz_name = str(content.get("timezone", "UTC"))
            # force validation
            ZoneInfo(tz_name)

            api_key = api_keys.get(provider)
            if api_key is not None:
                content["api_key"] = api_key
            config = ProviderConfig.from_config(content)
        except (ParseError, ZoneInfoNotFoundError) as exc:
            return Failure(reason=f"Could not parse provider '{provider}'", error=exc)

        providers[provider] = config

    return Success(providers)


# ---------------------------------
# Normalize series templates
# ---------------------------------


def check_template(reader: JsonReader) -> None:
    """Check the values early so of there are errors, it's clear where they are
    (i.e. in the template and not in the asset definition)
    """
    validate_duration(reader.get(str, "interval"), "interval")
    validate_duration(reader.get(str, "bootstrap_history"), "bootstrap history")
    series_type = reader.get(str, "series_type")
    if series_type is not None:
        SeriesType.require(series_type)
    retention = reader.get(str, "retention")
    if retention is not None:
        Retention.require(retention)
    validate_duration(reader.get(str, "publication_offset"), "publication offset")


def check_series_templates(reader: JsonReader) -> Result[JsonObject]:
    templates = reader.require_object()

    current = ""
    try:
        for name, item_reader in reader.items():
            current = name
            check_template(item_reader)
        return Success(templates)
    except ParseError as exc:
        return Failure(reason=f"Could not parse series template '{current}'", error=exc)


# -----------------------------
# Normalize asset definitions
# -----------------------------


def _embed_templates(meta: list[str] | JsonObject, template_reader: JsonReader, config: JsonObject) -> JsonObject:

    if isinstance(meta, dict):
        config |= dict(meta)
        return config

    template_list = meta if isinstance(meta, list) else [meta]
    for name in template_list:
        template = template_reader.get_object(name, allow_missing="no")
        config = deep_merge(config, template)
    return config


def normalize_assets_and_series(asset_reader: JsonReader, template_reader: JsonReader) -> Result[BusinessConfig]:
    asset_list = []
    series_list = []

    for asset_name, reader in asset_reader.items():
        try:
            reader.require(str, ["provider", "name"])
            reader.require(str, ["provider", "code"])

            metadata = reader.get_array("metadata", expected_type=str, allow_missing="yes")

            # provider_section = require_key(cfg, "provider", f"asset '{asset_name}'")
            # if not isinstance(provider_section, dict):
            #    raise ValueError("malformed provider section.")

            # require_key(provider_section, "name")
            # require_key(provider_section, "code")

            # meta_def = cfg.get("metadata")
            cfg_reader = JsonReader(_embed_templates(metadata, template_reader, reader.get_object()))
            tags = {k.lower(): v for k, v in cfg_reader.get_object("tags", allow_missing="yes").items()}

            asset = Asset.from_config(name=asset_name, config=cfg_reader.get_object() | tags)
            asset_list.append(asset)

            series = cfg_reader.reader_for("series", allow_missing="no")

            for code, series_def in series.items():
                template_reader.context = f"series '{code}'"
                input = series_def.get_any()
                meta = input if isinstance(input, dict) else series_def.get_array(expected_type=str)
                config_reader = JsonReader(_embed_templates(meta, template_reader, {}))
                config_reader.require(str, "interval")
                series = Series.create(asset=asset, code=code, config=config_reader.get_object())
                series_list.append(series)

        except ParseError as exc:
            return Failure(reason=f"Could not parse asset '{asset_name}'", error=exc.args[0])

    return Success(BusinessConfig(providers={}, assets=asset_list, series=series_list))


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


def load_environment_config(reader: JsonReader, project_root: Path) -> YamlEnvironmentConfig:
    paths_cfg = reader.get_object("paths", allow_missing="yes")
    paths = {key: resolve_config_path(str(value), key, project_root) for key, value in paths_cfg.items()}
    timescaledb_cfg = reader.get_object(BACKEND, allow_missing="yes")

    logging_cfg = reader.get_object("logging", allow_missing="yes")
    return YamlEnvironmentConfig(timescaledb=timescaledb_cfg, paths=paths, logging=logging_cfg)


def load_business_config(reader: JsonReader, api_keys: JsonObject) -> Result[BusinessConfig]:

    provider_reader = reader.reader_for("providers", allow_missing="yes")
    providers_result = normalize_providers(provider_reader, api_keys)
    if providers_result.ok is False:
        return providers_result

    template_reader = reader.reader_for("templates", allow_missing="yes")
    template_result = check_series_templates(template_reader)
    if template_result.ok is False:
        return template_result
    template_reader = JsonReader(template_result.payload, "template")

    asset_reader = reader.reader_for("assets", allow_missing="yes")
    result = normalize_assets_and_series(asset_reader, template_reader)
    if result.ok is False:
        return result
    business_config = result.payload
    business_config.providers = providers_result.payload
    # validate composites
    """
    raw_composites = biz_cfg.get("composites", {})

    #composites = normalize_composites(raw_composites)
    if composites.ok is False:
        return composites
    """

    return Success(business_config)
