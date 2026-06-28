# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/state.py

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime

from ..common.model import Series, SeriesPoint, SeriesResult, SeriesState
from ..state.storage import StateStorage
from ..state.wal import JsonlWAL
from ..timeseries.timescale_backend import TimescaleBackend


class State:
    def __init__(self, backend: TimescaleBackend, wal: JsonlWAL, storage: StateStorage):
        self._backend: TimescaleBackend = backend
        self._wal: JsonlWAL = wal
        self._storage: StateStorage = storage
        self.series: dict[int, SeriesState] = storage.load()

    def save(self) -> None:
        self._storage.save(self.series)

    def get(self, series_id: int) -> SeriesState | None:
        entry = self.series.get(series_id)
        if entry is not None:
            return entry

        rebuilt = self._rebuild_measurement_state(series_id)
        if rebuilt:
            self.series[series_id] = rebuilt
            return rebuilt

        return None

    def update_after_fetch(self, series_id: int, now: datetime) -> bool:
        """
        Record that a fetch attempt was made
        """
        old = self.series.get(series_id)
        if old is None:
            # No state yet → create minimal entry
            self.series[series_id] = SeriesState(last_try=now)
        else:
            self.series[series_id] = replace(old, last_try=now)

    def _compute_policy(self, series_id: int, time: datetime) -> dict:
        entry = self.get(series_id)

        # No state or no time → first ever point, must write
        if entry is None or entry.first_time is None or entry.last_time is None:
            return {"skipped": False, "reason": "first"}

        # Before known window → must write
        if time < entry.first_time:
            return {"skipped": False, "reason": "before-window"}

        # After known window → must write
        if time > entry.last_time:
            return {"skipped": False, "reason": "new"}

        # Inside window → skip
        if time == entry.last_time:
            return {"skipped": True, "reason": "unchanged"}

        return {"skipped": True, "reason": "inside-window"}

    def update_range(self, series_id: int, first: datetime, last: datetime) -> None:
        """
        Update the saved range after a batch has been ingested
        """
        s = self.series.get(series_id) or SeriesState()

        new_first = s.first_time
        new_last = s.last_time

        if new_last is None or last > new_last:
            new_last = last

        if new_first is None or first < new_first:
            new_first = first

        if new_first != s.first_time or new_last != s.last_time:
            self.series[series_id] = replace(s, first_time=new_first, last_time=new_last)

    def ingest(self, series: Series, point: SeriesPoint) -> SeriesResult:
        """
        Ingest a new metric:
        - check if write is needed, if not bail out
        - append to WAL (ingestion succeeds here)
        - flush WAL FIFO to timeseries_client
        - on first write failure, stop and return that result

        Note: first and last times are not updated, that needs to happen after the batch was done
        """
        policy = self._compute_policy(series.id, point.time)
        if policy["skipped"]:
            return SeriesResult.ok_payload(series.name, None, meta=policy)

        # Durable accept: enqueue
        self._wal.enqueue(point)

        # Flush WAL FIFO
        while True:
            oldest = self._wal.peek()
            if oldest is None:
                break

            result = self._backend.add(oldest)

            if not result.ok:
                # stop flushing, keep WAL intact. Always give back requested entry even if an older failed
                # (because that implies the requested entry failed as well)
                return result

            # successful write → remove from WAL
            self._wal.dequeue()

        return SeriesResult.ok_payload(series.name, point, meta=policy)

    def iter_series_state(self) -> Iterable[tuple[int, SeriesState]]:
        """
        Yield (metric_name, entry_dict) for all metrics currently in state.

        This does NOT trigger lazy rebuild. It only iterates over what is
        already present in _state. CompositeEngine uses this to build the
        namespace for evaluation.
        """
        yield from self.series.items()


    # used for composite
    def get_last_time(self, series_id: int) -> datetime | None:
        """
        Return the last_time for a metric, performing lazy rebuild if needed.
        """
        entry = self.get(series_id)
        return None if entry is None else entry.last_time

    '''
    Removed from V1 scope
    def update_composite(self, series_id: str, fields: dict, timestamp: int) -> None:
        """
        Update a composite metric in state.
        """
        self.series[series_id] = {
            "fields": fields,
            "last_timestamp": timestamp,
        }
    '''

    def _rebuild_measurement_state(self, series_id: int) -> SeriesState | None:
        wal_entries = [e for e in self._wal.read_all() if e.series_id == series_id]

        # no need to check property existence as read_all already removes invalid entries
        wal_first = min((e.time for e in wal_entries), default=None)
        wal_last = max((e.time for e in wal_entries), default=None)

        timescale_first_point = self._backend.read_first(series_id)
        timescale_last_point = self._backend.read_last(series_id)

        timescale_first = timescale_first_point.payload.time if timescale_first_point.payload else None
        timescale_last = timescale_last_point.payload.time if timescale_last_point.payload else None

        # If nothing exists anywhere, bail out
        if wal_first is None and timescale_first is None:
            return None

        first_time = min(time for time in (wal_first, timescale_first) if time is not None)
        last_time = max(time for time in (wal_last, timescale_last) if time is not None)

        return SeriesState(
            first_time=first_time,
            last_time=last_time,
            last_try=None,
        )
