# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_result.py

from finance.common.result import Failure, Result, Success


def test_result_success_payload():
    result: Result[list[int]] = Success(payload=[1, 2, 3])

    assert result.ok is True
    assert result.payload == [1, 2, 3]
    assert result.warnings == []
    assert result.meta is None


def test_result_success_no_payload():
    result: Result[None] = Success(None)

    assert result.ok is True
    assert result.payload is None
    assert result.warnings == []
    assert result.meta is None


def test_result_success_with_warnings():
    result: Result = Success([1], ["slow response", "rate limited"])

    assert result.ok is True
    assert result.payload == [1]
    assert result.warnings == ["slow response", "rate limited"]
    assert result.meta is None


def test_result_success_with_empty_warnings():
    result: Result = Success(payload=[1], warnings=[])

    assert result.ok is True
    assert result.payload == [1]
    assert result.warnings == []


def test_result_error_reason_only():
    result: Result = Failure(reason="timeout")

    assert result.ok is False
    assert result.reason == "timeout"
    assert result.warnings == []
    assert result.error is None


def test_result_error_with_exception_and_meta():
    exc = ValueError("boom")
    result: Result = Failure(reason="bad data", error=exc, meta={"other": 1})

    assert result.ok is False
    assert result.reason == "bad data"
    assert result.warnings == []
    assert isinstance(result.error, ValueError)
    assert "boom" in str(result.error)
    assert result.meta == {"other": 1}
