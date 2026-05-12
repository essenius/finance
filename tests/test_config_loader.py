# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_config_loader.py

def test_load_env_secrets(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\nFRED_API_KEY=abc\n")

    monkeypatch.setenv("INFLUX_URL", "http://y")
    monkeypatch.setenv("INFLUX_DB", "bogus")
    monkeypatch.setenv("INFLUX_USER", "u")
    monkeypatch.setenv("INFLUX_PASSWORD", "p")
    monkeypatch.setenv("FRED_API_KEY", "fred123")
    monkeypatch.setenv("YAHOO_API_KEY", "yahoo123")

    from finance.config.loader import load_env_secrets

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

    from configparser import ConfigParser
    from finance.config.loader import load_symbols

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

    from configparser import ConfigParser
    from finance.config.loader import load_symbols

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

    from configparser import ConfigParser
    from finance.config.loader import load_symbols

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

    from configparser import ConfigParser
    from finance.config.loader import load_composites

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

    from finance.config.loader import load_config

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
