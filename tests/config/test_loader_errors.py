# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_loader_errors.py


from pathlib import Path
from unittest.mock import patch

from finance.config.loader import ConfigLoader, load_yaml_config
from tests.support.types import AssertError

COMPLETE_TIMESCALE_CONFIG = "TIMESCALEDB_HOST=x\nTIMESCALEDB_DB=y\nTIMESCALEDB_USER=u\nTIMESCALEDB_PASSWORD=p\n"


def test_load_config_incomplete_timescaledb(tmp_path: Path, assert_error: AssertError):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("")

    env_file = tmp_path / ".env"
    env_file.write_text("TIMESCALEDB_HOST=x\nTIMESCALEDB_DB=y\n")

    loader = ConfigLoader(cwd=tmp_path)
    with patch.dict("os.environ", {}, clear=True):
        result = loader.load()
    assert_error(
        result, reason="TimescaleDB configuration incomplete", error="Missing mandatory fields: ['user', 'password']"
    )


# ---------------------------------------------------------------------------
# load_yaml_config
# ---------------------------------------------------------------------------


def test_load_yaml_config_invalid_yaml(tmp_path: Path, assert_error: AssertError):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("this: [unclosed")

    assert_error(load_yaml_config(bad_yaml), "Invalid YAML", "while parsing a flow sequence")


# ---------------------------------------------------------------------------
# normalize_assets
# ---------------------------------------------------------------------------


def test_normalize_assets_missing_required(tmp_path: Path, assert_error: AssertError):
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
    env_file.write_text(COMPLETE_TIMESCALE_CONFIG)

    loader = ConfigLoader(cwd=tmp_path)
    with patch.dict("os.environ", {}, clear=True):
        result = loader.load()
    assert_error(result, "Could not parse asset 'spx'", "['provider', 'name']: Missing required key `provider`")


# ---------------------------------------------------------------------------
# load_business_config
# ---------------------------------------------------------------------------


def test_load_config_provider_duration_failure(tmp_path: Path, assert_error: AssertError):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
business:
  providers:
    ecb:
      timeout: qx
""")

    env_file = tmp_path / ".env"
    env_file.write_text(COMPLETE_TIMESCALE_CONFIG)

    loader = ConfigLoader(cwd=tmp_path)
    with patch.dict("os.environ", {}, clear=True):
        result = loader.load()
    assert_error(result, "Could not parse provider 'ecb'", "Invalid duration 'qx' in timeout")
