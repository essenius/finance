# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_load_config.py

from datetime import timedelta
from unittest.mock import patch

from finance.common.configuration import ProviderConfig
from finance.common.json_utils import JsonObject, JsonReader
from finance.common.model import Asset, Series
from finance.common.string_enums import Retention, SeriesType
from finance.common.types import Unwrap
from finance.config.loader import (
    AppConfig,
    ConfigLoader,
    check_series_templates,
    load_business_config,
    load_yaml_config,
)
from tests.support.types import AssertError


def test_load_yaml_config(tmp_path, unwrap: Unwrap[JsonReader]):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("providers:\n  yahoo:\n    default_interval: 10m\n")
    reader: JsonReader = unwrap(load_yaml_config(yaml_file))
    assert reader.get(str, ["providers", "yahoo", "default_interval"]) == "10m"


def test_load_config_end_to_end(tmp_path, unwrap: Unwrap[AppConfig]):
    yaml_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"

    yaml_file.write_text("""
environment:
  paths:
    wal: mywal.jsonl

business:
  providers:
    yahoo:
      timeout: 10s

  templates:
    daily:
      interval: 1d
    24x7:
      week_start: sun
      week_end: sat

  assets:
    spx:
      provider:
        name: yahoo
        code: "^GSPC"
      symbol: SPX
      metadata: 24x7
      tags:
        instrument: index
        exchange: NYSE
      series:
        daily: daily

  composites:
    spread:
      symbol: SPREAD
      expression: "fred_10y_daily - fred_2y_daily"
""")

    env_file.write_text("TIMESCALEDB_HOST=y\nTIMESCALEDB_DB=db1\nTIMESCALEDB_PASSWORD=password\n")

    environ = {"TIMESCALEDB_HOST": "x", "TIMESCALEDB_DB": "db2", "TIMESCALEDB_USER": "user", "FRED_API_KEY": "123abc"}

    loader = ConfigLoader(cwd=tmp_path, environ=environ)
    result = loader.load()

    app_config: AppConfig = unwrap(result)

    # providers
    assert app_config.providers["yahoo"].timeout == "10s"
    assert app_config.providers["fred"].api_key == "123abc"

    # assets
    assert len(app_config.assets) == 1
    asset: Asset = app_config.assets[0]
    assert asset.provider_code == "^GSPC"
    assert asset.name == "spx"
    assert asset.symbol == "SPX"
    assert asset.provider == "yahoo"
    assert asset.id is None

    metadata = asset.config_metadata
    assert metadata is not None
    assert metadata.instrument == "index"
    assert metadata.currency is None
    assert metadata.exchange == "NYSE"
    assert metadata.unit is None
    assert metadata.region is None
    assert metadata.first_trade_date is None
    assert metadata.week_start == "sun"
    assert metadata.week_end == "sat"

    # series
    assert len(app_config.series) == 1
    series: Series = app_config.series[0]
    assert series.asset_id is None
    assert series.asset_name == "spx"
    assert series.bootstrap_history == "10y"
    assert series.bootstrap_history_delta() == timedelta(days=3652.5)
    assert series.interval == "1d"
    assert series.interval_delta() == timedelta(days=1)
    assert series.retention == Retention.LONG_LIVED
    assert series.series_type == SeriesType.CANDLE
    assert series.id is None

    """
    # composites
    assert cfg["composites"]["spread"]["expression"] == "fred_10y_daily - fred_2y_daily"
    assert cfg["composites"]["spread"]["asset"].symbol == "SPREAD"
    """

    backend_config = app_config.timescaledb
    assert backend_config.host == "y"
    assert backend_config.dbname == "db1"

    wal_path = app_config.paths["wal"]
    assert wal_path.is_absolute()
    assert wal_path.name == "mywal.jsonl"


def test_load_config_missing_file(tmp_path, assert_error: AssertError):

    loader = ConfigLoader(cwd=tmp_path)
    result = loader.load()

    assert_error(result, "Config file not found", None)


def test_load_config_dev_mode(monkeypatch, tmp_path, unwrap: Unwrap[AppConfig]):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("business:\n  providers: {}\n  assets: {}\n  composites: {}\n")
    (tmp_path / ".env").write_text(
        "TIMESCALEDB_HOST=x\nTIMESCALEDB_DB=db\nTIMESCALEDB_USER=user\nTIMESCALEDB_PASSWORD=password"
    )

    with patch.dict("os.environ", {}, clear=True):
        loader = ConfigLoader(cwd=tmp_path)
        result = loader.load()

    cfg = unwrap(result)
    expected_params = {
        "timeout": "10s",
        "history_limits": {},
        "sweep": {},
    }
    assert cfg.providers == {
        "yahoo": ProviderConfig(name="yahoo", **expected_params),
        "ecb": ProviderConfig(name="ecb", **expected_params),
        "fred": ProviderConfig(name="fred", **expected_params),
    }


def test_load_config_resolves_paths(tmp_path, unwrap: Unwrap[AppConfig]):

    yaml_file = tmp_path / "my_config.yaml"
    env_file = tmp_path / ".env"

    yaml_file.write_text("""
business:
  providers: {}
  assets: {}
environment:
  paths:
    wal: "data/mywal.jsonl"
""")

    env_file.write_text(
        "TIMESCALEDB_HOST=x\nTIMESCALEDB_DB=db\nTIMESCALEDB_USER=u\nTIMESCALEDB_PASSWORD=p\nCONFIG_PATH=my_config.yaml"
    )

    loader = ConfigLoader(cwd=tmp_path, environ={})
    result = loader.load()
    cfg: AppConfig = unwrap(result)

    assert cfg.paths["wal"] == tmp_path / "data" / "mywal.jsonl"


def test_load_check_series_templates_minimal(unwrap: Unwrap[JsonObject]):
    reader = JsonReader({"t1": {"interval": "1d"}})
    result = check_series_templates(reader)
    output = unwrap(result)
    assert reader.value == output


def test_load_check_series_templates_maximal(unwrap: Unwrap[JsonObject]):
    reader = JsonReader(
        {
            "t1": {
                "interval": "1d",
                "series_type": "value",
                "retention": "short_lived",
                "bootstrap_history": "30d",
                "publication_offset": "16h",
            }
        }
    )
    result = check_series_templates(reader)
    output = unwrap(result)
    assert reader.value == output


def test_load_business_config_template_error(assert_error: AssertError):
    reader = JsonReader({"providers": None, "assets": None, "templates": {"t1": {"interval": "qx"}}})
    result = load_business_config(reader, {})
    assert_error(result, "Could not parse series template 't1'", "Invalid duration 'qx' in interval")
