# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/write/influx.py

import requests


class InfluxWriter:
    def __init__(self, secrets: dict):
        """
        base_url: e.g. "https://nas.local:8086"
        db:       InfluxDB database name
        user:     optional username
        password: optional password
        ca_cert:  path to CA certificate file, or None to disable verification
        """
        url = secrets["url"].rstrip("/")
        db = secrets["db"]
        user = secrets.get("user")
        password = secrets.get("password")
        ca_cert = secrets.get("ca_cert")

        # Prebuild the write URL
        self.write_url = f"{url}/write?db={db}&precision=s"

        # Precompute auth tuple or None
        if user and password:
            self.auth = (user, password)
        else:
            self.auth = None

        # Precompute TLS verification mode
        # - If ca_cert is a path → use it
        # - If None → disable verification
        self.verify = ca_cert if ca_cert else False

    def write(self, measurement, fields, timestamp):
        """
        measurement: string
        fields: dict, e.g. {"value": 123.45}
        timestamp: int (unix seconds)
        """

        # Convert fields dict to line protocol
        field_str = ",".join(f"{k}={v}" for k, v in fields.items())
        line = f"{measurement} {field_str} {timestamp}"

        try:
            r = requests.post(self.write_url, data=line, auth=self.auth, timeout=5, verify=self.verify)
            r.raise_for_status()
        except Exception as e:
            print(f"Influx write failed for {measurement}: {e}")
