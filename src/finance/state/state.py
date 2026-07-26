# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/state.py

from collections.abc import Iterable
from datetime import datetime

from ..common.model import SeriesPoint, SeriesState
from ..common.result import Result
from ..state.wal import JsonlWAL
from ..timeseries.timescale_backend import TimescaleBackend


class State:
    def __init__(self, backend: TimescaleBackend, wal: JsonlWAL):
        self._backend: TimescaleBackend = backend
        self._wal: JsonlWAL = wal
        self.series: dict[int, SeriesState] = {}

    def load(self) -> Result[int]:
        result = self._backend.get_series_states()
        if not result.ok:
            return result
        self.series = result.payload
        self.update_wal_range()
        return self.flush_wal()

    def update_wal_range(self):
        for entry in list(self._wal.read_all()):
            series_id = entry.series_id
            timestamp = entry.time

            st = self.get_series_state(series_id)
            st.update_point_range(timestamp, timestamp)

    def save(self) -> None:
        self.flush_wal()
        for id, state_entry in self.series.items():
            if state_entry.needs_save:
                self._backend.save_sweep(id, state_entry.next_sweep, state_entry.sweep_start)
                state_entry.needs_save = False

    def get_series_state(self, series_id: int) -> SeriesState | None:
        entry = self.series.get(series_id)
        if entry is not None:
            return entry

        self.series[series_id] = SeriesState()
        return self.series[series_id]

    def update_state(self, series_id: int, first: datetime, last: datetime) -> None:
        """
        Update the state after a batch has been ingested. Save if needed
        """
        s = self.get_series_state(series_id)
        s.update_point_range(first, last)
        if s.needs_save:
            self._backend.save_sweep(id, s.next_sweep, s.sweep_start)
            s.needs_save = False

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

    def ingest(self, point: SeriesPoint) -> Result[int]:
        """
        Ingest a new metric:
        - append to WAL (ingestion succeeds here)
        - ask backend to write it
        """
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

    '''
    TODO: re-introduce after V1
    # used for composite
    def get_last_point(self, series_id: int) -> datetime | None:
        """
        Return the last_point for a metric, performing lazy rebuild if needed.
        """
        entry = self.get_series_state(series_id)
        return entry.last_point


    def update_composite(self, series_id: str, fields: dict, timestamp: int) -> None:
        """
        Update a composite metric in state.
        """
        self.series[series_id] = {
            "fields": fields,
            "last_timestamp": timestamp,
        }
    '''
