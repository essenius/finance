# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_env_secrets.py

import os

import pytest

from finance.common.model import BACKEND
from finance.config.loader import ConfigLoader


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Remove all TIMESCALEDB_* and *_API_KEY variables
    for var in list(os.environ):
        if var.startswith("TIMESCALEDB_") or var.endswith("_API_KEY"):
            monkeypatch.delenv(var, raising=False)


def test_load_env_secrets_timescaledb(tmp_path, unwrap):
    env = tmp_path / ".env"
    backend_upper = BACKEND.upper()
    env.write_text(f"{backend_upper}_URL=http://x\n{backend_upper}_DB=db\nFRED_API_KEY=abc\n")

    fake_env = {
        "FINANCE_CONFIG": "my_config.yaml",
        f"{backend_upper}_USER": "u",
        f"{backend_upper}_PASSWORD": "p",
        "YAHOO_API_KEY": "yahoo123",
        "FRED_API_KEY": "overwritten",  # should be overridden by .env
    }

    loader = ConfigLoader(cwd=tmp_path, environ=fake_env)

    timescale, api_keys, config = loader.load_env_variables()

    assert timescale["db"] == "db"
    assert timescale["user"] == "u"
    assert timescale["password"] == "p"

    assert api_keys["fred"] == "abc"  # from .env
    assert api_keys["yahoo"] == "yahoo123"  # from getenv

    assert config == "my_config.yaml"
