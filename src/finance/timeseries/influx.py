# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/write/influx.py

from dataclasses import dataclass

import requests
from dateutil.parser import isoparse

from finance.common.introspection import here
from finance.common.model import Result, TimeseriesResult, TimeseriesWrite

from .ssl_context_adapter import SSLContextAdapter, make_legacy_ssl_context


@dataclass(frozen=True)
class InfluxConfig:
    ssl_verify: bool | str
    version: int
    base_url: str
    org: str | None = None
    write_token: str | None = None
    read_token: str | None = None
    db: str | None = None
    auth: tuple[str, str] | None = None


def configure_verify(session, mode, cert):
    mode = mode.lower()

    # --- Strict mode: system CA store ---
    if mode == "true":
        return cert if cert else True

    # --- Insecure mode ---
    if mode == "false":
        return False

    # --- Pinned mode: cert required ---
    if mode == "pinned":
        if not cert:
            raise ValueError("Pinned mode requires a certificate path")
        return cert

    # --- Legacy mode: cert optional ---
    if mode == "legacy":
        if cert:
            # Legacy CA mode
            ctx = make_legacy_ssl_context(cert)
        else:
            # Legacy system CA mode
            ctx = make_legacy_ssl_context("/etc/ssl/certs/ca-certificates.crt")

        session.mount("https://", SSLContextAdapter(ctx))
        return True  # verify=True but SSLContext overrides behavior

    raise ValueError(f"Unknown verify mode: {mode}")


class InfluxBackend:
    @classmethod
    def from_secrets(cls, secrets: dict) -> Result["InfluxBackend"]:
        try:
            context = { "location": here() }
            url = secrets["url"].rstrip("/")
            cert = secrets.get("cert")
            ssl_verify_mode = secrets.get("ssl_verify", "true")

            session = requests.Session()
            ssl_verify = configure_verify(session, ssl_verify_mode, cert)
            warnings = []
            config = None
            if "org" in secrets:
                base_url = f"{url}/api/v2/write"
                config = InfluxConfig(
                    ssl_verify=ssl_verify,
                    version=2,
                    base_url=base_url,
                    org=secrets["org"],
                    write_token=secrets["write-token"],
                    read_token=secrets["read-token"],
                )

            if "db" in secrets:
                if "org" in secrets:
                    warnings.append("secrets contain both 'org' (InfluxDb 2.x) and 'db' (InfluxDB 1.x), ignoring 'db'")
                else:
                    base_url = f"{url}/write"
                    user = secrets.get("user")
                    password = secrets.get("password")
                    auth = (user, password) if user and password else None
                    config = InfluxConfig(
                        ssl_verify=ssl_verify,
                        version=1,
                        base_url=base_url,
                        db=secrets["db"],
                        auth=auth,
                    )

            if config is None:
                return Result.fail("Secrets must contain either 'org' or 'db'", meta=context)

            return Result.ok_payload(cls(session, config), warnings, context)

        except Exception as e:
            return Result.fail("Influx backend initialization failed", e, meta=context)

    def __init__(self, session: requests.Session, config: InfluxConfig):
        print("InfluxBackend __init__ CALLED")
        self.session = session
        self.cfg = config

    def read(self, bucket: str, measurement: str) -> TimeseriesResult:
        """
        Unified read API for InfluxDB 1.x and 2.x.

        bucket: string (bucket for InfluxDB 2.x, retention policy for InfluxDB 1.x)
        measurement: string
        start, stop: unix timestamps (seconds)
        """
        try:
            if self.cfg.version == 2:
                raw = self._read_v2(bucket, measurement)
                return TimeseriesResult.ok_payload(measurement, self._parse_v2(bucket, measurement, raw))
            else:
                raw = self._read_v1(bucket, measurement)
                return TimeseriesResult.ok_payload(measurement, self._parse_v1(bucket, measurement, raw))

        except Exception as e:
            return TimeseriesResult.fail(measurement, "Influx read failed", e)

    def _read_v2(self, bucket: str, measurement: str) -> dict:
        url = self.cfg.base_url.replace("/write", "/query")

        query = f'''
from(bucket: "{bucket}")
  |> range(start:0)
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> last()
'''

        params = {"org": self.cfg.org}
        headers = {
            "Authorization": f"Token {self.cfg.read_token}",
            "Content-Type": "application/vnd.flux",
        }

        r = self.session.post(url, params=params, data=query, headers=headers, timeout=5, verify=self.cfg.ssl_verify)
        r.raise_for_status()
        return r.json()

    def _read_v1(self, bucket, measurement) -> dict:
        url = self.cfg.base_url.replace("/write", "/query")
        q = f'SELECT * FROM "{bucket}"."{measurement}" ORDER BY time DESC LIMIT 1'
        params = {"db": self.cfg.db, "q": q}
        r = self.session.get(url, params=params, auth=self.cfg.auth, timeout=5, verify=self.cfg.ssl_verify)
        r.raise_for_status()
        return r.json()

    def _parse_v2(self, bucket: str, measurement: str, data: dict) -> TimeseriesWrite | None:

        tables = data.get("tables", [])
        if not tables:
            return None

        # Flux returns one record per field
        fields = {}
        tags = {}
        timestamp = None

        for table in tables:
            for rec in table.get("records", []):
                if rec.get("_measurement") != measurement:
                    continue

                if timestamp is None:
                    timestamp = int(isoparse(rec["_time"]).timestamp())

                field = rec.get("_field")
                value = rec.get("_value")

                # Skip malformed Flux records
                if field is None or value is None:
                    continue

                fields[field] = value

                # Extract tags (everything except Flux internals)
                for k, v in rec.items():
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
                url = f"{self.cfg.base_url}?org={self.cfg.org}&bucket={entry.bucket}&precision=s"
                r = self.session.post(url, **base_params)
            else:
                url = f"{self.cfg.base_url}?db={self.cfg.db}&rp={entry.bucket}&precision=s"
                r = self.session.post(url, auth=self.cfg.auth, **base_params)

            r.raise_for_status()
            return TimeseriesResult.ok_payload(entry.measurement, None)

        except Exception as e:
            return TimeseriesResult.fail(entry.measurement, "Influx write failed", e, meta={"attempted_timestamp": entry.timestamp})
