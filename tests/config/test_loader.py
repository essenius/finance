# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_loader.py

import pytest

from finance.config.loader import (
    load_config,
    load_env_secrets,
    load_yaml_config,
    normalize_assets,
    normalize_composites,
)

# -----------------------------
# ENV TESTS
# -----------------------------


def clean_env(monkeypatch):
    # Remove all Influx-related variables. They can bleed in
    # from the real environment or the real .env file
    for var in [
        "INFLUX_URL",
        "INFLUX_SSL_VERIFY",
        "INFLUX_SSL_CERT",
        "INFLUX_DB",
        "INFLUX_ORG",
        "INFLUX_TOKEN",
        "INFLUX_WRITE_TOKEN",
        "INFLUX_USER",
        "INFLUX_PASSWORD",
        "FRED_API_KEY",
        "YAHOO_API_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_load_env_secrets_influx1(monkeypatch, tmp_path):
    clean_env(monkeypatch)
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\nFRED_API_KEY=abc\n")

    monkeypatch.setenv("INFLUX_USER", "u")
    monkeypatch.setenv("INFLUX_PASSWORD", "p")
    monkeypatch.setenv("YAHOO_API_KEY", "yahoo123")
    monkeypatch.setenv("FRED_API_KEY", "overwritten")

    secrets = load_env_secrets(env)

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["db"] == "db"
    assert secrets["influx"]["user"] == "u"
    assert secrets["influx"]["password"] == "p"

    assert secrets["api_keys"]["fred"] == "abc"
    assert secrets["api_keys"]["yahoo"] == "yahoo123"


def test_load_env_secrets_influx2(monkeypatch, tmp_path):
    clean_env(monkeypatch)
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_TOKEN=tok123\n")

    secrets = load_env_secrets(env)

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["token"] == "tok123"


def test_missing_url_raises(monkeypatch, tmp_path):
    clean_env(monkeypatch)
    env = tmp_path / ".env"
    env.write_text("")  # no INFLUX_URL

    with pytest.raises(RuntimeError, match="requires URL"):
        load_env_secrets(env)


def test_missing_db_in_influx1(monkeypatch, tmp_path):
    clean_env(monkeypatch)
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\n")  # no INFLUX_DB

    with pytest.raises(RuntimeError, match="InfluxDB 1.x requires database"):
        load_env_secrets(env)


def test_missing_token_in_influx2(monkeypatch, tmp_path):
    clean_env(monkeypatch)
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=o\n")  # no token

    with pytest.raises(RuntimeError, match="requires INFLUX_WRITE_TOKEN"):
        load_env_secrets(env)


# -----------------------------
# YAML LOADING TESTS
# -----------------------------
def test_load_yaml_config(tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("providers:\n  yahoo:\n    default_interval: 10m\n")

    cfg = load_yaml_config(yaml_file)
    assert cfg["providers"]["yahoo"]["default_interval"] == "10m"


# -----------------------------
# ASSET NORMALIZATION TESTS
# -----------------------------
def test_normalize_assets_basic():
    raw = {
        "eurusd": {
            "provider": "yahoo",
            "symbol": "EURUSD=X",
            "tags": {
                "Symbol": "EURUSD",
                "Instrument": "forex",
            },
            "timeseries": {
                "intraday": {
                    "interval": "10m",
                    "fields": ["price"],
                }
            },
        }
    }

    assets = normalize_assets(raw)

    # loader expands into eurusd_intraday
    assert "eurusd_intraday" in assets
    a = assets["eurusd_intraday"]

    assert a["provider"] == "yahoo"
    assert a["symbol"] == "EURUSD=X"

    # tags normalized to lowercase
    assert a["tags"]["symbol"] == "EURUSD"
    assert a["tags"]["instrument"] == "forex"

    # timeseries fields preserved
    assert a["interval"] == "10m"
    assert a["fields"] == ["price"]


def test_normalize_assets_default_fields():
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {
                "daily": {
                    "interval": "1d"
                    # no fields → default to ["price"]
                }
            },
        }
    }

    assets = normalize_assets(raw)
    a = assets["spx_daily"]

    assert a["fields"] == ["price"]


def test_normalize_assets_field_set_expansion():
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {"daily": {"interval": "1d", "fields": "ohlc"}},
        }
    }

    field_sets = {"ohlc": ["open", "high", "low", "close"]}

    assets = normalize_assets(raw, field_sets=field_sets)
    a = assets["spx_daily"]

    assert a["fields"] == ["open", "high", "low", "close"]


def test_normalize_assets_bucket_flattening():
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {
                "intraday": {"interval": "10m"},
                "daily": {"interval": "1d"},
            },
        }
    }

    buckets = {"intraday": "b_intraday", "daily": "b_daily"}

    assets = normalize_assets(raw, buckets=buckets)

    assert assets["spx_intraday"]["bucket"] == "b_intraday"
    assert assets["spx_daily"]["bucket"] == "b_daily"


# -----------------------------
# COMPOSITE NORMALIZATION TESTS
# -----------------------------
def test_normalize_composites_basic():
    raw = {
        "REAL10Y": {
            "expression": "fred_10y_nominal_daily - fred_10y_breakeven_daily",
            "tags": {"Series": "REAL10Y"},
        }
    }

    composites = normalize_composites(raw)

    assert "REAL10Y" in composites
    c = composites["REAL10Y"]

    assert c["expression"] == "fred_10y_nominal_daily - fred_10y_breakeven_daily"
    assert c["tags"]["series"] == "REAL10Y"
    assert "timeseries" not in c
    assert "bucket" not in c


def test_normalize_composites_with_timeseries_and_buckets():
    raw = {
        "SPREAD": {
            "expression": "t10y_daily - t2y_daily",
            "timeseries": "daily",
            "tags": {"Series": "SPREAD"},
        }
    }

    buckets = {"intraday": "b_intraday", "daily": "b_daily"}

    composites = normalize_composites(raw, buckets=buckets)
    c = composites["SPREAD"]

    assert c["timeseries"] == "daily"
    assert c["bucket"] == "b_daily"


# -----------------------------
# END-TO-END CONFIG LOADING
# -----------------------------
def test_load_config_end_to_end(tmp_path, monkeypatch):
    yaml_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"

    yaml_file.write_text("""
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

    cfg = load_config(yaml_file, env_file)

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


# -----------------------------
# MISSING FILE BEHAVIOR
# -----------------------------
def test_load_config_missing_file(tmp_path):
    missing_yaml = tmp_path / "missing.yaml"
    missing_env = tmp_path / "missing.env"

    with pytest.raises(FileNotFoundError):
        load_config(missing_yaml, missing_env)


def test_load_config_dev_mode(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "config.yaml").write_text("providers: {}\nassets: {}\ncomposites: {}\n")
    (tmp_path / ".env").write_text("INFLUX_URL=http://x\nINFLUX_DB=db\n")

    cfg = load_config()
    assert cfg["providers"] == {}


def test_normalize_assets_missing_required_field():
    raw = {
        "eurusd": {
            # "provider" is missing → should trigger ValueError
            "symbol": "EURUSD=X",
            "timeseries": {"intraday": {"interval": "10m"}},
        }
    }

    with pytest.raises(ValueError) as exc:
        normalize_assets(raw)

    assert "Missing required field 'provider' in asset 'eurusd'" in str(exc.value)


def test_normalize_assets_missing_interval():
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {
                "daily": {
                    # missing interval
                }
            },
        }
    }

    with pytest.raises(ValueError) as exc:
        normalize_assets(raw)

    assert "Missing required field 'interval' in timeseries 'daily' in asset 'spx'" in str(exc.value)


def test_normalize_assets_unknown_field_set():
    raw = {
        "spx": {
            "provider": "yahoo",
            "symbol": "^GSPC",
            "timeseries": {"daily": {"interval": "1d", "fields": "does_not_exist"}},
        }
    }

    field_sets = {"ohlc": ["open", "high", "low", "close"]}

    with pytest.raises(ValueError) as exc:
        normalize_assets(raw, field_sets=field_sets)

    assert "Unknown field set 'does_not_exist' in asset 'spx'" in str(exc.value)


def test_normalize_composites_bucket_branch():
    raw = {
        "SPREAD": {
            "expression": "t10y_daily - t2y_daily",
            "timeseries": "daily",
            "tags": {"Series": "SPREAD"},
        }
    }

    composites = normalize_composites(raw)
    c = composites["SPREAD"]

    assert c.get("bucket") is None
