# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_json_utils.py

import pytest

from finance.common.json_utils import JsonObject, JsonReader, Sentinel
from finance.common.types import ParseError


def test_json_reader_is_empty():
    assert JsonReader({}).is_empty(), "empty dict"
    assert not JsonReader({"x": 1}).is_empty(), "filled dict"
    assert not JsonReader(1).is_empty(), "int"
    assert JsonReader([]).is_empty(), "list"


def test_json_reader_get():
    config: JsonObject = {"str": "string", "int": 1, "float_int": 2, "float": 2.5, "object": {"bool": True}}
    reader = JsonReader(config, "test")
    assert reader.get(str, "str", default="a") == "string", "get(str)"
    assert reader.get(str, "bogus", default="a") == "a", "get(unknown str) with default"
    assert reader.get(int, "int", default=0) == 1, "get(int)"
    assert reader.get(float, "float", default=0.0) == 2.5, "get(float)"
    assert reader.get(float, "float_int") == 2.0, "get(float_int)"
    assert reader.get(float, "unknown", default=0.0) == 0.0, "get(unknown float)"

    assert reader.get(bool, ["object", "bool"], default=False) is True
    assert reader.get(int, ["object", "bogus"], default=42) == 42

    sub_reader = reader.reader_for("object")
    assert sub_reader.get(bool, "bool", default=False) is True, "get(bool)"
    assert sub_reader.context == "test"

    with pytest.raises(ParseError) as ve:
        sub_reader.get(int, "bool", default=10)
    assert ve.value.args[0] == "test:bool: 'True' must be of type int", "invalid type for get"


def test_json_reader_require():
    reader = JsonReader({"str": "test"})
    assert reader.require(str, "str") == "test"

    with pytest.raises(ParseError) as ve:
        reader.require(int, "str")
    assert ve.value.args[0] == "str: 'test' must be of type int"

    with pytest.raises(ParseError) as ve:
        reader.require(int, "bogus")
    assert ve.value.args[0] == "['bogus']: Missing required key `bogus`"


def test_json_reader_get_object():
    config: JsonObject = {"list": [{"int": 3}], "float": 3.5, "none": None}
    reader = JsonReader(config)
    obj = reader.get_object(["list", 0])
    assert obj == {"int": 3}

    assert reader.get_object(["bogus"]) == {}, "non-existing leaf returns empty dict"

    with pytest.raises(ParseError) as ve:
        reader.get_object("float")
    assert ve.value.args[0] == "float: must refer to an object", "non-object leaf throws"

    assert reader.get_object("None") == {}


def test_json_reader_require_object():
    config: JsonObject = {"list": [{"int": 3}], "float": 3.5, "none": None}
    reader = JsonReader(config)
    obj = reader.require_object(["list", 0])
    assert obj == {"int": 3}

    with pytest.raises(ParseError) as ve:
        reader.require_object(["bogus"])
    assert ve.value.args[0] == "['bogus']: Missing required key `bogus`", "missing leaf throws"

    with pytest.raises(ParseError) as ve:
        reader.require_object("float")
    assert ve.value.args[0] == "float: must refer to an object", "missing leaf throws"


def test_json_reader_get_array():
    config: JsonObject = {"list": [{"int": 3}], "ints": [1, 2, 3], "wrong_ints": [1, "a"], "int": 5}
    reader = JsonReader(config)
    array = reader.get_array("list")
    assert array == [{"int": 3}]
    array2 = reader.get_array("int")
    assert array2 == [5]
    array3 = reader.get_array(["ints"])
    assert array3 == [1, 2, 3]
    array4 = reader.get_array("wrong_ints")
    assert array4 == [1, "a"]
    array5 = reader.get_array("bogus", allow_missing="yes")
    assert array5 == []
    with pytest.raises(ParseError) as ve:
        reader.get_array("wrong_ints", expected_type=int)
    assert ve.value.args[0] == "wrong_ints: 'a' must be of type int"

    with pytest.raises(ParseError) as ve:
        reader.get_array(["list", 0])
    assert ve.value.args[0] == "['list', 0]: must refer to a list"


def test_json_reader_get_nullable_array():
    config: JsonObject = {"ints": [1, 2, 3], "null_ints": [1, None, 2], "wrong_ints": [1, None, "a"]}
    reader = JsonReader(config)
    array = reader.get_nullable_array("ints", expected_type=int)
    assert array == [1, 2, 3]
    array2 = reader.get_nullable_array("null_ints")
    assert array2 == [1, None, 2]

    array3 = reader.get_nullable_array("wrong_ints")
    assert array3 == [1, None, "a"]

    with pytest.raises(ParseError) as ve:
        reader.get_nullable_array("wrong_ints", expected_type=int)
    assert ve.value.args[0] == "wrong_ints: 'a' must be of type int"


def test_json_reader_get_path():
    obj = {"int": 3, "array": [1]}
    reader = JsonReader(obj)
    assert reader.get_path("int") == 3
    assert isinstance(reader.get_path("bogus"), Sentinel)
    assert reader.get_path(["array", 0]) == 1
    with pytest.raises(ParseError) as ve:
        reader.get_path(["array", 1])
    assert ve.value.args[0] == "['array', 1]: index `1` out of range (level: 1)"
    assert reader.get_path(None) == obj


@pytest.mark.parametrize(
    "data, path, expected",
    [
        ({"a": {}}, ["a", "b", "c"], "['a', 'b', 'c']: Missing required key `b` (level: 1)"),
        ({"a": []}, ["a", 0, "b"], "['a', 0, 'b']: index `0` out of range (level: 1)"),
        ({"a": 42}, ["a", 0], "['a', 0]: type `int` is not a container (level: 1)"),
        ({1: 42}, [1], "1: object index must be a string"),  # json dict keys must be strings
        ([1, 2], ["a"], "a: array index must be an int"),  # json array keys must be int
    ],
)
def test_get_path_errors(data: JsonObject, path: list[str | int], expected: str):
    reader = JsonReader(data)
    with pytest.raises(ParseError) as ve:
        reader.get_path(path)
    assert ve.value.args[0] == expected


def test_get_first_object_value():
    config: JsonObject = {"obj": {"int": 3, "bool": True}}
    reader = JsonReader(config)
    first_value = reader.get_first_object_value("obj")
    assert first_value == 3
    with pytest.raises(ParseError) as ve:
        reader.get_first_object_value("bogus", allow_missing="yes")
    assert ve.value.args[0] == "bogus: expected at least one object value"


def test_ensure_type():

    reader = JsonReader("")
    reader.context = "context"
    assert reader.ensure_type("x", str, "string") == "x"
    assert reader.ensure_type(1, int, "int") == 1
    with pytest.raises(ParseError) as ve:
        reader.ensure_type(1, str, "not a string")
    assert ve.value.args[0] == "context:1: not a string"
    with pytest.raises(ParseError) as ve:
        reader.ensure_type("x", int, "not an int")
    assert ve.value.args[0] == "context:x: not an int"


def test_get_first_array_value():
    config: JsonObject = {"array1": [1, 2, 3], "array2": []}
    reader = JsonReader(config)
    assert reader.get_first_array_value("array1") == 1
    with pytest.raises(ParseError) as ve:
        assert reader.get_first_array_value("array2", allow_missing="leaf")
    assert ve.value.args[0] == "array2: expected at least one array value"

    with pytest.raises(ParseError) as ve:
        reader.get_first_array_value("bogus", allow_missing="yes")
    assert ve.value.args[0] == "bogus: expected at least one array value"


def test_items_returns_key_and_reader():
    reader = JsonReader({"a": 1, "b": "hello", "c": [1, 2]})

    items = list(reader.items())

    assert [key for key, _ in items] == ["a", "b", "c"]
    assert all(isinstance(item_reader, JsonReader) for _, item_reader in items)

    assert items[0][1].require(int) == 1
    assert items[1][1].require(str) == "hello"
    assert items[2][1].get_array(expected_type=int) == [1, 2]


def test_items_fails_on_non_object():
    reader = JsonReader(1)
    reader.context = "context"
    with pytest.raises(ParseError) as ve:
        reader.items()
    assert ve.value.args[0] == "context:1: value must be a JSON object"
