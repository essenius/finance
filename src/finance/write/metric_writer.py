# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/write/metric_writer.py


from finance.common.log_mixin import LogMixin


class MetricWriter(LogMixin):
    def __init__(self, state):
        self._state = state

    def should_write(self, measurement, timestamp: int) -> dict:
        """Return {"ok": bool, "reason": str} describing write policy."""
        entry = self._state.get(measurement)
        if entry is None:
            return {"ok": True, "reason": "first-time"}

        last_timestamp = entry["last_timestamp"]

        if timestamp > last_timestamp:
            return {"ok": True, "reason": "new"}

        if timestamp == last_timestamp:
            return {"ok": False, "reason": "unchanged"}

        return {"ok": False, "reason": "older"}

    def write(self, bucket, measurement, fields, timestamp):
        """
        bucket: InfluxDB bucket (ignored for V1)
        measurement: e.g. "brent", "gold", etc.
        fields: dict of field values (multi-field supported)
        timestamp: timestamp (int)
        """

        policy = self.should_write(measurement, timestamp)

        entry = {
            "bucket": bucket,
            "measurement": measurement,
            "fields": fields,
            "timestamp": timestamp,
        }

        if not policy["ok"]:
            return {"ok": False, "status": "skipped", "reason": f"skipped: {policy['reason']} sample", **entry}

        result = self._state.ingest(entry)

        return {
            **result,
            "reason": result.get("reason") or f"wrote {policy['reason']} sample",
        }
