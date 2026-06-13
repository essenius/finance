# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/config.py

from dataclasses import dataclass

from finance.common.model import Result

from .ssl_context_adapter import SSLContextAdapter, make_legacy_ssl_context


@dataclass(frozen=True)
class InfluxConfig:
    ssl_verify: bool | str
    version: int
    base_url: str
    max_batch_size: int
    max_batch_age_seconds: float
    org: str | None = None
    write_token: str | None = None
    read_token: str | None = None
    db: str | None = None
    auth: tuple[str, str] | None = None


class ConfigFactory:
    def __init__(self, config: dict, secrets: dict):
        self.config = config
        self.secrets = secrets

    def get_config(self, key, default=None):
        # YAML overrides env
        if key in self.config:
            return self.config[key]
        if key in self.secrets:
            return self.secrets[key]
        return default

    def create(self, session) -> Result[InfluxConfig]:
        # URL
        url = self.get_config("url")
        if not url:
            return Result.fail("Missing INFLUX_URL or environment.influx.url")
        url = url.rstrip("/")

        # SSL
        ssl_cert = self.get_config("ssl_cert")
        ssl_verify_mode = self.get_config("ssl_verify", "true")
        ssl_verify = configure_verify(session, ssl_verify_mode, ssl_cert)

        # Batch policy
        max_size = self.get_config("max_batch_size", 20)
        max_age = self.get_config("max_batch_age_seconds", 2.0)

        # Version detection
        org = self.get_config("org")
        db = self.get_config("db")
        if org:
            # Influx 2
            read_token = self.get_config("read_token") or self.get_config("token")
            write_token = self.get_config("write_token") or self.get_config("token")
            if not read_token or not write_token:
                return Result.fail("InfluxDB 2 requires INFLUX_WRITE_TOKEN and INFLUX_READ_TOKEN, or INFLUX_TOKEN")
            base_url = f"{url}/api/v2/"  # was with write
            warnings = ["both org and db specified, assuming InfluxDB 2.x and ignoring db"] if db else None
            return Result.ok_payload(
                InfluxConfig(
                    ssl_verify=ssl_verify,
                    version=2,
                    base_url=base_url,
                    org=org,
                    write_token=write_token,
                    read_token=read_token,
                    max_batch_size=max_size,
                    max_batch_age_seconds=max_age,
                ),
                warnings=warnings,
            )
        if not db:
            return Result.fail("One of INFLUX_ORG/INFLUX_DB is required (or environment.influx.org/db)")
        # Influx 1
        base_url = url
        user = self.get_config("user")
        password = self.get_config("password")
        auth = (user, password) if user and password else None
        return Result.ok_payload(
            InfluxConfig(
                ssl_verify=ssl_verify,
                version=1,
                base_url=base_url,
                db=db,
                auth=auth,
                max_batch_size=1,  # not used with v1
                max_batch_age_seconds=0,  # not used with v1
            )
        )


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
