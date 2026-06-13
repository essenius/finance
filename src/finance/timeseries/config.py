# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/config.py

from dataclasses import dataclass

from finance.common.model import Result


@dataclass(frozen=True)
class InfluxConfig:
    ssl_verify: bool | str
    ssl_use_legacy: bool
    version: int
    base_url: str
    max_batch_size: int
    max_batch_age_seconds: float
    org: str | None = None
    write_token: str | None = None
    read_token: str | None = None
    db: str | None = None
    auth: tuple[str, str] | None = None


@dataclass(frozen=True)
class VerifyConfig:
    ssl_verify: bool | str
    ssl_use_legacy: bool = False


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

    def create(self) -> Result[InfluxConfig]:
        url = self.get_config("url")
        if not url:
            return Result.fail("Missing INFLUX_URL or environment.influx.url")
        url = url.rstrip("/")

        ssl_cert = self.get_config("ssl_cert")
        ssl_verify_mode = self.get_config("ssl_verify", "true")
        ssl_verify_result = self.configure_verify(ssl_verify_mode, ssl_cert)
        if not ssl_verify_result.ok:
            return ssl_verify_result

        args = {
            "ssl_verify": ssl_verify_result.payload.ssl_verify,
            "ssl_use_legacy": ssl_verify_result.payload.ssl_use_legacy,
        }

        # Version detection
        org = self.get_config("org")
        db = self.get_config("db")
        if org:
            # Influx 2
            read_token = self.get_config("read_token") or self.get_config("token")
            write_token = self.get_config("write_token") or self.get_config("token")
            if not read_token or not write_token:
                return Result.fail("InfluxDB 2 requires INFLUX_WRITE_TOKEN and INFLUX_READ_TOKEN, or INFLUX_TOKEN")
            warnings = ["both org and db specified, assuming InfluxDB 2.x and ignoring db"] if db else None
            args.update(
                {
                    "version": 2,
                    "base_url": f"{url}/api/v2/",
                    "org": org,
                    "write_token": write_token,
                    "read_token": read_token,
                    "max_batch_size": self.get_config("max_batch_size", 20),
                    "max_batch_age_seconds": self.get_config("max_batch_age_seconds", 2.0),
                }
            )
            return Result.ok_payload(InfluxConfig(**args), warnings=warnings)

        if not db:
            return Result.fail("One of INFLUX_ORG/INFLUX_DB is required (or environment.influx.org/db)")

        # Influx 1
        user = self.get_config("user")
        password = self.get_config("password")

        args.update(
            {
                "version": 1,
                "base_url": url,
                "db": db,
                "auth": (user, password) if user and password else None,
                "max_batch_size": self.get_config("max_batch_size", 1),
                "max_batch_age_seconds": self.get_config("max_batch_age_seconds", 0.0),
            }
        )

        return Result.ok_payload(InfluxConfig(**args))

    def configure_verify(self, mode: str, cert: str | None) -> Result[VerifyConfig]:
        mode = mode.lower()

        if mode == "true":
            return Result.ok_payload(VerifyConfig(ssl_verify=True))

        if mode == "false":
            return Result.ok_payload(VerifyConfig(ssl_verify=False))

        if mode == "pinned":
            if not cert:
                return Result.fail("Pinned mode requires a certificate path")
            return Result.ok_payload(VerifyConfig(ssl_verify=cert))

        if mode == "legacy":
            return Result.ok_payload(VerifyConfig(ssl_verify=cert if cert else True, ssl_use_legacy=True))

        return Result.fail(f"Unknown verify mode: {mode}")
