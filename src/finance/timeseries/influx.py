# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/write/influx.py

import requests

from finance.common.log_mixin import LogMixin

from .ssl_context_adapter import SSLContextAdapter, make_legacy_ssl_context


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


class InfluxWriter(LogMixin):
    def __init__(self, secrets: dict):

        url = secrets["url"].rstrip("/")
        cert = secrets.get("cert", None)
        ssl_verify = secrets.get("ssl_verify", "true")

        self.session = requests.Session()
        self.ssl_verify = configure_verify(self.session, ssl_verify, cert)

        self.is_v2 = "org" in secrets
        self.is_v1 = "db" in secrets

        if self.is_v1 and self.is_v2:
            self.warning("secrets contain both 'org' (InfluxDb 2.x) and 'db' (InfluxDB 1.x), ignoring 'db'")

        if self.is_v2:
            # InfluxDB 2.x
            self.org = secrets["org"]
            self.token = secrets["token"]
            self.base_url = f"{url}/api/v2/write"
            self.headers = {
                "Authorization": f"Token {self.token}",
                "Content-Type": "text/plain; charset=utf-8",
            }

        elif self.is_v1:
            # InfluxDB 1.x
            self.db = secrets["db"]
            user = secrets.get("user")
            password = secrets.get("password")
            self.base_url = f"{url}/write"
            self.auth = (user, password) if user and password else None
            self.headers = {
                "Content-Type": "text/plain; charset=utf-8",
            }

        else:
            raise ValueError("Secrets must contain either 'org' (InfluxDB 2.x) or 'db' (InfluxDB 1.x)")

        self.debug("InfluxWriter initialized", base_url=self.base_url, verify=self.ssl_verify)

    def write(self, bucket, measurement, fields, timestamp, tags=None):
        """
        bucket: string (InfluxDB 2.x only, ignored in 1.x)
        measurement: string
        fields: dict, e.g. {"value": 123.45}
        timestamp: int (unix seconds)
        """
        tag_str = ""
        if tags:
            tag_str = "," + ",".join(f"{k}={v}" for k, v in tags.items())
        field_str = ",".join(f"{k}={v}" for k, v in fields.items())
        line = f"{measurement}{tag_str} {field_str} {timestamp}"

        base_params = {
            "data": line,
            "headers": self.headers,
            "timeout": 5,
            "verify": self.ssl_verify,
        }
        try:
            if self.is_v2:
                url = f"{self.base_url}?org={self.org}&bucket={bucket}&precision=s"
                r = self.session.post(url, **base_params)
            else:
                url = f"{self.base_url}?db={self.db}&precision=s"
                r = self.session.post(url, auth=self.auth, **base_params)

            r.raise_for_status()
            return {"ok": True}

        except Exception as e:
            self.error("Influx write failed", measurement=measurement, exception=e, args=e.args)
            return {"ok": False, "error": str(e)}
