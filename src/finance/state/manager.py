# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/manager.py

import json
import shutil
import tempfile
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from ..common.model import FetchResult, TimeseriesResult, TimeseriesWrite
from ..state.wal import JsonlWAL
from ..timeseries import InfluxBackend


class State:
    def __init__(self, timeseries_client: InfluxBackend, wal: JsonlWAL, path: Path, bucket_for: Callable[[str], str]):
        self._timeseries_client = timeseries_client
        self._wal = wal
        self._path = path
        self._state: dict[str, dict] = load_state(self._path)
        self._bucket_for = bucket_for

    def save(self) -> None:
        save_state(self._state, self._path)

    def get(self, measurement: str, default: dict | None = None) -> dict | None:
        entry = self._state.get(measurement)
        if entry is not None:
            return entry

        rebuilt = rebuild_measurement_state(
            self._bucket_for(measurement), measurement, self._wal, self._timeseries_client
        )
        if rebuilt:
            self._state[measurement] = rebuilt
            return rebuilt

        return default

    def update_after_fetch(self, result: FetchResult) -> bool:
        """
        Record that a fetch attempt was made, and report whether the provider
        appears to have newer data than what we have already persisted.

        Returns:
            True  - provider returned data newer than our last persisted timestamp
            False - no new data, fetch failed, or provider returned nothing
        """

        now = int(time.time())

        # Always update last_try
        entry = self.data.setdefault(result.measurement, {})
        entry["last_try"] = now

        if not result.ok or not result.payload:
            return False

        # Determine if provider has newer data than what we have persisted
        newest_provider_ts = max(p.timestamp for p in result.payload)
        last_persisted_ts = entry.get("last_timestamp")

        return last_persisted_ts is None or newest_provider_ts > last_persisted_ts


    @property
    def data(self) -> dict:
        return self._state


    def _compute_policy(self, measurement: str, timestamp: int) -> dict:
        entry = self._state.get(measurement)
        if entry is None:
            return {"skipped": False, "reason": "first-time"}

        last_timestamp = entry["last_timestamp"]

        if timestamp > last_timestamp:
            return {"skipped": False, "reason": "new"}

        if timestamp == last_timestamp:
            return {"skipped": True, "reason": "unchanged"}

        return {"skipped": True, "reason": "older"}


    def ingest(self, write: TimeseriesWrite) -> TimeseriesResult:
        """
        Ingest a new metric:
        - check if write is needed, if not bail out
        - append to WAL (ingestion succeeds here)
        - update in memory state immediately
        - flush WAL oldest → newest to timeseries_client
        - dequeue flushed entries
        - on first write failure, stop and return that result
        """

        # State reflects ingested value immediately

        policy = self._compute_policy(write.measurement, write.timestamp)
        if policy["skipped"]:
            return TimeseriesResult.ok_payload(write.measurement, None, meta=policy)
        # Durable accept: enqueue
        self._wal.enqueue(write)

        # State reflects ingested value immediately

        entry = self._state.setdefault(write.measurement, {})
        entry["fields"] = write.fields
        entry["last_timestamp"] = write.timestamp

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


def load_state(path: Path) -> dict:
    """
    Load state.json from the project root unless an explicit path is provided.
    """

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass  # corrupted or unreadable

    return {}


def save_state(state: dict, path: Path) -> None:
    """
    Save state atomically to avoid corruption.
    """

    tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    try:
        json.dump(state, tmp, indent=2)
        tmp.flush()
        tmp.close()
        shutil.move(tmp.name, path)
    except Exception:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass
        raise


def rebuild_measurement_state(
    bucket: str, measurement: str, wal: JsonlWAL, influx_client: InfluxBackend
) -> dict | None:
    """
    Rebuild state for a single measurement using:
    1. WAL (most recent entry wins)
    2. Influx (latest point)
    """

    # Check WAL
    wal_entries = [e for e in wal.read_all() if e.measurement == measurement]

    if wal_entries:
        newest = max(wal_entries, key=lambda e: e.timestamp)
        return {
            "fields": newest.fields,
            "last_timestamp": newest.timestamp,
        }

    # Not in WAL, query Influx
    latest = influx_client.read(bucket, measurement)
    if latest.ok:
        return {
            "fields": latest.payload.fields,
            "last_timestamp": latest.payload.timestamp,
        }

    # No history
    return None
