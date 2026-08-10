# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_candle_identity.py

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from finance.common.candle_identity import CandleIdentity


def test_candle_identity():
    tokyo = ZoneInfo("Asia/Tokyo")
    now = datetime(2026, 7, 15, 12, tzinfo=tokyo)
    offset = timedelta(days=1)
    id1 = CandleIdentity(value=now, is_daily=False)

    with pytest.raises(TypeError):
        _ = id1 < 0

    assert id1 != "x"
    assert id1 == id1

    id2 = replace(id1, value=now + offset)
    id3 = replace(id2, value=now)
    assert id1 < id2, "id1 is smaller"
    assert id2 > id1, "id2 is larger"
    assert id3 == id1, "id3 and id1 are equal"
    id4 = replace(id3, is_daily=True)
    assert id4 != id3, "equal values but unequal is_daily is not equal"
    assert id1.store_label() == datetime(2026, 7, 15, 3, tzinfo=UTC)
    assert id1.publish_label() == datetime(2026, 7, 15, 12, tzinfo=tokyo)
