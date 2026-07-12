# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/state.py

from collections.abc import Iterable
from datetime import datetime, timedelta

from ..common.model import Result, Series, SeriesPoint, SeriesState
from ..state.storage import StateStorage
from ..state.wal import JsonlWAL
from ..timeseries.timescale_backend import TimescaleBackend


class State:
    def __init__(self, backend: TimescaleBackend, wal: JsonlWAL, storage: StateStorage):
        self._backend: TimescaleBackend = backend
        self._wal: JsonlWAL = wal
        self._storage: StateStorage = storage
        self.series: dict[int, SeriesState] = {}

    def load(self) -> Result[int]:
        self.series: dict[int, SeriesState] = self._storage.load()
        return self.flush_wal()

    def save(self) -> None:
        self.flush_wal()
        self._storage.save(self.series)

    def get_series_state(self, series_id: int) -> SeriesState | None:
        entry = self.series.get(series_id)
        if entry is not None:
            return entry

        rebuilt = self._rebuild_measurement_state(series_id)
        self.series[series_id] = rebuilt
        return rebuilt

    '''
    def update_after_fetch(self, series_id: int, now: datetime) -> bool:
        """
        Record that a fetch attempt was made
        """
        old = self.series.get(series_id)
        if old is None:
            # No state yet → create minimal entry
            self.series[series_id] = SeriesState(last_end=now)
        else:
            self.series[series_id] = replace(old, last_end=now)
    '''

    @staticmethod
    def is_aligned(ts: datetime, interval: timedelta) -> bool:
        # Yahoo's last candle time isn't aligned, it's the last data so far.
        # This is not a Yahoo specific policy, we don't those in general.
        seconds = int(interval.total_seconds())
        return int(ts.timestamp()) % seconds == 0

    '''
    TODO delete
    def _compute_policy(self, series: Series, time: datetime) -> dict:

        if not is_aligned(time, series.interval_delta()):
            return {"skipped": True, "reason": "misaligned-interval"}

        entry = self.get_series_state(series.id)

        # No state or no time → first ever point, must write
        if entry.first_point is None or entry.last_point is None:
            return {"skipped": False, "reason": "first"}

        # Before known window → must write
        if time < entry.first_point:
            return {"skipped": False, "reason": "before-window"}

        # After known window → must write
        if time > entry.last_point:
            return {"skipped": False, "reason": "new"}

        # Inside window → skip
        if time == entry.last_point:
            return {"skipped": False, "reason": "perhaps-changed"}

        return {"skipped": True, "reason": "inside-window"}
    '''

    def update_range(self, series_id: int, first: datetime, last: datetime) -> None:
        """
        Update the saved range after a batch has been ingested
        """
        s = self.get_series_state(series_id)
        s.update_point_range(first, last)


    def flush_wal(self) -> Result[int]:
        flushed_count = 0
        warnings = []
        # We need to create a snapshot, as the process changes the WAL
        entries = list(self._wal.read_all())
        for entry in entries:
            result = self.sync_backend(entry)
            # no sense continuing if the backend can't handle new points
            if not result.ok:
                return result
            warnings = result.warnings
            flushed_count += result.payload

        # force the backend to flush to the database
        result = self._backend.flush()
        if result.ok and (result.payload > 0):
            self.sync_wal(result.payload)
            flushed_count += result.payload
        return Result.ok_payload(flushed_count, warnings=warnings)

    def sync_wal(self, written_count: int) -> Result[int]:
        warnings = []
        removed_count = self._wal.dequeue_multiple(written_count)
        if removed_count != written_count:
            warnings.append(f"Requested to remove {written_count} entries from the WAL but removed {removed_count}")

        return Result.ok_payload(removed_count, warnings=warnings)

    def sync_backend(self, point: SeriesPoint) -> Result[int]:
        """
        - Ask backend to write a point
        - receive number of written points
        - remove that number of points from the wal
        """
        result = self._backend.add(point)

        if not result.ok:
            return result

        return self.sync_wal(result.payload)

    def ingest(self, series: Series, point: SeriesPoint) -> Result[int]:
        """
        Ingest a new metric:
        - check if write is needed, if not bail out
        - append to WAL (ingestion succeeds here)
        - ask backend to write it
        """
        if self.is_aligned(point.time, series.interval_delta()):
            self._wal.enqueue(point)

        return self.sync_backend(point)

    def iter_series_state(self) -> Iterable[tuple[int, SeriesState]]:
        """
        Yield (metric_name, entry_dict) for all metrics currently in state.

        This does NOT trigger lazy rebuild. It only iterates over what is
        already present in _state. CompositeEngine uses this to build the
        namespace for evaluation.
        """
        yield from self.series.items()

    # used for composite
    def get_last_point(self, series_id: int) -> datetime | None:
        """
        Return the last_point for a metric, performing lazy rebuild if needed.
        """
        entry = self.get_series_state(series_id)
        return entry.last_point

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
            return SeriesState()

        first_point = min(time for time in (wal_first, timescale_first) if time is not None)
        last_point = max(time for time in (wal_last, timescale_last) if time is not None)

        return SeriesState(
            first_point=first_point,
            last_point=last_point,
            first_start=first_point,
            last_end=last_point,
        )
