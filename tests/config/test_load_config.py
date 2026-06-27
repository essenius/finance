# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_load_config.py

from finance.common.model import Asset, Provider, Resolution, Series, SeriesType
from finance.config.loader import ConfigLoader, load_yaml_config


def test_load_yaml_config(tmp_path, unwrap):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("providers:\n  yahoo:\n    default_interval: 10m\n")
    cfg = unwrap(load_yaml_config(yaml_file))
    assert cfg["providers"]["yahoo"]["default_interval"] == "10m"


def test_load_config_end_to_end(tmp_path, unwrap):
    yaml_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"

    yaml_file.write_text("""
environment:
  paths:
    wal: mywal.jsonl
    state: state.json

business:
  providers:
    yahoo:
      timezone: UTC

  assets:
    spx:
      provider: yahoo
      provider_code: "^GSPC"
      symbol: SPX
      tags:
        instrument: index
        exchange: NYSE
      resolution:
        daily:
          interval: 1d

  composites:
    spread:
      symbol: SPREAD
      expression: "fred_10y_daily - fred_2y_daily"
""")

    env_file.write_text("TIMESCALEDB_URL=http://y\nTIMESCALEDB_DB=db1\n")

    environ = {"TIMESCALEDB_URL": "http://x", "TIMESCALEDB_DB": "db2"}

    loader = ConfigLoader(tmp_path, environ)
    result = loader.load()

    cfg = unwrap(result)

    # providers
    assert cfg["providers"]["yahoo"].timezone == "UTC"

    # assets
    assert len(cfg["assets"]) == 1
    asset: Asset = cfg["assets"][0]
    assert asset.provider_code == "^GSPC"
    assert asset.name == "spx"
    assert asset.symbol == "SPX"
    assert asset.provider == "yahoo"
    assert asset.instrument == "index"
    assert asset.currency is None
    assert asset.exchange == "NYSE"
    assert asset.unit is None
    assert asset.region is None
    assert asset.id is None

    # series
    assert len(cfg["series"]) == 1
    series: Series = cfg["series"][0]
    assert series.asset_id is None
    assert series.asset_name == "spx"
    assert series.history_limit == "10y"
    assert series.history_limit_seconds == 315576000
    assert series.interval == "1d"
    assert series.interval_seconds == 86400
    assert series.resolution == Resolution.DAILY
    assert series.series_type == SeriesType.CANDLE
    assert series.id is None

    # composites
    assert cfg["composites"]["spread"]["expression"] == "fred_10y_daily - fred_2y_daily"
    assert cfg["composites"]["spread"]["asset"].symbol == "SPREAD"

    # secrets -- .env overrides environment
    assert cfg["secrets"]["timescaledb"]["url"] == "http://y"
    assert cfg["secrets"]["timescaledb"]["db"] == "db1"

    assert cfg["paths"]["wal"].is_absolute()
    assert cfg["paths"]["state"].is_absolute()

    assert cfg["paths"]["wal"].name == "mywal.jsonl"
    assert cfg["paths"]["state"].name == "state.json"


def test_load_config_missing_file(tmp_path, assert_error):

    loader = ConfigLoader(tmp_path)
    result = loader.load()

    assert_error(result, "Config file not found", None)


def test_load_config_dev_mode(monkeypatch, tmp_path, unwrap):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "config.yaml").write_text("business:\n  providers: {}\n  assets: {}\n  composites: {}\n")
    (tmp_path / ".env").write_text("TIMESCALEDB_URL=http://x\nTIMESCALEDB_DB=db\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    cfg = unwrap(result)
    expected_params = {
        "timezone": "UTC",
        "intraday_history_limit": "5d",
        "daily_history_limit": "10y",
        "intraday_interval": "10m",
        "daily_interval": "1d",
        "daily_series_type": "candle",
    }
    assert cfg["providers"] == {
        "yahoo": Provider(name="yahoo", **expected_params),
        "ecb": Provider(name="ecb", **expected_params),
        "fred": Provider(name="fred", **expected_params),
    }


def test_load_config_resolves_paths(tmp_path, unwrap):

    yaml_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"

    yaml_file.write_text("""
business: {}
environment:
  paths:
    wal: "data/mywal.jsonl"
    state: "data/mystate.json"
""")

    env_file.write_text("TIMESCALEDB_URL=http://x\nTIMESCALEDB_DB=db\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    cfg = unwrap(result)

    assert cfg["paths"]["wal"] == tmp_path / "data" / "mywal.jsonl"
    assert cfg["paths"]["state"] == tmp_path / "data" / "mystate.json"
