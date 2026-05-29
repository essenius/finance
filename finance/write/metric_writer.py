# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/write/metric_writer.py


from finance.common.log_mixin import LogMixin


class MetricWriter(LogMixin):
    def __init__(self, influx_writer, wal):
        self.influx = influx_writer
        self.wal = wal

    @staticmethod
    def should_write(entry: dict, timestamp: int) -> dict:
        """Return {"ok": bool, "reason": str} describing write policy."""

        # No previous state → treat as new sample
        if not entry or entry.get("last_timestamp") is None:
            return {"ok": True, "reason": "first-time"}

        last_timestamp = entry["last_timestamp"]

        if timestamp > last_timestamp:
            return {"ok": True, "reason": "new"}

        if timestamp == last_timestamp:
            return {"ok": False, "reason": "unchanged"}

        return {"ok": False, "reason": "older"}

    @staticmethod
    def make_entry(bucket, measurement, fields, timestamp):
        return {
            "bucket": bucket,
            "measurement": measurement,
            "fields": fields,
            "timestamp": timestamp,
        }

    def write_metric(self, bucket, measurement, fields, timestamp, state):
        """
        bucket: InfluxDB bucket (ignored for V1)
        measurement: e.g. "brent", "gold", etc.
        fields: dict of field values (multi-field supported)
        timestamp: timestamp (int)
        state: dict tracking last written values
        """

        measurement_state = state.setdefault(measurement, {})

        wal_entry = self.make_entry(bucket, measurement, fields, timestamp)

        policy = self.should_write(measurement_state, timestamp)
        if not policy["ok"]:
            return {"ok": False, "status": "skipped", "reason": f"skipped: {policy['reason']} sample", **wal_entry}

        # Add new sample to WAL
        self.wal.enqueue(wal_entry)

        # we've now persisted the entry even if we can't put it in influx, so we can update the state
        measurement_state["fields"] = {**fields}
        measurement_state["last_timestamp"] = timestamp

        # try to write samples in WAL to Influx
        while True:
            oldest = self.wal.peek()
            if oldest is None:
                break

            result = self.influx.write(oldest["bucket"], oldest["measurement"], oldest["fields"], oldest["timestamp"])

            if not result["ok"]:
                # stop flushing, keep WAL intact. Always give back requested entry even if an older failed
                # (because that implies the requested entry failed as well)
                return {
                    "ok": False,
                    "status": "error",
                    "reason": f"failed to write: {result.get('error')}",
                    "failed_timestamp": oldest["timestamp"],
                    **wal_entry,
                }

            self.wal.dequeue()

        return {
            "ok": True,
            "status": "written",
            "reason": f"wrote {policy['reason']} sample",
            **wal_entry,
            "fields": {**fields},
        }
