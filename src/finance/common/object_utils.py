# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/object_utils.py


from dataclasses import fields, is_dataclass, replace
from typing import Any, cast


def deep_merge(a: dict, b: dict) -> dict:
    result = a.copy()
    for key, value in b.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def apply_overrides[T](base: T, overrides: T) -> T:
    assert is_dataclass(base) and is_dataclass(overrides)

    values = {field.name: value for field in fields(base) if (value := getattr(overrides, field.name)) is not None}

    # Pyright cannot express the generic relationship between a dataclass instance
    # and dataclasses.replace(): the argument needs Any, while the return preserves T.
    return cast(T, replace(cast(Any, base), **values))
