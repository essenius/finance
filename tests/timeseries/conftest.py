# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/conftest.py

from unittest.mock import Mock

import pytest

from finance.common.model import TimeseriesWrite
from finance.timeseries.influx import InfluxBackend, InfluxConfig


@pytest.fixture
def session():
    return Mock()


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


@pytest.fixture
def backend_v1():
    session = Mock()
    cfg = InfluxConfig(
        ssl_verify=True,
        ssl_use_legacy=False,
        version=1,
        base_url="http://x/write",
        db="finance",
        auth=("u", "p"),
        max_batch_size=1,
        max_batch_age_seconds=0,
    )
    return InfluxBackend(session, cfg, FakeClock())


@pytest.fixture
def backend_v2():
    session = Mock()
    cfg = InfluxConfig(
        ssl_verify=True,
        ssl_use_legacy=False,
        version=2,
        base_url="https://example/api/v2/write",
        org="rik",
        read_token="123",
        write_token="abc",
        max_batch_size=3,
        max_batch_age_seconds=5.0,
    )
    return InfluxBackend(session, cfg, FakeClock())


@pytest.fixture
def make_entry():
    def _make(
        measurement="m",
        fields=None,
        tags=None,
        timestamp=0,
        bucket="bucket",
    ):
        return TimeseriesWrite(
            measurement=measurement,
            fields=fields or {},
            tags=tags or {},
            timestamp=timestamp,
            bucket=bucket,
        )

    return _make


@pytest.fixture
def make_entries(make_entry):
    def _make(n):
        return [make_entry(fields={"v": i}, timestamp=i) for i in range(n)]

    return _make


@pytest.fixture
def mock_post():
    def _mock(backend, *, status, text="", json_data=None, exception=None):
        class MockResponse:
            def __init__(self):
                self.status_code = status
                self.text = text

            def raise_for_status(self):
                # 204 OK
                if self.status_code < 300:
                    return

                # 400 is NOT an exception for InfluxDB v2 batch writes
                if self.status_code == 400:
                    return

                # 500+ should raise
                if self.status_code >= 500:
                    raise Exception(f"HTTP {self.status_code}")

            def json(self):
                if json_data is None:
                    return {}
                return json_data

        def fake_post(*args, **kwargs):
            if exception:
                raise exception
            return MockResponse()

        backend.session = Mock()
        backend.session.post = Mock(side_effect=fake_post)

    return _mock
