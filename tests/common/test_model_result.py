from finance.common.model import MeasurementResult


def test_result_success_payload():
    result = MeasurementResult.ok_payload("spx", payload=[1, 2, 3])

    assert result.ok is True
    assert result.measurement == "spx"
    assert result.payload == [1, 2, 3]
    assert result.warning is None
    assert result.error is None
    assert result.reason is None
    assert result.meta is None

def test_result_success_no_payload():
    result = MeasurementResult.ok_payload("spx", None)

    assert result.ok is True
    assert result.measurement == "spx"
    assert result.payload is None
    assert result.warning is None
    assert result.error is None
    assert result.reason is None
    assert result.meta is None

def test_result_success_with_warning():
    result = MeasurementResult.ok_payload("spx",[42], ["partial data"], meta={"location": "here"})

    assert result.ok is True
    assert result.measurement == "spx"
    assert result.payload == [42]
    assert result.warning == "partial data"
    assert result.error is None
    assert result.reason is None
    assert result.meta == {"location": "here"}

def test_result_success_with_multiple_warnings():
    result = MeasurementResult.ok_payload("spx", [1], ["slow response", "rate limited"])

    assert result.ok is True
    assert result.measurement == "spx"
    assert result.payload == [1]
    assert result.warning == "slow response\nrate limited"
    assert result.error is None
    assert result.reason is None
    assert result.meta is None

def test_result_success_with_empty_warnings():
    result = MeasurementResult.ok_payload("spx", payload=[1], warnings=[])

    assert result.ok is True
    assert result.measurement == "spx"
    assert result.payload == [1]
    assert result.warning is None
    assert result.error is None
    assert result.reason is None

def test_result_error_reason_only():
    result = MeasurementResult.fail("spx", "timeout")

    assert result.ok is False
    assert result.measurement == "spx"
    assert result.payload is None
    assert result.reason == "timeout"
    assert result.warning is None
    assert result.error is None

def test_result_error_with_exception_and_meta():
    exc = ValueError("boom")
    result = MeasurementResult.fail("spx","bad data", exc, meta={ "other": 1})

    assert result.ok is False
    assert result.payload is None
    assert result.reason == "bad data"
    assert result.warning is None
    assert isinstance(result.error, str)
    assert "boom" in result.error
    assert result.meta == {"other": 1}
