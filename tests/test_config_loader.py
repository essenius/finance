# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_config_loader.py

from configparser import ConfigParser

import pytest

import finance.config.loader as loader
from finance.config.loader import (
    load_composites,
    load_config,
    load_env_secrets,
    load_symbols,
)


def test_load_env_secrets(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\nFRED_API_KEY=abc\n")

    monkeypatch.setenv("INFLUX_URL", "http://y")
    monkeypatch.setenv("INFLUX_DB", "bogus")
    monkeypatch.setenv("INFLUX_USER", "u")
    monkeypatch.setenv("INFLUX_PASSWORD", "p")
    monkeypatch.setenv("FRED_API_KEY", "fred123")
    monkeypatch.setenv("YAHOO_API_KEY", "yahoo123")

    secrets = load_env_secrets(env)

    # .env wins from environment variables

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["db"] == "db"
    assert secrets["influx"]["user"] == "u"
    assert secrets["influx"]["password"] == "p"

    assert secrets["api_keys"]["fred"] == "abc"
    assert secrets["api_keys"]["yahoo"] == "yahoo123"


def test_load_symbols_default_interval(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text("""
[general]
interval = 60

[yahoo]
spx = ^GSPC
""")

    parser = ConfigParser()
    parser.optionxform = str
    parser.read(ini)

    general = {"default_interval": 60 * 60}  # 60 minutes → 3600 seconds

    symbols = load_symbols(parser, general)
    assert symbols["spx"]["interval"] == 3600
    assert symbols["spx"]["symbol"] == "^GSPC"
    assert symbols["spx"]["source"] == "yahoo"
    assert symbols["spx"]["measurement"] == "spx"


def test_load_symbols_section_interval_override(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text("""
[general]
interval = 60

[yahoo]
interval = 5
spx = ^GSPC
""")

    parser = ConfigParser()
    parser.optionxform = str
    parser.read(ini)

    general = {"default_interval": 3600}

    symbols = load_symbols(parser, general)

    assert symbols["spx"]["interval"] == 5 * 60
    assert symbols["spx"]["symbol"] == "^GSPC"
    assert symbols["spx"]["source"] == "yahoo"
    assert symbols["spx"]["measurement"] == "spx"


def test_load_symbols_multiple_sections(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text("""
[general]
interval = 60

[yahoo]
spx = ^GSPC

[ecb]
eurusd = USD

[fred]
t10y = T10YIE
""")

    parser = ConfigParser()
    parser.optionxform = str
    parser.read(ini)

    general = {"default_interval": 3600}

    symbols = load_symbols(parser, general)

    assert symbols["spx"]["source"] == "yahoo"
    assert symbols["eurusd"]["source"] == "ecb"
    assert symbols["t10y"]["source"] == "fred"


def test_load_composites(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text("""
[composites]
spread = t10y - t2y
ratio = spx / gold
""")

    parser = ConfigParser()
    parser.optionxform = str
    parser.read(ini)

    composites = load_composites(parser)

    assert composites["spread"] == "t10y - t2y"
    assert composites["ratio"] == "spx / gold"


def test_load_config_end_to_end(tmp_path, monkeypatch):
    ini = tmp_path / "config.ini"
    env = tmp_path / ".env"

    ini.write_text("""
[general]
interval = 30

[yahoo]
spx = ^GSPC

[composites]
spread = t10y - t2y
""")

    env.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\n")

    monkeypatch.setenv("INFLUX_URL", "http://x")
    monkeypatch.setenv("INFLUX_DB", "db")

    cfg = load_config(ini, env)

    # default interval: 30 minutes → 1800 seconds
    assert cfg["general"]["default_interval"] == 1800

    # symbol
    sym = cfg["symbols"]["spx"]
    assert sym["symbol"] == "^GSPC"
    assert sym["interval"] == 1800
    assert sym["source"] == "yahoo"

    # composite
    assert cfg["composites"]["spread"] == "t10y - t2y"

    # secrets
    assert cfg["secrets"]["influx"]["url"] == "http://x"
    assert cfg["secrets"]["influx"]["db"] == "db"


def test_load_composites_none(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text("")

    from finance.config.loader import load_composites

    parser = ConfigParser()
    parser.optionxform = str
    parser.read(ini)

    composites = load_composites(parser)

    assert not composites


def test_load_config_dev_mode(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "config.ini").write_text("""
[general]
interval = 30

[yahoo]
spx = ^GSPC

[composites]
spread = t10y - t2y
""")

    (tmp_path / ".env").write_text("INFLUX_URL=http://x\nINFLUX_DB=db\n")

    cfg = loader.load_config()
    assert cfg["general"]["default_interval"] == 1800


def test_load_config_missing_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    # No config.ini → cwd is NOT a valid project root
    with pytest.raises(RuntimeError):
        loader.load_config()


def test_load_config_explicit_missing_file(tmp_path):
    """
    When ini_path is explicitly provided and does not exist,
    load_config() must raise FileNotFoundError.
    """
    missing_ini = tmp_path / "does_not_exist.ini"
    missing_env = tmp_path / "does_not_exist.env"

    with pytest.raises(FileNotFoundError):
        loader.load_config(ini_path=missing_ini, env_path=missing_env)
