# tests/test_fetch_controller.py
import time
from unittest.mock import Mock
from finance.fetch.controller import FetchController

def test_fetch_controller_skips_fresh(monkeypatch):
    # Fake fetcher that should NOT be called
    fake_fetch = Mock(return_value={"value": 123, "timestamp": 999})

    now = int(time.time())
    interval = 3600  # 1 hour

    config = {
        "sources": {
            "spx": {"source": "yahoo", "symbol": "^GSPC", "interval": interval}
        }
    }

    fetch_controller = FetchController(config, {}, now_provider=lambda: now) 
    fetch_controller.fetchers["yahoo"] = lambda cfg, key: fake_fetch(cfg["symbol"])

    state = {
        "spx": {
            "last_try": now - 100,   # fresh
            "last_value": 4000,
            "last_timestamp": 123456
        }
    }

    fetch_controller.fetch_all(state)

    fake_fetch.assert_not_called()


def test_fetch_controller_fetches_when_stale(monkeypatch):
    fake_fetch = Mock(return_value={"value": 4321, "timestamp": 777})

    interval = 3600

    config = {
        "sources": {
            "spx": {"source": "yahoo", "symbol": "^GSPC", "interval": interval}
        }
    }

    api_keys = {}
    now = 1_000_000_000

    fetch_controller = FetchController(config, api_keys, now_provider=lambda: now) 
    fetch_controller.fetchers["yahoo"] = lambda cfg, key: fake_fetch(cfg["symbol"])

    state = {
        "spx": {
            "last_try": now - 7200,  # stale
            "last_value": 4000,
            "last_timestamp": 123456
        }
    }

    result = fetch_controller.fetch_all(state)

    fake_fetch.assert_called_once_with("^GSPC")
    assert state["spx"]["last_value"] == 4000
    assert state["spx"]["last_timestamp"] == 123456
    assert state["spx"]["last_try"] >= now


def test_fetch_controller_unknown_source(capsys):
    config = {
        "sources": {
            "mystery": {
                "source": "unknown",
                "symbol": "???",
                "interval": 3600
            }
        }
    }

    api_keys = {}
    now = 1_000_000_000
    fc = FetchController(config, api_keys, now_provider=lambda: now)

    state = {}
    results = fc.fetch_all(state)

    # No results and no stete updates because no fetcher exists
    assert results == {}
    assert state == {}

    # verify the printed message
    captured = capsys.readouterr()
    assert "Skipping unknown metric mystery - no fetcher" in captured.out


def test_fetch_controller_fetcher_returns_none():
    fake_fetch = Mock(return_value={"value": None, "timestamp": None})

    config = {
        "sources": {
            "spx": {
                "source": "yahoo",
                "symbol": "^GSPC",
                "interval": 3600
            }
        }
    }

    api_keys = {"yahoo": None}
    now = 1_000_000_000
    fc = FetchController(config, api_keys, now_provider=lambda: now)

    fc.fetchers["yahoo"] = lambda cfg, key: fake_fetch(cfg["symbol"])

    state = {"spx": {}}

    results = fc.fetch_all(state)

    # Fetcher was called
    fake_fetch.assert_called_once_with("^GSPC")

    # No result returned
    assert results == {}

    # last_try updated
    assert state["spx"]["last_try"] == now

    # No value/timestamp updated
    assert "last_value" not in state["spx"]
    assert "last_timestamp" not in state["spx"]
