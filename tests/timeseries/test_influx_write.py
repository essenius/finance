# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx_write.py

from unittest.mock import Mock

from finance.common.model import BatchWriteResult, TimeseriesResult, TimeseriesWrite
from finance.timeseries.influx import InfluxBackend, InfluxConfig

# -------------------
# Helpers
# -------------------


def mock_post_success(session):
    session.post.return_value = Mock(raise_for_status=lambda: None)


def mock_post_failure(session, exc):
    session.post.side_effect = exc


# ----------------------
# single write tests
# ----------------------


def test_write_v1_success(backend_v1, make_entry, mock_post):
    mock_post(backend_v1, status=204)

    entry = make_entry("spx", {"value": 1}, {"a": "b"}, 100)
    result = backend_v1.write(entry)

    assert result.ok
    backend_v1.session.post.assert_called_once()
    sent = backend_v1.session.post.call_args.kwargs["data"]
    assert sent == "spx,a=b value=1 100"


def test_write_v2_success(backend_v2, make_entry, mock_post):
    mock_post(backend_v2, status=204)

    entry = make_entry("gold", {"price": 123}, {}, 1000, "finance_daily")
    result = backend_v2.write(entry)

    assert result.ok

    url = backend_v2.session.post.call_args.args[0]
    assert "bucket=finance_daily" in url
    assert "org=rik" in url

    headers = backend_v2.session.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Token abc"


def test_write_failure(backend_v1, make_entry):
    backend_v1.session.post.side_effect = Exception("boom")

    entry = make_entry("m", {"v": 1}, {}, 10)

    result = backend_v1.write(entry)
    assert not result.ok
    assert "Influx write failed" in result.reason


def test_write_no_tags(backend_v1, make_entry, mock_post):
    mock_post(backend_v1, status=204)

    entry = make_entry("m", {"v": 1}, {}, 10)
    backend_v1.write(entry)

    sent = backend_v1.session.post.call_args.kwargs["data"]
    assert sent == "m v=1 10"


# -----------------------
# batch_write_v2 tests
# -----------------------


def test_batch_write_v2_full_success(backend_v2, make_entries, mock_post):
    entries = make_entries(2)

    mock_post(backend_v2, status=204)

    result = backend_v2.batch_write_v2(entries)

    assert result.ok is True
    assert result.succeeded == [0, 1]
    assert result.failed == []


def test_batch_write_v2_partial_points_rejected(backend_v2, make_entries, mock_post):
    entries = make_entries(5)

    mock_post(backend_v2, status=400, text="partial write: points 1, 3 rejected")

    result = backend_v2.batch_write_v2(entries)

    assert not result.ok
    assert result.failed == [1, 3]
    assert result.succeeded == [0, 2, 4]


def test_batch_write_v2_partial_line_errors(backend_v2, make_entries, mock_post):
    entries = make_entries(5)

    mock_post(
        backend_v2,
        status=400,
        text='{"lineErrors":[{"line":2},{"line":4}]}',
        json_data={"lineErrors": [{"line": 2}, {"line": 4}]},
    )

    result = backend_v2.batch_write_v2(entries)

    assert not result.ok
    assert result.failed == [2, 4]
    assert result.succeeded == [0, 1, 3]


def test_batch_write_v2_full_failure_500(backend_v2, make_entries, mock_post):
    entries = make_entries(3)
    mock_post(backend_v2, status=500, text="server error")

    result = backend_v2.batch_write_v2(entries)

    assert not result.ok
    assert result.succeeded == []
    assert result.failed == [0, 1, 2]


def test_batch_write_v2_malformed_json(backend_v2, make_entries, monkeypatch):
    entries = make_entries(2)

    class BadJSON:
        status_code = 400
        text = "not json"

        def json(self):
            raise ValueError("bad json")

    monkeypatch.setattr(backend_v2.session, "post", lambda *a, **k: BadJSON())

    result = backend_v2.batch_write_v2(entries)

    assert not result.ok
    assert result.succeeded == []
    assert result.failed == [0, 1]


def test_batch_write_v2_empty_error_body(backend_v2, make_entries, mock_post):
    entries = make_entries(2)
    mock_post(backend_v2, status=400, text="")

    result = backend_v2.batch_write_v2(entries)

    assert not result.ok
    assert result.succeeded == []
    assert result.failed == [0, 1]


def test_batch_write_v2_network_exception(backend_v2, make_entries, mock_post):
    entries = make_entries(2)

    mock_post(backend_v2, status=0, exception=RuntimeError("network down"))

    result = backend_v2.batch_write_v2(entries)

    assert not result.ok
    assert result.succeeded == []
    assert result.failed == [0, 1]
    assert "exception" in result.meta


def test_batch_write_v2_empty_entries(backend_v2):
    result = backend_v2.batch_write_v2([])
    assert result.ok
    assert result.succeeded == []
    assert result.failed == []


def test_batch_write_v2_with_tags(backend_v2, mock_post):
    entry = TimeseriesWrite(
        measurement="m",
        fields={"v": 1},
        tags={"a": "b"},
        timestamp=1,
        bucket="bucket",
    )

    mock_post(backend_v2, status=204)

    result = backend_v2.batch_write_v2([entry])
    assert result.ok

    sent = backend_v2.session.post.call_args.kwargs["data"]
    assert sent == "m,a=b v=1 1"


def test_batch_write_v2_line_errors_with_non_dict(backend_v2, make_entries, mock_post):
    entries = make_entries(4)

    mock_post(
        backend_v2,
        status=400,
        text='{"lineErrors":[{"line":1},"oops",{"line":3}]}',
        json_data={"lineErrors": [{"line": 1}, "oops", {"line": 3}]},
    )

    result = backend_v2.batch_write_v2(entries)

    # "oops" is ignored
    assert result.failed == [1, 3]
    assert result.succeeded == [0, 2]


def test_write_entry_v1_bypasses_batching(make_entry, monkeypatch):
    cfg = InfluxConfig(
        ssl_verify=True,
        version=1,
        base_url="https://example/api/v2/write",
        org="rik",
        read_token="123",
        write_token="abc",
        max_batch_size=20,
        max_batch_age_seconds=2.0,
    )
    b = InfluxBackend(Mock(), cfg)

    called = {}

    def fake_write(entry):
        called["ok"] = True
        return TimeseriesResult.ok_payload(entry.measurement, None)

    monkeypatch.setattr(b, "write", fake_write)

    result = b.write_entry(make_entry())

    assert result.ok
    assert called["ok"]


def test_write_entry_flush_success(backend_v2, make_entry, monkeypatch):
    b = backend_v2

    def fake_batch(entries):
        return BatchWriteResult(ok=True, succeeded=list(range(len(entries))), failed=[])

    monkeypatch.setattr(b, "batch_write_v2", fake_batch)

    b.write_entry(make_entry())
    b.write_entry(make_entry())
    assert len(b._pending) == 2, "no flush after 2 writes"

    result = b.write_entry(make_entry())  # triggers flush

    assert result.ok
    assert b._pending == [], "Flushed after 3"


def test_write_entry_flush_failure_maps_to_timeseries_result(backend_v2, make_entry, monkeypatch):
    b = backend_v2

    def fake_batch(entries):
        return BatchWriteResult(
            ok=False,
            succeeded=[],
            failed=[0, 1],
            warnings=["partial failure"],
            meta={"exception": "boom"},
        )

    monkeypatch.setattr(b, "batch_write_v2", fake_batch)

    b.write_entry(make_entry())
    b.write_entry(make_entry())
    result = b.write_entry(make_entry())  # triggers flush

    assert not result.ok
    assert any("partial failure" in w for w in result.warnings)
    assert result.meta["exception"] == "boom"


def test_write_entry_flush_failure_keeps_failed_entries(backend_v2, make_entry, monkeypatch):
    b = backend_v2
    e1 = make_entry()
    e2 = make_entry()
    e3 = make_entry()

    def fake_batch(entries):
        return BatchWriteResult(ok=False, succeeded=[], failed=[0, 1, 2])

    monkeypatch.setattr(b, "batch_write_v2", fake_batch)

    b.write_entry(e1)
    b.write_entry(e2)
    b.write_entry(e3)  # triggers flush

    assert b._pending == [e1, e2, e3]


def test_flush_pending_empty(backend_v2):
    b = backend_v2
    b._pending = []
    b._pending_bucket = None

    result = b._flush_pending()

    assert result.ok
    assert result.succeeded == []
    assert result.failed == []
    assert b._pending == []
    assert b._pending_bucket is None
