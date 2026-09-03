# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/json_utils.py

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Literal, cast, overload

from ..common.types import ParseError

type JsonValue = str | int | float | bool | None
type JsonObject = dict[str, JsonLike]
type JsonArray = list[JsonLike]
type JsonContainer = dict[str, JsonLike] | list[JsonLike]
type JsonLike = JsonValue | JsonContainer
type JsonPathPart = str | int
type JsonPath = str | list[JsonPathPart] | None

type AllowMissing = Literal["yes", "no", "leaf"]


class Sentinel:
    pass


class JsonReader:
    context: str
    value: JsonLike

    def __init__(self, value: JsonLike, context: str = ""):
        self.value = value
        self.context = context

    # ---------------
    # Public methods
    # ---------------

    def ensure_type[T](self, value: JsonLike, type: type[T], message: str) -> T:
        if not isinstance(value, type):
            raise self._error(message, subject=value)
        return value

    @overload
    def get[T: JsonLike](self, expected_type: type[T], path: JsonPath = None, *, default: None = None) -> T | None: ...

    @overload
    def get[T: JsonLike](self, expected_type: type[T], path: JsonPath = None, *, default: T) -> T: ...

    def get[T: JsonLike](self, expected_type: type[T], path: JsonPath = None, *, default: T | None = None) -> T | None:
        value = self.get_any(path, default=default)
        if value is None:
            return value
        return self._validate(path, value, expected_type)

    def get_any(
        self, path: JsonPath = None, *, allow_missing: AllowMissing = "leaf", default: JsonLike = None
    ) -> JsonLike:
        value = self.get_path(path, allow_missing=allow_missing)
        if isinstance(value, Sentinel):
            return default
        return value

    @overload
    def get_array(
        self, path: JsonPath = None, *, expected_type: None = None, allow_missing: AllowMissing = "no"
    ) -> JsonArray: ...

    @overload
    def get_array[T: JsonLike](
        self, path: JsonPath = None, *, expected_type: type[T], allow_missing: AllowMissing = "no"
    ) -> list[T]: ...

    def get_array[T: JsonLike](
        self, path: JsonPath = None, *, expected_type: type[T] | None = None, allow_missing: AllowMissing = "no"
    ) -> JsonArray | list[T]:
        if expected_type is None:
            return self._get_array(path, allow_missing)

        return self._get_array(path, allow_missing, lambda item: self._validate(path, item, expected_type))

    def get_first_array_value(self, path: JsonPath, allow_missing: AllowMissing = "no") -> JsonLike:
        allow2 = allow_missing if allow_missing != "leaf" else "no"
        array = self.get_array(path, allow_missing=allow2)
        if not array:
            raise self._error("expected at least one array value", subject=path)
        return array[0]

    def get_first_object_value(self, path: JsonPath, allow_missing: AllowMissing = "no") -> JsonLike:
        allow2 = allow_missing if allow_missing != "leaf" else "no"
        obj = self.get_object(path, allow2)
        if not obj:
            raise self._error("expected at least one object value", subject=path)
        return next(iter(obj.values()))

    @overload
    def get_nullable_array(
        self, path: JsonPath, *, expected_type: None = None, allow_missing: AllowMissing = "no"
    ) -> JsonArray: ...

    @overload
    def get_nullable_array[T: JsonLike](
        self, path: JsonPath, *, expected_type: type[T], allow_missing: AllowMissing = "no"
    ) -> list[T | None]: ...

    def get_nullable_array[T: JsonLike](
        self, path: JsonPath, *, expected_type: type[T] | None = None, allow_missing: AllowMissing = "no"
    ) -> JsonArray | list[T | None]:
        if expected_type is None:
            return self._get_array(path, allow_missing)

        def validate(item: JsonLike) -> T | None:
            if item is None:
                return None
            return self._validate(path, item, expected_type)

        return self._get_array(path, allow_missing, validate)

    def get_object(self, path: JsonPath = None, allow_missing: AllowMissing = "leaf") -> JsonObject:
        value = self.get_any(path, allow_missing=allow_missing)
        if isinstance(value, Sentinel) or value is None:
            # not 100% pure to equate None to an empty object, but good enough for our purposes, and makes types a lot easier
            return {}
        if not isinstance(value, dict):
            raise self._error("must refer to an object", subject=path)
        return value

    @overload
    def get_path(self, path: JsonPath, allow_missing: Literal["no"]) -> JsonLike: ...
    @overload
    def get_path(self, path: JsonPath, allow_missing: Literal["yes", "leaf"] = "leaf") -> JsonLike | Sentinel: ...

    def get_path(self, path: JsonPath, allow_missing: AllowMissing = "leaf") -> JsonLike | Sentinel:
        path = self._normalize_path(path)
        if path is None:
            return self.value

        current: JsonLike = self.value

        for i, part in enumerate(path):
            is_leaf = i == len(path) - 1

            # if we fail before the leaf, give the default only if allow missing is yes
            if current is None and allow_missing == "yes":
                return Sentinel()

            if isinstance(current, dict):
                part = self.ensure_type(part, str, "object index must be a string")
                value = current.get(part)
                if value is None:
                    if allow_missing == "yes" or (allow_missing == "leaf" and is_leaf):
                        return Sentinel()
                    raise self._error(f"Missing required key `{part}`", subject=path, level=i)
                current = value
                continue

            if isinstance(current, list):
                part = self.ensure_type(part, int, "array index must be an int")
                if part < 0 or part >= len(current):
                    raise self._error(f"index `{part}` out of range", subject=path, level=i)
                current = current[part]
                continue
            message = (
                "Incomplete path"
                if current is None
                else f"type `{None if current is None else type(current).__name__}` is not a container"
            )
            raise self._error(message, subject=path, level=i)

        return current

    def is_empty(self) -> bool:
        return not self.value

    def items(self) -> Iterator[tuple[str, JsonReader]]:
        if self.value is None:
            return iter(())

        if not isinstance(self.value, dict):
            raise self._error("value must be a JSON object", subject=self.value)

        return ((key, JsonReader(value)) for key, value in self.value.items())

    def reader_for(self, path: JsonPath, allow_missing: AllowMissing = "no", context: str = "") -> JsonReader:
        value = self.get_any(path, allow_missing=allow_missing)
        context = self.context if context == "" else context
        return JsonReader(value, context)

    def require[T: JsonLike](self, expected_type: type[T], path: JsonPath = None) -> T:
        value = self.get_path(path, allow_missing="no")
        return self._validate(path, value, expected_type)

    def require_object(self, path: JsonPath = None) -> JsonObject:
        return self.get_object(path, allow_missing="no")

    # ----------------
    # Private methods
    # ----------------

    def _error(self, message: str, subject: Any = "", level: int = 0) -> ParseError:
        subject = str(subject)
        parts = [part for part in (self.context, subject) if part]
        prefix = f"{':'.join(parts)}: " if parts else ""
        postfix = f" (level: {level})" if level > 0 else ""
        return ParseError(f"{prefix}{message}{postfix}")

    def _get_array[T: JsonLike](
        self, path: JsonPath, allow_missing: AllowMissing = "no", validator: Callable[[JsonLike], T] | None = None
    ) -> JsonArray | list[T]:
        value = self.get_any(path, allow_missing=allow_missing, default=[])

        if isinstance(value, dict):
            raise self._error("must refer to a list", subject=path)

        values: JsonArray = value if isinstance(value, list) else [value]

        if validator is None:
            return values
        return [validator(item) for item in values]

    def _normalize_path(self, path: JsonPath) -> list[JsonPathPart] | None:
        if path is None:
            return None
        return [path] if isinstance(path, str) else path

    def _validate[T: JsonLike](self, path: JsonPath, value: JsonLike, expected_type: type[T]) -> T:
        if type(value) is expected_type:
            return cast(T, value)

        if expected_type is float and type(value) is int:
            return cast(T, float(value))

        raise self._error(f"'{value}' must be of type {expected_type.__name__}", subject=path)
