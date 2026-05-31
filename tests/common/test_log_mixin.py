# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_log_mixin.py

import logging

from finance.common.log_mixin import LOG_LEVELS, LogMixin


class Dummy(LogMixin):
    pass


def test_error_logs_to_logger(caplog):
    d = Dummy()
    d.min_level = LOG_LEVELS["debug"]

    with caplog.at_level(logging.ERROR):
        result = d.error("boom", x=1)

    # The logline is exactly what LogMixin constructs
    assert "ERROR | boom | x=1" in caplog.text

    # Return structure still correct
    assert result["level"] == "error"
    assert result["logline"] == "ERROR | boom | x=1"
    assert result["x"] == 1

def test_info_logs(caplog):
    d = Dummy()

    with caplog.at_level(logging.INFO):
        result = d.info("hello", a=2)

    assert "INFO | hello | a=2" in caplog.text
    assert result["level"] == "info"
    assert result["a"] == 2


def test_debug_filtered_out(caplog):
    d = Dummy()

    # Set global logging level to INFO
    with caplog.at_level(logging.INFO):
        result = d.debug("hidden", foo=3)

    # No debug logs should appear at INFO level
    assert caplog.text == ""

    # Return structure is still consistent, but no 'skipped' flag anymore
    assert result["level"] == "debug"
    assert result["foo"] == 3


def test_log_without_msg(caplog):
    d = Dummy()

    with caplog.at_level(logging.INFO):
        result = d.info(x=42)

    # Extract the logline
    assert "INFO" in caplog.text
    assert "x=42" in caplog.text
    assert "INFO | |" not in caplog.text  # no double separator

    assert result["level"] == "info"
    assert result["x"] == 42


def test_ok_field_removed(caplog):
    d = Dummy()

    with caplog.at_level(logging.INFO):
        d.info("msg", ok=False, x=4)

    assert "ok=" not in caplog.text
    assert "x=4" in caplog.text


def test_nested_dict_flattening(caplog):
    d = Dummy()

    with caplog.at_level(logging.INFO):
        d.info("nested", data={"a": 1, "b": 2})

    assert "data.a=1" in caplog.text
    assert "data.b=2" in caplog.text


def test_warning_level(caplog):
    d = Dummy()

    with caplog.at_level(logging.WARNING):
        d.warning("careful", y=5)

    assert "WARNING | careful | y=5" in caplog.text
