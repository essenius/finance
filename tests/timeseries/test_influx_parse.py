# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx.py

from unittest.mock import Mock

from finance.timeseries.influx import InfluxBackend, InfluxConfig


def test_parse_v1_basic():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 1, "x", db="d"))

    data = {
        "results": [{
            "series": [{
                "columns": ["time", "value", "tag1"],
                "values": [["2024-01-01T00:00:00Z", 123, "abc"]],
            }]
        }]
    }

    result = backend._parse_v1("bucket", "m", data)
    assert result.measurement == "m"
    assert result.fields == {"value": 123}
    assert result.tags == {"tag1": "abc"}

def test_parse_v2_basic():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 2, "x", org="o"))

    data = {
        "tables": [
            {
                "records": [
                    {
                        "_measurement": "m",
                        "_field": "value",
                        "_value": 123,
                        "_time": "2024-01-01T00:00:00Z",
                        "tag1": "abc",
                    }
                ]
            }
        ]
    }

    result = backend._parse_v2("bucket", "m", data)
    assert result.fields == {"value": 123}
    assert result.tags == {"tag1": "abc"}


def test_parse_v2_empty_tables():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 2, "x", org="o"))
    result = backend._parse_v2("bucket", "m", {"tables": []})
    assert result is None


def test_parse_v2_wrong_measurement():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 2, "x", org="o"))

    data = {
        "tables": [
            {"records": [{"_measurement": "other", "_field": "v", "_value": 1, "_time": "2024-01-01T00:00:00Z"}]}
        ]
    }

    result = backend._parse_v2("bucket", "m", data)
    assert result is None


def test_parse_v2_no_fields():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 2, "x", org="o"))

    data = {
        "tables": [
            {"records": [{"_measurement": "m", "_time": "2024-01-01T00:00:00Z"}]}
        ]
    }

    result = backend._parse_v2("bucket", "m", data)
    assert result is None

def test_parse_v2_skips_malformed_records():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 2, "x", org="o"))

    data = {
        "tables": [
            {
                "records": [
                    # malformed: missing _value
                    {"_measurement": "m", "_field": "a", "_time": "2024-01-01T00:00:00Z"},
                    # malformed: missing _field
                    {"_measurement": "m", "_value": 10, "_time": "2024-01-01T00:00:00Z"},
                    # valid
                    {
                        "_measurement": "m",
                        "_field": "good",
                        "_value": 123,
                        "_time": "2024-01-01T00:00:00Z",
                    },
                ]
            }
        ]
    }

    result = backend._parse_v2("bucket", "m", data)
    assert result.fields == {"good": 123}


def test_parse_v2_skips_result_and_table_keys():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 2, "x", org="o"))

    data = {
        "tables": [
            {
                "records": [
                    {
                        "_measurement": "m",
                        "_field": "value",
                        "_value": 123,
                        "_time": "2024-01-01T00:00:00Z",
                        "result": "ignored",
                        "table": 5,
                        "tag1": "ok",
                    }
                ]
            }
        ]
    }

    result = backend._parse_v2("bucket", "m", data)

    # Only tag1 should remain
    assert result.tags == {"tag1": "ok"}

def test_parse_v1_no_results():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 1, "x", db="d"))
    result = backend._parse_v1("bucket", "m", {"results": []})
    assert result is None


def test_parse_v1_missing_values():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 1, "x", db="d"))

    data = {
        "results": [{
            "series": [{
                "columns": ["time", "value"],
                "values": [],
            }]
        }]
    }

    result = backend._parse_v1("bucket", "m", data)
    assert result is None


def test_parse_v1_missing_columns():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 1, "x", db="d"))

    data = {
        "results": [{
            "series": [{
                # missing "columns"
                "values": [["2024-01-01T00:00:00Z", 10]],
            }]
        }]
    }

    result = backend._parse_v1("bucket", "m", data)
    assert result is None


def test_parse_v1_missing_series_returns_none():
    backend = InfluxBackend(Mock(), InfluxConfig(True, 1, "x", db="d"))

    data = {
        "results": [{
            "series": []   # triggers line 207
        }]
    }

    result = backend._parse_v1("bucket", "m", data)
    assert result is None
