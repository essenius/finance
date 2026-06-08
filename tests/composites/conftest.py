import pytest


@pytest.fixture
def state_obj(state_env):
    state, ts, wal, path = state_env
    return state

