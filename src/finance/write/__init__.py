# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/write/__init__.py

from .metric_writer import MetricWriter


def write_metric(bucket, measurement, fields, timestamp, state):
    """
    Public API for writing a metric.
    This is what main.py and tests should call.
    """
    writer = MetricWriter(state)
    result = writer.write(bucket, measurement, fields, timestamp)
    if result["status"] == "error":
        writer.error("write failed", **result)
    elif result["status"] == "skipped":
        writer.info("write skipped", **result)
    else:
        writer.debug(result["status"], **result)
    return result
