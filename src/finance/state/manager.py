# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/manager.py

import json
import shutil
import tempfile
from pathlib import Path


class State:
    def __init__(self, timeseries_client, wal, path: Path):
        self._timeseries_client = timeseries_client
        self._wal = wal
        self._path = path
        self._state: dict[str, dict] = load_state(self._path)

    def save(self) -> None:
        save_state(self._state, self._path)

    def get(self, measurement) -> dict | None:
        entry = self._state.get(measurement)
        if entry is not None:
            return entry

        rebuilt = rebuild_measurement_state(measurement, self._wal, self._timeseries_client)
        if rebuilt:
            self._state[measurement] = rebuilt
            return rebuilt

        return None

    @property
    def data(self):
        return self._state

    def ingest(self, entry: dict) -> dict:
        """
        Ingest a new metric:

        - append to WAL (ingestion succeeds here)
        - update in‑memory state immediately
        - flush WAL oldest → newest to timeseries_client
        - dequeue flushed entries
        - on first write failure, stop and return that result
        """

        # Durable accept: enqueue
        self._wal.enqueue(entry)

        # State reflects ingested value immediately
        self._state[entry["measurement"]] = { "fields": entry["fields"], "last_timestamp": entry["timestamp"] }

        # Flush WAL FIFO
        while True:
            oldest = self._wal.peek()
            if oldest is None:
                break

            result = self._timeseries_client.write(
                oldest["bucket"],
                oldest["measurement"],
                oldest["fields"],
                oldest["timestamp"],
            )

            if not result.get("ok", False):

                # stop flushing, keep WAL intact. Always give back requested entry even if an older failed
                # (because that implies the requested entry failed as well)

                return  {
                    "ok": False,
                    "status": "error",
                    "reason": f"failed to write: {result.get('error')}",
                    "failed_timestamp": oldest["timestamp"],
                    **entry,
                }

            # successful write → remove from WAL
            self._wal.dequeue()

        return {
            "ok": True,
            "status": "written",
            **entry,
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


def save_state(state: dict, path: Path):
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

def rebuild_measurement_state(measurement, wal, influx_client):
    """
    Rebuild state for a single measurement using:
    1. WAL (most recent entry wins)
    2. Influx (latest point)
    3. None (no history)
    """

    # Check WAL
    wal_entries = [
        e for e in wal.read_all()
        if e["measurement"] == measurement
    ]

    if wal_entries:
        newest = max(wal_entries, key=lambda e: e["timestamp"])
        return {
            "fields": newest["fields"],
            "last_timestamp": newest["timestamp"],
        }

    # Not in WAL, query Influx
    latest = influx_client.query_latest(measurement)
    if latest:
        return {
            "fields": latest.fields,
            "last_timestamp": latest.timestamp,
        }

    # No history
    return None
