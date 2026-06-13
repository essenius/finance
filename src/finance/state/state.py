# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/state.py

from collections.abc import Callable, Iterable

from ..common.model import FetchResult, TimeseriesResult, TimeseriesWrite
from ..state.storage import StateStorage
from ..state.wal import JsonlWAL
from ..timeseries import InfluxBackend


class State:
    def __init__(
        self, series_store: InfluxBackend, wal: JsonlWAL, storage: StateStorage, bucket_for: Callable[[str], str]
    ):
        self._timeseries_client = series_store
        self._wal = wal
        self._storage = storage
        self._bucket_for = bucket_for
        self._state: dict[str, dict] = storage.load()

    def save(self) -> None:
        self._storage.save(self._state)

    def get(self, measurement: str, default: dict | None = None) -> dict | None:
        entry = self._state.get(measurement)
        if entry is not None:
            return entry

        rebuilt = self._rebuild_measurement_state(measurement)
        if rebuilt:
            self._state[measurement] = rebuilt
            return rebuilt

        return default

    def update_after_fetch(self, result: FetchResult, now: int) -> bool:
        """
        Record that a fetch attempt was made
        """

        entry = self.data.setdefault(result.measurement, {})
        entry["last_try"] = now

    @property
    def data(self) -> dict:
        return self._state

    def _compute_policy(self, measurement: str, timestamp: int) -> dict:
        entry = self.get(measurement)

        # No state or no timestamp → first ever point, must write
        if entry is None:
            return {"skipped": False, "reason": "first"}

        first_ts = entry.get("first_timestamp")
        if first_ts is None:
            return {"skipped": False, "reason": "first"}

        last_ts = entry.get("last_timestamp")
        if last_ts is None:
            return {"skipped": False, "reason": "first"}

        # Before known window → must write
        if timestamp < first_ts:
            return {"skipped": False, "reason": "before-window"}

        # After known window → must write
        if timestamp > last_ts:
            return {"skipped": False, "reason": "new"}

        # Inside window → skip
        if timestamp == last_ts:
            return {"skipped": True, "reason": "unchanged"}

        return {"skipped": True, "reason": "inside-window"}

    def update_range(self, measurement: str, first: int, last: int) -> None:
        """
        Update the saved range after a batch has been ingested
        """
        # when this is called, the entry is always there
        entry = self._state[measurement]
        last_saved = entry.get("last_timestamp")
        if last_saved is None or last > last_saved:
            entry["last_timestamp"] = last
        first_saved = entry.get("first_timestamp")
        if first_saved is None or first < first_saved:
            entry["first_timestamp"] = first

    def ingest(self, write: TimeseriesWrite) -> TimeseriesResult:
        """
        Ingest a new metric:
        - check if write is needed, if not bail out
        - append to WAL (ingestion succeeds here)
        - flush WAL oldest → newest to timeseries_client
        - dequeue flushed entries
        - on first write failure, stop and return that result

        Note: first and last timestamps are not updated, that needs to happen after the batch was done
        """

        policy = self._compute_policy(write.measurement, write.timestamp)
        if policy["skipped"]:
            return TimeseriesResult.ok_payload(write.measurement, None, meta=policy)
        # Durable accept: enqueue
        self._wal.enqueue(write)

        entry = self._state.setdefault(write.measurement, {})
        entry["fields"] = write.fields

        # Flush WAL FIFO
        while True:
            oldest = self._wal.peek()
            if oldest is None:
                break

            result = self._timeseries_client.write(oldest)

            if not result.ok:
                # stop flushing, keep WAL intact. Always give back requested entry even if an older failed
                # (because that implies the requested entry failed as well)
                return result

            # successful write → remove from WAL
            self._wal.dequeue()

        return TimeseriesResult.ok_payload(write.measurement, write, meta=policy)

    def iter_metrics(self) -> Iterable[dict]:
        """
        Yield (metric_name, entry_dict) for all metrics currently in state.

        This does NOT trigger lazy rebuild. It only iterates over what is
        already present in _state. CompositeEngine uses this to build the
        namespace for evaluation.
        """
        yield from self._state.items()

    def get_last_timestamp(self, measurement: str) -> int | None:
        """
        Return the last_timestamp for a metric, performing lazy rebuild if needed.
        """
        entry = self.get(measurement)
        if entry is None:
            return None
        return entry.get("last_timestamp")

    def update_composite(self, measurement: str, fields: dict, timestamp: int) -> None:
        """
        Update a composite metric in state.

        This does NOT write to WAL or Influx — composites are derived data.
        They are stored directly in state and persisted on state.save().
        """
        self._state[measurement] = {
            "fields": fields,
            "last_timestamp": timestamp,
        }

    def _rebuild_measurement_state(self, measurement: str) -> dict | None:

        bucket = self._bucket_for(measurement)
        wal_entries = [e for e in self._wal.read_all() if e["measurement"] == measurement]

        # no need to check property existence as read_all already removes invalid entries
        wal_first = min((e["timestamp"] for e in wal_entries), default=None)
        wal_last = max((e["timestamp"] for e in wal_entries), default=None)
        wal_fields = next((e["fields"] for e in wal_entries if e["timestamp"] == wal_last), None)

        # Collect Influx timestamps
        influx_first_point = self._timeseries_client.read_first(bucket, measurement)
        influx_last_point = self._timeseries_client.read_last(bucket, measurement)

        influx_first = influx_first_point.payload.timestamp if influx_first_point.payload else None
        influx_last = influx_last_point.payload.timestamp if influx_last_point.payload else None
        influx_fields = influx_last_point.payload.fields if influx_last_point.payload else None

        # If nothing exists anywhere, bail out
        if wal_first is None and influx_first is None:
            return None

        # Combine earliest and latest
        first_timestamp = min(timestamp for timestamp in (wal_first, influx_first) if timestamp is not None)
        last_timestamp = max(timestamp for timestamp in (wal_last, influx_last) if timestamp is not None)

        # Pick fields from the newest point
        if wal_last is not None and (influx_last is None or wal_last >= influx_last):
            fields = wal_fields
        else:
            fields = influx_fields

        return {
            "fields": fields,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
        }
