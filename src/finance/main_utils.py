# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main_utils.py

from dataclasses import asdict
from typing import TypeVar

from finance.common.applogger import AppLogger
from finance.common.model import FetchResult, Result, TimeseriesWrite
from finance.state.state import State

logger = AppLogger()

T = TypeVar("T")


def unwrap(result: Result[T], throw: bool | None = True) -> T | None:
    """
    Unwrap a Result[T]:
    - log warnings
    - return payload on success
    - optionally throw ValueError on failure
    """
    result_dict = asdict(result)
    if not result.ok:
        logger.error(**result_dict)
        if throw:
            raise (ValueError(f"{result.reason}: {result.error}")) if result.error else ValueError(result.reason)

    # we can have warnings with ok, they still have results
    if result.warnings:
        logger.warning(**result_dict)
    else:
        logger.debug(**result_dict)
    return result.payload


def process_result(result: FetchResult, state: State, tags: dict, bucket: str) -> bool:
    """
    Process a FetchResult:
    - unwrap the MeasurementResult
    - iterate over all FetchPoints
    - build a TimeseriesWrite for each
    - ingest each one
    - only update state timestamps if all ingests succeeded
    - return True only if all ingests succeed (skip counts as success)

    """
    payload = unwrap(result, throw=False)

    # if the raw Result failed, stop here
    if not result.ok:
        return False

    if not payload:
        return True  # nothing to do

    all_ok = True

    batch_first = payload[0].timestamp
    batch_last = payload[-1].timestamp

    for point in payload:
        write = TimeseriesWrite(
            measurement=result.measurement,
            fields=point.fields,
            tags=tags or {},
            timestamp=point.timestamp,
            bucket=bucket,
        )

        ingest_result = state.ingest(write)
        # log any errors
        unwrap(ingest_result, throw=False)
        if not ingest_result.ok:
            all_ok = False

    if all_ok:
        state.update_range(result.measurement, batch_first, batch_last)
    return all_ok
