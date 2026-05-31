from finance.config.loader import normalize_composites


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
