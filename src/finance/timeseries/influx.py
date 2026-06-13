# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/influx.py

from __future__ import annotations

import re
import time

from dateutil.parser import isoparse
from requests import Response, Session

from ..common.model import BatchWriteResult, Result, TimeseriesResult, TimeseriesWrite
from .config import ConfigFactory, InfluxConfig


class InfluxBackend:
    @classmethod
    def from_config(cls, config: dict, secrets: dict, now=None) -> Result[InfluxBackend]:
        try:
            factory = ConfigFactory(config, secrets)
            session = Session()
            influx_config = factory.create(session)
            if not influx_config.ok:
                return influx_config
            warnings = influx_config.warnings
            return Result.ok_payload(cls(session, influx_config.payload, now), warnings)

        except Exception as e:
            return Result.fail("Influx backend initialization failed", e)

    def __init__(self, session: Session, config: InfluxConfig, now=None):
        self.session = session
        self.cfg = config
        self.now = now or time.time

        # batching state
        self._pending: list[TimeseriesWrite] = []
        self._pending_bucket: str | None = None
        self._last_flush_time: float = 0.0

    # -------------------------
    # Reading
    # -------------------------

    def read_one(self, bucket: str, measurement: str, asc: bool) -> TimeseriesResult:
        """
        Unified read API for InfluxDB 1.x and 2.x.

        bucket: string (bucket for InfluxDB 2.x, retention policy for InfluxDB 1.x)
        measurement: string
        asc: whether to sort ascending (get first) or descending (get last)
        """
        try:
            if self.cfg.version == 2:
                raw = self._read_one_v2(bucket, measurement, asc)
                return TimeseriesResult.ok_payload(measurement, self._parse_v2(bucket, measurement, raw))
            else:
                raw = self._read_one_v1(bucket, measurement, asc)
                return TimeseriesResult.ok_payload(measurement, self._parse_v1(bucket, measurement, raw))

        except Exception as e:
            return TimeseriesResult.fail(measurement, "Influx read failed", e)

    def read_first(self, bucket: str, measurement: str) -> TimeseriesResult:
        return self.read_one(bucket, measurement, asc=True)

    def read_last(self, bucket: str, measurement: str) -> TimeseriesResult:
        return self.read_one(bucket, measurement, asc=False)

    def _read_one_v2(self, bucket: str, measurement: str, asc: bool) -> dict:
        url = f"{self.cfg.base_url}/query"
        query = f'''
from(bucket: "{bucket}")
  |> range(start:0)
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> sort(columns: ["_time"], desc: {str(not asc).lower()})
  |> limit(n: 1)
'''

        params = {"org": self.cfg.org}
        headers = {
            "Authorization": f"Token {self.cfg.read_token}",
            "Content-Type": "application/vnd.flux",
        }

        r = self.session.post(url, params=params, data=query, headers=headers, timeout=5, verify=self.cfg.ssl_verify)
        r.raise_for_status()
        return r.json()

    def _read_one_v1(self, bucket: str, measurement: str, asc: bool) -> dict:
        url = f"{self.cfg.base_url}/query"
        order = "ASC" if asc else "DESC"
        q = f'SELECT * FROM "{bucket}"."{measurement}" ORDER BY time {order} LIMIT 1'
        params = {"db": self.cfg.db, "q": q}
        r = self.session.get(url, params=params, auth=self.cfg.auth, timeout=5, verify=self.cfg.ssl_verify)
        r.raise_for_status()
        return r.json()

    # -------------------------
    # Parsing
    # -------------------------

    def _parse_v2(self, bucket: str, measurement: str, data: dict) -> TimeseriesWrite | None:

        tables = data.get("tables", [])
        if not tables:
            return None

        # Flux returns one record per field
        fields = {}
        tags = {}
        timestamp = None

        for table in tables:
            for record in table.get("records", []):
                if record.get("_measurement") != measurement:
                    continue

                if timestamp is None:
                    timestamp = int(isoparse(record["_time"]).timestamp())

                field = record.get("_field")
                value = record.get("_value")

                # Skip malformed Flux records
                if field is None or value is None:
                    continue

                fields[field] = value

                # Extract tags (everything except Flux internals)
                for k, v in record.items():
                    if k.startswith("_"):
                        continue
                    if k in ["result", "table"]:
                        continue
                    tags[k] = v

        if not fields:
            return None

        return TimeseriesWrite(measurement=measurement, fields=fields, tags=tags, timestamp=timestamp, bucket=bucket)

    def _parse_v1(self, bucket: str, measurement: str, data: dict) -> TimeseriesWrite | None:
        results = data.get("results", [])
        if not results:
            return None

        series = results[0].get("series", [])
        if not series:
            return None

        row = series[0]
        columns = row.get("columns")
        if not columns:
            return None
        values_list = row.get("values", [])
        if not values_list:
            return None

        values = values_list[0]

        record = dict(zip(columns, values, strict=True))

        # Extract timestamp
        timestamp = int(isoparse(record["time"]).timestamp())

        fields = {}
        tags = {}

        for key, value in record.items():
            if key == "time":
                continue

            # InfluxQL rule: tags are always strings. Assume there are no string fields
            if isinstance(value, str):
                tags[key] = value
            else:
                fields[key] = value

        return TimeseriesWrite(measurement=measurement, fields=fields, tags=tags, timestamp=timestamp, bucket=bucket)

    # -------------------------
    # Writing
    # -------------------------

    def write(self, entry: TimeseriesWrite) -> TimeseriesResult:
        """
        write a time series entry to InfluxDB
        """
        tag_str = ""
        if entry.tags:
            tag_str = "," + ",".join(f"{k}={v}" for k, v in entry.tags.items())
        field_str = ",".join(f"{k}={v}" for k, v in entry.fields.items())
        line = f"{entry.measurement}{tag_str} {field_str} {entry.timestamp}"

        base_params = {
            "data": line,
            "headers": {"Content-Type": "text/plain; charset=utf-8"},
            "timeout": 5,
            "verify": self.cfg.ssl_verify,
        }

        try:
            if self.cfg.version == 2:
                base_params["headers"]["Authorization"] = f"Token {self.cfg.write_token}"
                url = f"{self.cfg.base_url}/write?org={self.cfg.org}&bucket={entry.bucket}&precision=s"
                r = self.session.post(url, **base_params)
            else:
                url = f"{self.cfg.base_url}/write?db={self.cfg.db}&rp={entry.bucket}&precision=s"
                r = self.session.post(url, auth=self.cfg.auth, **base_params)

            r.raise_for_status()
            return TimeseriesResult.ok_payload(entry.measurement, None)

        except Exception as e:
            return TimeseriesResult.fail(
                entry.measurement, "Influx write failed", e, meta={"attempted_timestamp": entry.timestamp}
            )

    def write_entry(self, entry: TimeseriesWrite) -> TimeseriesResult:
        if self.cfg.version == 1 or self.cfg.max_batch_size <= 1:
            # v1 never batches, and if the user doesn't want it, we don't do it either
            return self.write(entry)

        self._pending.append(entry)

        if self._pending_bucket is None:
            self._pending_bucket = entry.bucket

        if self._should_flush(entry.bucket):
            result = self._flush_pending()
            if not result.ok:
                meta = {
                    "failed_indices": result.failed,
                    "succeeded_indices": result.succeeded,
                }
                if result.meta:
                    meta["exception"] = result.meta.get("exception")
                return TimeseriesResult.fail(
                    measurement=entry.measurement,
                    reason="Batch write failed",
                    error="InfluxDB rejected one or more entries",
                    warnings=result.warnings,
                    meta=meta,
                )

        return TimeseriesResult.ok_payload(entry.measurement, entry)

    def _flush_pending(self) -> BatchWriteResult:
        """
        Flush the current pending batch (InfluxDB v2 only).
        Invariant: after this call, _pending is empty and _pending_bucket is None on success.
        On partial failure, _pending contains the failed entries and _pending_bucket is preserved.
        On catastrophic failure, _pending contains all entries
        """

        # Nothing to flush → success
        if not self._pending:
            return BatchWriteResult(ok=True, succeeded=[], failed=[])

        # Snapshot the batch
        entries = self._pending
        count = len(entries)

        try:
            result = self.batch_write_v2(entries)

            if result.ok:
                # full success → clear everything
                self._pending = []
                self._pending_bucket = None
                self._last_flush_time = self.now()
                return result

            # partial failure → keep only failed entries
            failed_indices = set(result.failed)
            self._pending = [entries[i] for i in failed_indices]

            # bucket stays the same if failed entries remain
            self._pending_bucket = self._pending[0].bucket if self._pending else None

            # update last flush time only if something succeeded
            if result.succeeded:
                self._last_flush_time = time.time()

            return result

        except Exception as e:
            # catastrophic failure → keep all entries
            return BatchWriteResult(
                ok=False,
                succeeded=[],
                failed=list(range(count)),
                meta={"exception": str(e)},
            )

    def batch_write_v2(self, entries: list[TimeseriesWrite]) -> BatchWriteResult:
        """
        Batch write for InfluxDB v2.
        Returns BatchWriteResult with succeeded/failed indices.
        """

        if not entries:
            return BatchWriteResult(ok=True, succeeded=[], failed=[])

        # --- Build multi-line payload ---
        lines = []
        for e in entries:
            tag_str = ""
            if e.tags:
                tag_str = "," + ",".join(f"{k}={v}" for k, v in e.tags.items())
            field_str = ",".join(f"{k}={v}" for k, v in e.fields.items())
            lines.append(f"{e.measurement}{tag_str} {field_str} {e.timestamp}")

        payload = "\n".join(lines)

        url = f"{self.cfg.base_url}/write?org={self.cfg.org}&bucket={entries[0].bucket}&precision=s"
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "Authorization": f"Token {self.cfg.write_token}",
        }

        count = len(entries)
        all_indices = list(range(count))
        try:
            r = self.session.post(url, data=payload, headers=headers, timeout=5, verify=self.cfg.ssl_verify)

            # --- Full success ---
            if r.status_code == 204:
                return BatchWriteResult(ok=True, succeeded=all_indices, failed=[])

            # --- Partial or full failure ---
            failed = self._parse_v2_batch_error(r, all_indices)
            succeeded = [i for i in all_indices if i not in failed]
            return BatchWriteResult(ok=False, succeeded=succeeded, failed=failed)

        except Exception as e:
            # Network or unexpected error → full failure
            return BatchWriteResult(ok=False, succeeded=[], failed=all_indices, meta={"exception": str(e)})

    def _should_flush(self, next_bucket: str) -> bool:
        # No pending → nothing to flush
        if not self._pending:
            return False

        # 1. Bucket switch → must flush
        if self._pending_bucket is not None and next_bucket != self._pending_bucket:
            return True

        # 2. Size threshold
        if len(self._pending) >= self.cfg.max_batch_size:
            return True

        # 3. Age threshold
        if self.now() - self._last_flush_time >= self.cfg.max_batch_age_seconds:
            return True

        return False

    # ---------------------------------------------------------
    # Error handling helper
    # ---------------------------------------------------------

    def _parse_v2_batch_error(self, response: Response, all_indices: list[int]) -> list[int]:
        """
        Extract failing line indices from InfluxDB v2 error responses.
        Returns [] if no indices found.
        """

        text = response.text or ""
        failed = set()

        # --- Pattern 1: "points 1,3 rejected" ---
        m = re.search(r"points ([0-9, ]+) rejected", text)
        if m:
            nums = m.group(1)
            for n in nums.split(","):
                n = n.strip()
                failed.add(int(n))  # always an int, as per the regex
            return sorted(failed)

        # --- Pattern 2: {"lineErrors":[{"line":3}, ...]} ---
        try:
            data = response.json()
            if isinstance(data, dict) and "lineErrors" in data:
                for item in data["lineErrors"]:
                    if isinstance(item, dict) and "line" in item:
                        failed.add(int(item["line"]))
                return sorted(failed)

        except Exception:
            pass  # ignore JSON errors

        return all_indices
