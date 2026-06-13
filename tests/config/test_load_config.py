# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_load_config.py

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
  buckets:
    intraday: investing_intraday
    daily: investing_daily

business:
  providers:
    yahoo:
      timezone: UTC

  assets:
    spx:
      provider: yahoo
      symbol: "^GSPC"
      tags:
        symbol: SPX
        instrument: index
      timeseries:
        daily:
          interval: 1d
          fields: [open, close]

  composites:
    spread:
      expression: "fred_10y_daily - fred_2y_daily"
      tags:
        series: SPREAD
""")

    env_file.write_text("INFLUX_URL=http://y\nINFLUX_DB=db1\n")

    environ = {"INFLUX_URL": "http://x", "INFLUX_DB": "db2"}

    loader = ConfigLoader(tmp_path, environ)
    result = loader.load()

    cfg = unwrap(result)

    # providers
    assert cfg["providers"]["yahoo"]["timezone"] == "UTC"

    # assets expanded
    assert "spx_daily" in cfg["assets"]
    spx = cfg["assets"]["spx_daily"]
    assert spx["symbol"] == "^GSPC"
    assert spx["tags"]["symbol"] == "SPX"

    # composites
    assert cfg["composites"]["spread"]["expression"] == "fred_10y_daily - fred_2y_daily"

    # secrets -- .env overrides environment
    assert cfg["secrets"]["influx"]["url"] == "http://y"
    assert cfg["secrets"]["influx"]["db"] == "db1"

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

    (tmp_path / "config.yaml").write_text(
        "environment:\n  buckets:\n    intraday: a\n    daily: b\nbusiness:\n  providers: {}\n  assets: {}\n  composites: {}\n"
    )
    (tmp_path / ".env").write_text("INFLUX_URL=http://x\nINFLUX_DB=db\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    cfg = unwrap(result)
    assert cfg["providers"] == {
        "yahoo": {"timezone": "UTC", "intraday_history_limit": "5d", "daily_history_limit": "10y"},
        "ecb": {"timezone": "UTC", "intraday_history_limit": "5d", "daily_history_limit": "10y"},
        "fred": {"timezone": "UTC", "intraday_history_limit": "5d", "daily_history_limit": "10y"},
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
  buckets:
    daily: daily
    intraday: intraday
""")

    env_file.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    cfg = unwrap(result)

    assert cfg["paths"]["wal"] == tmp_path / "data" / "mywal.jsonl"
    assert cfg["paths"]["state"] == tmp_path / "data" / "mystate.json"
