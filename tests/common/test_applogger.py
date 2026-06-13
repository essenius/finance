# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_applogger.py

import logging

from finance.common.applogger import LOG_LEVELS, AppLogger


def test_error_logs_to_logger(caplog):
    log = AppLogger()
    log.min_level = LOG_LEVELS["debug"]

    with caplog.at_level(logging.ERROR):
        result = log.error("boom", x=1)

    # The logline is exactly what LogMixin constructs
    assert "ERROR | boom | x=1" in caplog.text

    # Return structure still correct
    assert result["level"] == "error"
    assert result["logline"] == "ERROR | boom | x=1"
    assert result["x"] == 1


def test_info_logs(caplog):
    log = AppLogger()

    with caplog.at_level(logging.INFO):
        result = log.info("hello", a=2)

    assert "INFO | hello | a=2" in caplog.text
    assert result["level"] == "info"
    assert result["a"] == 2


def test_debug_filtered_out(caplog):
    log = AppLogger()

    # Set global logging level to INFO
    with caplog.at_level(logging.INFO):
        result = log.debug("hidden", foo=3)

    # No debug logs should appear at INFO level
    assert caplog.text == ""
    assert result == {}


def test_log_without_msg(caplog):
    log = AppLogger()

    with caplog.at_level(logging.INFO):
        result = log.info(x=42)

    # Extract the logline
    assert "INFO" in caplog.text
    assert "x=42" in caplog.text
    assert "INFO | |" not in caplog.text  # no double separator

    assert result["level"] == "info"
    assert result["x"] == 42


def test_ok_field_removed(caplog):
    log = AppLogger()

    with caplog.at_level(logging.INFO):
        log.info("msg", ok=False, x=4)

    assert "ok=" not in caplog.text
    assert "x=4" in caplog.text


def test_nested_dict_flattening(caplog):
    log = AppLogger()

    with caplog.at_level(logging.INFO):
        log.info("nested", data={"a": 1, "b": 2})

    assert "data.a=1" in caplog.text
    assert "data.b=2" in caplog.text


def test_warning_level(caplog):
    log = AppLogger()

    with caplog.at_level(logging.WARNING):
        log.warning("careful", y=5)

    assert "WARNING | careful | y=5" in caplog.text


def test_warning_flattening(caplog):
    log = AppLogger()

    with caplog.at_level(logging.WARNING):
        log.warning(warnings=["warning 1", "warning 2"])

    assert "WARNING | warnings=warning 1" in caplog.text
    assert "WARNING | warnings=warning 2" in caplog.text


"WARNING  AppLogger:test_applogger.py:97 WARNING | warnings=warning 1\nWARNING  AppLogger:test_applogger.py:97 WARNING | warnings=warning 2\n"
