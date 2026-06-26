# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: ops/test_connectivity.py

from datetime import UTC, datetime
from pathlib import Path

from finance.timeseries.influx import InfluxBackend  # your unified backend

from finance.common.model import TimeseriesWrite
from finance.config.loader import ConfigLoader


def main():
    project_root = Path(__file__).resolve().parent

    print("Loading config...")
    loader = ConfigLoader(project_root)
    cfg_result = loader.load()
    if not cfg_result.ok:
        print("Config load failed:", cfg_result.reason, cfg_result.error)
        return

    full_cfg = cfg_result.payload
    secrets = full_cfg["secrets"]["influx"]
    env_cfg = full_cfg["influx"]

    # Build InfluxConfig

    # Build backend
    backend_result = InfluxBackend.from_config(config=env_cfg, secrets=secrets)
    if not backend_result.ok:
        print("Backend creation failed:", backend_result.reason, backend_result.error)
        return
    # Write a point
    backend = backend_result.payload
    now = int(datetime.now(tz=UTC).timestamp())
    write = TimeseriesWrite(
        series_name="connectivity_test", fields={"value": 43.0}, tags={"env": "acc"}, timestamp=now, bucket="test1"
    )
    """
    write_result = backend.write(entry = write)

    if not write_result.ok:
        print("Write failed:", write_result.reason, write_result.error)
        return

    print("Write OK")
    """
    # Read it back
    print("Reading back...")
    read_result = backend.read_first(bucket=write.bucket, measurement=write.series_name)

    if not read_result.ok:
        print("Read failed:", read_result.error)
        return

    print("Read OK")
    print("Returned point:", read_result.payload)


if __name__ == "__main__":
    main()
