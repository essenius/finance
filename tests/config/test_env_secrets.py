# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_env_secrets.py

import os

import pytest

from finance.config.loader import ConfigLoader


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Remove all INFLUX_* and *_API_KEY variables
    for var in list(os.environ):
        if var.startswith("INFLUX_") or var.endswith("_API_KEY"):
            monkeypatch.delenv(var, raising=False)


def test_load_env_secrets_influx1(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\nFRED_API_KEY=abc\n")

    fake_env = {
        "INFLUX_USER": "u",
        "INFLUX_PASSWORD": "p",
        "YAHOO_API_KEY": "yahoo123",
        "FRED_API_KEY": "overwritten",  # should be overridden by .env
    }

    loader = ConfigLoader(project_root=tmp_path, environ=fake_env)

    secrets = unwrap(loader.load_env_secrets())["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["db"] == "db"
    assert secrets["influx"]["user"] == "u"
    assert secrets["influx"]["password"] == "p"

    assert secrets["api_keys"]["fred"] == "abc"  # from .env
    assert secrets["api_keys"]["yahoo"] == "yahoo123"  # from getenv


def test_load_env_secrets_influx2_one_token(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_TOKEN=tok123\n")

    loader = ConfigLoader(project_root=tmp_path, environ={})

    secrets = unwrap(loader.load_env_secrets())["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["token"] == "tok123"


def test_load_env_secrets_influx2_two_tokens(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_READ_TOKEN=tok123\nINFLUX_WRITE_TOKEN=123tok\n")

    loader = ConfigLoader(project_root=tmp_path, environ={})

    secrets = unwrap(loader.load_env_secrets())["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["write_token"] == "123tok"
    assert secrets["influx"]["read_token"] == "tok123"


def test_load_env_secrets_influx2_fallback_token(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_READ_TOKEN=tok123\nINFLUX_TOKEN=123tok\n")

    loader = ConfigLoader(project_root=tmp_path, environ={})

    secrets = unwrap(loader.load_env_secrets())["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["token"] == "123tok"
    assert secrets["influx"]["read_token"] == "tok123"
