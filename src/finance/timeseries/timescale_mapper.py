# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/timescale_mapper.py

from collections.abc import Callable
from zoneinfo import ZoneInfo

from finance.common.asset_metadata import AssetMetadata
from finance.common.json_utils import JsonObject

from ..common.model import Asset, Series, SeriesState
from ..common.time_utils import parse_time


def asset_from_row(row: tuple, columns: dict[str, int]) -> Asset:
    meta = AssetMetadata(
        long_name=row[columns["long_name"]],
        short_name=row[columns["short_name"]],
        instrument=row[columns["instrument"]],
        region=row[columns["region"]],
        exchange=row[columns["exchange"]],
        currency=row[columns["currency"]],
        unit=row[columns["unit"]],
        first_available_date=row[columns["first_available_date"]],
        timezone=ZoneInfo(row[columns["timezone"]] or "UTC"),
        week_start=row[columns["week_start"]],
        week_end=row[columns["week_end"]],
        market_open=parse_time(row[columns["market_open"]]),
        market_close=parse_time(row[columns["market_close"]]),
    )

    return Asset(
        id=row[columns["id"]],
        name=row[columns["name"]],
        symbol=row[columns["symbol"]],
        provider=row[columns["provider"]],
        provider_code=row[columns["provider_code"]],
        effective_metadata=meta,
        config_metadata=meta,
    )


def series_from_row(row: tuple, columns: dict[str, int], get_asset: Callable[[int], Asset]) -> Series:
    asset = get_asset(row[columns["asset_id"]])
    config: JsonObject = {}
    for field, index in columns.items():
        config[field] = row[index]
    return Series.create(asset, code=row[columns["code"]], config=config)
    """return Series(
        asset=asset,
        calendar=SeriesCalendar.create(),
        id=row[columns["id"]],
        code=row[columns["code"]],
        asset_id=row[columns["asset_id"]],
        asset_name=row[columns["asset_name"]],
        interval=row[columns["interval"]],
        series_type=SeriesType.require(row[columns["series_type"]]),
        retention=Retention.require(row[columns["retention"]]),
        retention_period=row[columns["retention_period"]],
        bootstrap_history=row[columns["bootstrap_history"]],
        publication_offset=row[columns["publication_offset"]],
    )"""


def series_state_from_range_rows(rows: list[tuple]) -> dict[int, SeriesState]:
    state: dict[int, SeriesState] = {}
    for row in rows:
        series_id = int(row[0])
        state[series_id] = SeriesState(first_point=row[1], last_point=row[2], needs_save=False)
    return state


def series_state_merge_sweep_info(state: dict[int, SeriesState], rows: list[tuple]) -> dict[int, SeriesState]:
    for row in rows:
        series_id = row[0]
        if series_id not in state:
            state[series_id] = SeriesState(next_sweep=row[1], sweep_start=row[2], needs_save=False)
        else:
            state[series_id].next_sweep = row[1]
            state[series_id].sweep_start = row[2]
            state[series_id].needs_save = False
    return state
