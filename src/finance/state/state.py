# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/state.py

from datetime import datetime

from ..common.guards import require
from ..common.model import SeriesPoint, SeriesState
from ..common.types import Result, Success
from ..state.wal import JsonlWAL
from ..timeseries.series_backend import SeriesBackend


class State:
    def __init__(self, backend: SeriesBackend, wal: JsonlWAL):
        self._backend: SeriesBackend = backend
        self._wal: JsonlWAL = wal
        self.series_state: dict[int, SeriesState] = {}

    def get_series_state(self, series_id: int) -> SeriesState:
        entry = self.series_state.get(series_id)
        if entry is not None:
            return entry

        self.series_state[series_id] = SeriesState()
        return self.series_state[series_id]

    def ingest(self, point: SeriesPoint) -> Result[int]:
        """
        Ingest a new metric:
        - append to WAL (ingestion succeeds here)
        - ask backend to write it
        """
        self._wal.enqueue(point)
        return self._sync_backend(point)

    def load(self) -> Result[int]:
        result = self._backend.get_series_states()
        if result.ok is False:
            return result
        self.series_state = result.payload
        self._update_wal_range()
        return self._flush_wal()

    def save(self) -> None:
        self._flush_wal()
        for id, state_entry in self.series_state.items():
            self._save_sweep(id, state_entry)

    def update_state(self, series_id: int, first: datetime, last: datetime) -> None:
        """
        Update the state after a batch has been ingested. Save if needed
        """
        series_state = require(self.get_series_state(series_id), "series state")
        series_state.update_point_range(first, last)
        self._save_sweep(series_id, series_state)

    # ----------------
    # Private methods
    # ----------------

    def _save_sweep(self, id: int, series_state: SeriesState) -> None:
        if series_state.needs_save:
            self._backend.save_sweep(
                id, require(series_state.next_sweep, "next"), require(series_state.sweep_start, "start")
            )
            series_state.needs_save = False

    def _flush_wal(self) -> Result[int]:
        flushed_count = 0
        warnings: list[str] = []
        # We need to create a snapshot, as the process changes the WAL
        entries = list(self._wal.read_all())
        for entry in entries:
            result = self._sync_backend(entry)
            # no sense continuing if the backend can't handle new points
            if result.ok is False:
                return result
            warnings = result.warnings
            flushed_count += result.payload

        # force the backend to flush to the database
        result = self._backend.flush()
        if result.ok is True and result.payload > 0:
            self._sync_wal(result.payload)
            flushed_count += result.payload
        return Success(flushed_count, warnings=warnings)

    def _sync_backend(self, point: SeriesPoint) -> Result[int]:
        """
        - Ask backend to write a point
        - receive number of written points
        - remove that number of points from the wal
        """
        result = self._backend.add_point(point)

        if result.ok is False:
            return result

        return self._sync_wal(result.payload)

    def _sync_wal(self, written_count: int) -> Result[int]:
        warnings: list[str] = []
        removed_count = self._wal.dequeue_multiple(written_count)
        if removed_count != written_count:
            warnings.append(f"Requested to remove {written_count} entries from the WAL but removed {removed_count}")

        return Success(removed_count, warnings=warnings)

    def _update_wal_range(self):
        for entry in list(self._wal.read_all()):
            series_id = entry.series_id
            timestamp = entry.time

            st = require(self.get_series_state(series_id), "series state")
            st.update_point_range(timestamp, timestamp)

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
