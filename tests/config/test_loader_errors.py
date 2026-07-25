# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_loader_errors.py


import pytest

from finance.config.loader import ConfigLoader, load_yaml_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("FINANCE_CONFIG")
    # Remove all TIMESCALEDB_* and *_API_KEY variables


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
""")

    env_file = tmp_path / ".env"
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(cwd=tmp_path)
    result = loader.load()
    assert_error(result, "Could not parse asset 'spx'", "Missing required field 'provider'")


# ---------------------------------------------------------------------------
# load_business_config
# ---------------------------------------------------------------------------


def test_load_config_provider_timezone_failure(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers:
    ecb:
      timezone: bogus
""")

    env_file = tmp_path / ".env"
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(cwd=tmp_path)
    result = loader.load()
    assert_error(result, "Could not parse provider 'ecb'", "Invalid timezone 'bogus'")


def test_load_config_provider_duration_failure(tmp_path, assert_error):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers:
    ecb:
      timeout: qx
""")

    env_file = tmp_path / ".env"
    env_file.write_text("TIMESCALEDB_URL=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(cwd=tmp_path)
    result = loader.load()
    assert_error(result, "Could not parse provider 'ecb'", "Invalid duration 'qx' in timeout")
