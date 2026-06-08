# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/composites/conftest.py

import pytest


@pytest.fixture
def state_obj(state_env):
    state, ts, wal, path = state_env
    return state
