# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_env_secrets.py

import os

import pytest

from finance.common.model import BACKEND, BACKEND_UPPER
from finance.config.loader import ConfigLoader


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Remove all TIMESCALEDB_* and *_API_KEY variables
    for var in list(os.environ):
        if var.startswith("TIMESCALEDB_") or var.endswith("_API_KEY"):
            monkeypatch.delenv(var, raising=False)


def test_load_env_secrets_timescaledb(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text(f"{BACKEND_UPPER}_URL=http://x\n{BACKEND_UPPER}_DB=db\nFRED_API_KEY=abc\n")

    fake_env = {
        f"{BACKEND_UPPER}_USER": "u",
        f"{BACKEND_UPPER}_PASSWORD": "p",
        "YAHOO_API_KEY": "yahoo123",
        "FRED_API_KEY": "overwritten",  # should be overridden by .env
    }

    loader = ConfigLoader(project_root=tmp_path, environ=fake_env)

    secrets = unwrap(loader.load_env_secrets())["secrets"]

    assert secrets[BACKEND]["url"] == "http://x"
    assert secrets[BACKEND]["db"] == "db"
    assert secrets[BACKEND]["user"] == "u"
    assert secrets[BACKEND]["password"] == "p"

    assert secrets["api_keys"]["fred"] == "abc"  # from .env
    assert secrets["api_keys"]["yahoo"] == "yahoo123"  # from getenv
