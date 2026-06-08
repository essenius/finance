
import pytest

from finance.common.model import FetchPoint, MeasurementResult, Result, TimeseriesWrite
from finance.main_utils import process_result, unwrap

# ---------------------------------------------------------------------------
# unwrap tests
# ---------------------------------------------------------------------------

def test_unwrap_success_no_warning(caplog):
    caplog.set_level("DEBUG")
    r = Result.ok_payload(123)
    assert unwrap(r, throw=False) == 123
    # no warnings logged
    assert "warning=" not in caplog.text


def test_unwrap_success_with_warning(caplog):
    caplog.set_level("WARNING")
    r = Result(ok=True, payload=42, warning="careful")
    assert unwrap(r, throw=False) == 42
    assert "warning=careful" in caplog.text


def test_unwrap_failure_no_throw(caplog):
    caplog.set_level("ERROR")
    r = Result.fail("x", "broken")
    assert unwrap(r, throw=False) is None
    assert "reason=x | error=broken" in caplog.text


def test_unwrap_failure_with_throw():
    r = Result.fail("x", "boom")
    with pytest.raises(ValueError):
        unwrap(r, throw=True)


# ---------------------------------------------------------------------------
# process_result tests
# ---------------------------------------------------------------------------

class FakeState:
    """State that records ingest calls."""
    def __init__(self):
        self.calls = []

    def ingest(self, write: TimeseriesWrite):
        self.calls.append(write)
        return Result.ok_payload(write)  # success


class SkipState(FakeState):
    """State that returns skip (payload=None)."""
    def ingest(self, write: TimeseriesWrite):
        self.calls.append(write)
        return Result.ok_payload(None)  # skip


class FailingState(FakeState):
    """State that returns failure."""
    def ingest(self, write: TimeseriesWrite):
        self.calls.append(write)
        return Result.fail(write.measurement, "ingest failed")


def test_process_result_failure_result_not_ok():
    r = MeasurementResult.fail("spx", "network")
    state = FakeState()
    ok = process_result(r, state, {}, "daily")
    assert ok is False
    assert state.calls == []


def test_process_result_empty_payload():
    r = MeasurementResult.ok_payload("spx", [])
    state = FakeState()
    ok = process_result(r, state, {}, "daily")
    assert ok is True
    assert state.calls == []


def test_process_result_single_point():
    fp = FetchPoint(fields={"x": 1}, timestamp=100)
    r = MeasurementResult.ok_payload("spx", [fp])
    state = FakeState()

    ok = process_result(r, state, {"tag": "v"}, "daily")
    assert ok is True

    assert len(state.calls) == 1
    w = state.calls[0]
    assert w.measurement == "spx"
    assert w.fields == {"x": 1}
    assert w.tags == {"tag": "v"}
    assert w.timestamp == 100
    assert w.bucket == "daily"


def test_process_result_multiple_points():
    fp1 = FetchPoint(fields={"a": 1}, timestamp=10)
    fp2 = FetchPoint(fields={"b": 2}, timestamp=20)
    r = MeasurementResult.ok_payload("spx", [fp1, fp2])
    state = FakeState()

    ok = process_result(r, state, {}, "intraday")
    assert ok is True
    assert len(state.calls) == 2

    assert state.calls[0].fields == {"a": 1}
    assert state.calls[1].fields == {"b": 2}


def test_process_result_skip():
    fp = FetchPoint(fields={"x": 1}, timestamp=100)
    r = MeasurementResult.ok_payload("spx", [fp])
    state = SkipState()

    ok = process_result(r, state, {}, "daily")
    assert ok is True
    assert len(state.calls) == 1


def test_process_result_ingest_failure():
    fp = FetchPoint(fields={"x": 1}, timestamp=100)
    r = MeasurementResult.ok_payload("spx", [fp])
    state = FailingState()

    ok = process_result(r, state, {}, "daily")
    assert ok is False
    assert len(state.calls) == 1
