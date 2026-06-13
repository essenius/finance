# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_loader_errors.py


from finance.config.loader import ConfigLoader, load_yaml_config

# ---------------------------------------------------------------------------
# load_yaml_config
# ---------------------------------------------------------------------------


def test_load_yaml_config_invalid_yaml(tmp_path, assert_error):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("this: [unclosed")

    assert_error(load_yaml_config(bad_yaml), "Invalid YAML", "while parsing a flow sequence")


# ---------------------------------------------------------------------------
# normalize_assets
# ---------------------------------------------------------------------------


def test_normalize_assets_missing_required(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets:
    spx:
      symbol: "^GSPC"   # missing provider
  composites: {}
environment:
  buckets:
    daily: d
    intraday: i
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")

    loader = ConfigLoader(tmp_path)
    assert_error(loader.load(), "Missing required field 'provider' in asset 'spx'", None)


def test_normalize_assets_field_sets_wrong(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  field_sets:
    candle: ["bogus"]
environment:
  buckets:
    daily: d
    intraday: i
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")
    loader = ConfigLoader(tmp_path)

    assert_error(loader.load(), "Cannot redefine field set 'candle'", None)


# ---------------------------------------------------------------------------
# load_environment_config
# ---------------------------------------------------------------------------


def test_load_environment_config_missing_buckets(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets: {}
  composites: {}
environment:
  paths:
    wal: w
    state: s
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Missing bucket definitions for: ['daily', 'intraday']", None)


def test_load_environment_config_invalid_bucket(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets: {}
  composites: {}
environment:
  paths:
    wal: w
    state: s
  buckets:
    daily: d
    bogus: b
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Invalid bucket keys: ['bogus']. Allowed keys: ['daily', 'intraday']", None)


# ---------------------------------------------------------------------------
# load_business_config
# ---------------------------------------------------------------------------


def test_load_business_config_invalid_asset(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers:
    yahoo: {}
  assets:
    spx: {}   # missing symbol, provider
  composites: {}
environment:
  buckets:
    daily: d
    intraday: i
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Missing required field 'provider' in asset 'spx'", None)


def test_load_business_config_invalid_bucket(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets: {}
  composites: {}
environment:
  buckets:
    daily: d
  paths:
    wal: w
    state: s
""")

    # asset refers to bucket "bogus" which is missing
    yaml_file.write_text("""
business:
  providers: {}
  assets:
    spx:
      provider: yahoo
      symbol: X
      tags: {}
      timeseries:
        bogus:
          interval: 1d
          fields: [open]
  composites: {}
environment:
  buckets:
    daily: d,
    intraday: i
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")
    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Unknown timeseries name 'bogus' in asset 'spx'", None)


def test_load_business_config_invalid_composite(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets: {}
  composites:
    spread:
      tags: {}   # missing expression
environment:
  buckets:
    daily: d
    intraday: i
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Missing required field 'expression' in composite 'spread'", None)


def test_load_config_business_failure(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets:
    spx: {}   # invalid
  composites: {}
environment:
  buckets:
    daily: d,
    intraday: i
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Missing required field 'provider' in asset 'spx'", None)


def test_load_config_provider_failure(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers:
    ecb:
      timezone: bogus
environment:
  buckets:
    daily: d,
    intraday: i
""")

    env_file = tmp_path / ".env"
    env_file.write_text("INFLUX_URL=x\nINFLUX_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Invalid timezone 'bogus' for provider 'ecb'", None)
