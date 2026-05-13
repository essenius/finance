# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/write/influx.py

import requests

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


class InfluxWriter:
    def __init__(self, secrets: dict):

        print(f"Initializing InfluxWriter with secrets: {secrets}")  # Debug print --- IGNORE ---
        url = secrets["url"].rstrip("/")
        db = secrets["db"]
        user = secrets.get("user", None)
        password = secrets.get("password", None)
        cert = secrets.get("cert", None)
        verify = secrets.get("verify", "true")

        # Prebuild the write URL
        self.write_url = f"{url}/write?db={db}&precision=s"

        # Precompute auth tuple or None
        if user and password:
            self.auth = (user, password)
        else:
            self.auth = None

        self.session = requests.Session()
        self.verify = configure_verify(self.session, verify, cert)

        print(
            f"InfluxWriter initialized with write_url: {self.write_url}, auth: {'set' if self.auth else 'none'}, verify: {self.verify}"
        )  # Debug print --- IGNORE ---

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
            r = self.session.post(self.write_url, data=line, auth=self.auth, timeout=5, verify=self.verify)
            r.raise_for_status()
        except Exception as e:
            print(f"Influx write failed for {measurement}: {e}")
            for err in e.args:
                print(err)
