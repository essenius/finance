# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_load_config.py

from finance.config.loader import load_config, load_yaml_config


def test_load_yaml_config(tmp_path, unwrap):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("providers:\n  yahoo:\n    default_interval: 10m\n")
    cfg = unwrap(load_yaml_config(yaml_file))
    assert cfg["providers"]["yahoo"]["default_interval"] == "10m"


def test_load_config_end_to_end(tmp_path, monkeypatch, unwrap):
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
      default_interval: 10m

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

    env_file.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\n")

    monkeypatch.setenv("INFLUX_URL", "http://x")
    monkeypatch.setenv("INFLUX_DB", "db")

    cfg = unwrap(load_config(yaml_file, env_file))

    # providers
    assert cfg["providers"]["yahoo"]["default_interval"] == "10m"

    # assets expanded
    assert "spx_daily" in cfg["assets"]
    spx = cfg["assets"]["spx_daily"]
    assert spx["symbol"] == "^GSPC"
    assert spx["tags"]["symbol"] == "SPX"

    # composites
    assert cfg["composites"]["spread"]["expression"] == "fred_10y_daily - fred_2y_daily"

    # secrets
    assert cfg["secrets"]["influx"]["url"] == "http://x"

    assert cfg["paths"]["wal"].is_absolute()
    assert cfg["paths"]["state"].is_absolute()

    assert cfg["paths"]["wal"].name == "mywal.jsonl"
    assert cfg["paths"]["state"].name == "state.json"


def test_load_config_missing_file(tmp_path, assert_error):
    missing_yaml = tmp_path / "missing.yaml"
    missing_env = tmp_path / "missing.env"

    assert_error(load_config(missing_yaml, missing_env), "Config file not found", None)


def test_load_config_dev_mode(monkeypatch, tmp_path, unwrap):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "config.yaml").write_text(
        "environment:\n  buckets:\n    intraday: a\n    daily: b\nbusiness:\n  providers: {}\n  assets: {}\n  composites: {}\n"
    )
    (tmp_path / ".env").write_text("INFLUX_URL=http://x\nINFLUX_DB=db\n")

    result = load_config()
    cfg = unwrap(result)
    assert cfg["providers"] == {}


def test_load_config_resolves_paths(tmp_path, monkeypatch, unwrap):
    # Pretend project root is tmp_path
    monkeypatch.setattr("finance.common.paths.get_project_root", lambda: tmp_path)

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

    result = load_config(yaml_file, env_file)
    cfg = unwrap(result)

    assert cfg["paths"]["wal"] == tmp_path / "data" / "mywal.jsonl"
    assert cfg["paths"]["state"] == tmp_path / "data" / "mystate.json"
