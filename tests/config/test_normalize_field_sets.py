# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/config/test_normalize_field_sets.py

from finance.config.loader import CANDLE, PRICE, normalize_field_sets


def test_normalize_field_sets_basic(unwrap):
    field_sets = unwrap(normalize_field_sets({}))
    assert field_sets == {"candle": CANDLE, "price": PRICE}


def test_normalize_field_sets_has_candle(assert_error):
    field_sets = normalize_field_sets({"candle": []})
    assert_error(field_sets, "Cannot redefine field set 'candle'", None)


def test_normalize_field_sets_has_price(assert_error):
    field_sets = normalize_field_sets({"price": []})
    assert_error(field_sets, "Cannot redefine field set 'price'", None)


def test_normalize_field_sets_subset(unwrap):
    field_sets = unwrap(normalize_field_sets({"cv": ["close", "volume"]}))
    assert field_sets == {"candle": CANDLE, "price": PRICE, "cv": ["close", "volume"]}


def test_normalize_field_sets_has_wrong_field(assert_error):
    field_sets = normalize_field_sets({"wrong": ["bogus"]})
    assert_error(field_sets, "Unknown field 'bogus' in field set 'wrong'", None)
