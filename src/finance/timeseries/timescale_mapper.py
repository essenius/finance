# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/timescale_mapper.py

from ..common.model import Asset, Series, SeriesState
from ..common.string_enums import Retention, SeriesType
from ..common.time_utils import parse_time, parse_timezone


def asset_from_row(row: tuple, columns: dict[str, int]) -> Asset:
    return Asset(
        id=row[columns["id"]],
        name=row[columns["name"]],
        symbol=row[columns["symbol"]],
        provider=row[columns["provider"]],
        provider_code=row[columns["provider_code"]],
        long_name=row[columns["long_name"]],
        short_name=row[columns["short_name"]],
        instrument=row[columns["instrument"]],
        region=row[columns["region"]],
        exchange=row[columns["exchange"]],
        currency=row[columns["currency"]],
        unit=row[columns["unit"]],
        first_trade_date=row[columns["first_trade_date"]],
        timezone=parse_timezone(row[columns["timezone"]]),
        week_start=row[columns["week_start"]],
        week_end=row[columns["week_end"]],
        market_open=parse_time(row[columns["market_open"]]),
        market_close=parse_time(row[columns["market_close"]]),
    )


def series_from_row(row: tuple, columns: dict[str, int]) -> Series:
    return Series(
        id=row[columns["id"]],
        code=row[columns["code"]],
        asset_id=row[columns["asset_id"]],
        asset_name=row[columns["asset_name"]],
        name=row[columns["name"]],
        interval=row[columns["interval"]],
        series_type=SeriesType.validate(row[columns["series_type"]]),
        retention=Retention.validate(row[columns["retention"]]),
        retention_period=row[columns["retention_period"]],
        bootstrap_history=row[columns["bootstrap_history"]],
        publication_offset=row[columns["publication_offset"]],
    )


def series_state_from_range_rows(rows: list[tuple]) -> dict[int, SeriesState]:
    state: dict[int, SeriesState] = {}
    for row in rows:
        series_id = int(row[0])
        state[series_id] = SeriesState(first_point=row[1], last_point=row[2], needs_save=True)
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
