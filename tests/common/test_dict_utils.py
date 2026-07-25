# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_dict_utils.py

from finance.common.dict_utils import deep_merge


def test_scalar_overwrite():
    a = {"interval": "1m"}
    b = {"interval": "5m"}
    result = deep_merge(a, b)
    assert result == {"interval": "5m"}


def test_add_new_keys():
    a = {"interval": "1m"}
    b = {"bootstrap_history": "5y"}
    result = deep_merge(a, b)
    assert result == {"interval": "1m", "bootstrap_history": "5y"}


def test_nested_merge():
    a = {"provider": {"timeout": 5, "retries": 3}}
    b = {"provider": {"retries": 10}}
    result = deep_merge(a, b)
    assert result == {"provider": {"timeout": 5, "retries": 10}}


def test_nested_merge_add_keys():
    a = {"provider": {"timeout": 5}}
    b = {"provider": {"retries": 10}}
    result = deep_merge(a, b)
    assert result == {"provider": {"timeout": 5, "retries": 10}}


def test_nested_overwrite_entire_value_when_not_dict():
    a = {"provider": {"timeout": 5}}
    b = {"provider": 42}
    result = deep_merge(a, b)
    assert result == {"provider": 42}


def test_list_overwrite():
    a = {"modes": ["intraday"]}
    b = {"modes": ["daily", "weekly"]}
    result = deep_merge(a, b)
    assert result == {"modes": ["daily", "weekly"]}


def test_multiple_levels_deep():
    a = {"a": {"b": {"c": 1}}}
    b = {"a": {"b": {"d": 2}}}
    result = deep_merge(a, b)
    assert result == {"a": {"b": {"c": 1, "d": 2}}}


def test_right_side_wins_scalar_vs_dict():
    a = {"provider": {"timeout": 5}}
    b = {"provider": "disabled"}
    result = deep_merge(a, b)
    assert result == {"provider": "disabled"}


def test_left_side_unchanged():
    a = {"provider": {"timeout": 5}}
    b = {"provider": {"timeout": 10}}
    result = deep_merge(a, b)
    assert a == {"provider": {"timeout": 5}}  # original must not mutate
    assert result == {"provider": {"timeout": 10}}


def test_empty_right_side():
    a = {"interval": "1m"}
    b = {}
    result = deep_merge(a, b)
    assert result == {"interval": "1m"}


def test_empty_left_side():
    a = {}
    b = {"interval": "1m"}
    result = deep_merge(a, b)
    assert result == {"interval": "1m"}
