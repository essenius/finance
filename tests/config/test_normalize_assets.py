
import pytest

from finance.config.loader import normalize_assets


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

