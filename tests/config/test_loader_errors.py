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
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Error parsing assets", "Missing required field 'provider' in asset 'spx'")


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
""")

    env_file = tmp_path / ".env"
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Error parsing assets", "Missing required field 'provider' in asset 'spx'")


def test_load_business_config_invalid_resolution(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"

    # asset refers to resolution "bogus" which is missing
    yaml_file.write_text("""
business:
  providers: {}
  assets:
    spx:
      provider: yahoo
      provider_code: ^GSPC
      symbol: SPX
      tags: {}
      resolution:
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
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")
    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(
        result, "Error parsing assets", "Invalid Resolution in asset 'spx': 'bogus'. Allowed: ['intraday', 'daily']"
    )


def test_load_business_config_invalid_composite(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets: {}
  composites:
    spread:
      symbol: SPREAD
      tags: {}   # missing expression
""")

    env_file = tmp_path / ".env"
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Error parsing composites", "Missing required field 'expression' in composite 'spread'")


'''
def test_load_config_business_failure(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers: {}
  assets:
    spx: {}   # invalid
  composites: {}
""")

    env_file = tmp_path / ".env"
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Missing required field 'provider' in asset 'spx'", None)
'''


def test_load_config_provider_timezone_failure(tmp_path, assert_error):
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
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load()
    assert_error(result, "Could not parse provider 'ecb'", "Invalid timezone 'bogus'")
