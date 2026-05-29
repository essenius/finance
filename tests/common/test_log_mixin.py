# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_log_mixin.py

from finance.common.log_mixin import LOG_LEVELS, LogMixin


class Dummy(LogMixin):
    pass


def test_error_goes_to_stderr(capsys):
    d = Dummy()
    d.min_level = LOG_LEVELS["debug"]

    result = d.error("boom", x=1)

    captured = capsys.readouterr()
    assert captured.err.strip() == "ERROR | boom | x=1"
    assert captured.out == ""
    assert result["level"] == "error"
    assert result["logline"] == "ERROR | boom | x=1"
    assert result["x"] == 1


def test_info_goes_to_stdout(capsys):
    d = Dummy()
    d.min_level = LOG_LEVELS["debug"]

    result = d.info("hello", a=2)

    captured = capsys.readouterr()
    assert captured.out.strip() == "INFO | hello | a=2"
    assert captured.err == ""
    assert result["level"] == "info"
    assert result["a"] == 2


def test_debug_filtered_out(capsys):
    d = Dummy()
    d.min_level = LOG_LEVELS["info"]  # debug < info → filtered

    result = d.debug("hidden", foo=3)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert result["level"] == "debug"
    assert result["skipped"] is True
    assert result["foo"] == 3


def test_log_without_msg(capsys):
    d = Dummy()
    d.min_level = LOG_LEVELS["debug"]

    result = d.info(x=42)

    captured = capsys.readouterr()
    line = captured.out.strip()

    # Should start with just the level
    assert line.startswith("INFO")

    # Should NOT contain a double separator like "INFO | | x=42"
    assert "INFO | |" not in line

    # Should contain the flattened context
    assert "x=42" in line

    # Should not write to stderr
    assert captured.err == ""

    # Return structure should be correct
    assert result["level"] == "info"
    assert result["logline"] == line
    assert result["x"] == 42


def test_ok_field_removed(capsys):
    d = Dummy()
    d.min_level = LOG_LEVELS["debug"]

    d.info("msg", ok=False, x=4)

    captured = capsys.readouterr()
    assert "ok=" not in captured.out
    assert "x=4" in captured.out


def test_nested_dict_flattening(capsys):
    d = Dummy()
    d.min_level = LOG_LEVELS["debug"]

    d.info("nested", data={"a": 1, "b": 2})

    captured = capsys.readouterr()
    line = captured.out.strip()
    assert "data.a=1" in line
    assert "data.b=2" in line


def test_warning_level(capsys):
    d = Dummy()
    d.min_level = LOG_LEVELS["debug"]

    d.warning("careful", y=5)

    captured = capsys.readouterr()
    assert captured.out.strip() == "WARNING | careful | y=5"
    assert captured.err == ""
