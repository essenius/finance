# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_series_backend.py

from datetime import timedelta

from finance.common.configuration import TimescaleConfig
from finance.common.model import SeriesPoint, SeriesState
from finance.common.types import Failure, Result, Success
from finance.timeseries.backend_protocol import SqlReadPayload
from finance.timeseries.series_backend import SeriesBackend


class FakeConnection:
    closed: bool = False


class SqlFakeOk:
    def __init__(self, config: TimescaleConfig | None = None):
        self._config = config
        self._connection = FakeConnection()
        self.read_count = 0
        self.write_count = 0
        self.execute_many_count = 0
        self.error_in = 0
        self.read_results: list[SqlReadPayload] = []

    def fail(self, context, error) -> Result:
        return Failure(reason=f"{context} operation failed", error=error)

    def result(self, context: str) -> Result:
        if not self._connection or self._connection.closed:
            return self.fail(context, "Boom!")

        return Success(None)

    def execute_read(self, query: str, params: tuple | None = None, context: str = "Read") -> Result[SqlReadPayload]:
        self.read_count += 1
        if self.error_in == self.read_count:
            return self.fail(context, f"Error in {self.error_in}")

        result = self.result(context)
        if result.ok is False:
            return result

        if not self.read_results:
            payload: SqlReadPayload = {"rows": [], "columns": {}}
            return Success(payload)

        next_payload = self.read_results.pop(0)
        return Success(next_payload)

    def execute_write(self, query: str, params: tuple, context: str = "Write") -> Result[int]:
        self.write_count += 1
        return self.result(context)

    def execute_many(self, query: str, params: list[tuple], context: str) -> Result[None]:
        self.execute_many_count += 1
        return self.result(context)

    def close_connection(self) -> None:
        self._connection = None

    def is_connected(self) -> bool:
        return True


class SqlFakeOkFactory:
    instance: SqlFakeOk
    config: TimescaleConfig | None

    def __call__(self, config: TimescaleConfig | None = None) -> SqlFakeOk:
        self.config = config
        self.instance = SqlFakeOk(config)
        return self.instance


class SqlFakeFail:
    def __init__(self, config: TimescaleConfig | None = None):
        self._config = config
        self._connection = None

    def fail(self, context: str) -> Result:
        return Failure(reason=f"{context} operation failed", error="Boom!")

    def execute_read(self, query: str, params: tuple | None = None, context: str = "Read") -> Result[SqlReadPayload]:
        return self.fail(context)

    def execute_write(self, query: str, params: tuple, context: str = "Write") -> Result[int]:
        return self.fail(context)

    def execute_many(self, query: str, params: list[tuple], context: str) -> Result[None]:
        return self.fail(context)

    def close_connection(self) -> None:
        self._connection = None

    def is_connected(self) -> bool:
        return False


def test_from_config_failure_cert(assert_error, make_timescale_config):
    config = make_timescale_config(ssl_mode="verify-ca")

    result = SeriesBackend.from_config(config=config, sql_factory=SqlFakeOkFactory())

    # with make_backend_context(config) as result:
    assert_error(
        result,
        "Timescale backend initialization failed",
        "verify-ca requires path in TIMESCALEDB_SSL_ROOT_CERT in .env or ssl_root_cert in yaml",
    )


def test_from_config_success_no_defaults(unwrap, make_timescale_config):
    config = make_timescale_config(
        **{
            "host": "myhost",
            "port": 1234,
            "user": "finuser",
            "password": "secret",
            "db": "fin1",
            "ssl_mode": "verify-full",
            "max_batch_size": 500,
            "max_batch_age_seconds": 2.5,
        }
    )

    sql_factory = SqlFakeOkFactory()
    backend = unwrap(SeriesBackend.from_config(config=config, sql_factory=sql_factory))

    timescale_config = backend._config
    assert timescale_config.host == "myhost"
    assert timescale_config.port == 1234
    assert timescale_config.user == "finuser"
    assert timescale_config.password == "secret"
    assert timescale_config.dbname == "fin1"
    assert timescale_config.sslmode == "verify-full"
    assert timescale_config.max_batch_size == 500
    assert timescale_config.max_batch_age == timedelta(seconds=2.5)

    sql_config = sql_factory.config
    assert sql_config is not None, "_config exists"
    connect_config = sql_config.connect_config()
    assert connect_config == {
        "host": "myhost",
        "port": 1234,
        "dbname": "fin1",
        "user": "finuser",
        "password": "secret",
        "sslmode": "verify-full",
        "sslrootcert": "system",
    }

    result = backend.flush()
    assert result.ok is True
    assert backend.now is not None


def test_from_config_success_defaults(unwrap, make_timescale_config):

    backend = unwrap(SeriesBackend.from_config(config=make_timescale_config(), sql_factory=SqlFakeOkFactory()))

    timescale_config = backend._config
    assert timescale_config.host == "host123"
    assert timescale_config.user == "fin_user"
    assert timescale_config.password == "s3cr3t"
    assert timescale_config.dbname == "fin2"
    assert timescale_config.port == 5432
    assert timescale_config.sslmode == "verify-full"
    assert timescale_config.max_batch_size == 1000
    assert timescale_config.max_batch_age == timedelta(seconds=2.0)

    result = backend.flush()
    assert result.ok is True
    assert backend.now is not None


"""
def test_from_config_key_failure(assert_error):

    result = SeriesBackend.from_config(config={}, sql_factory=SqlFakeOk)
    assert_error(result, "Timescale backend initialization failed", "['host']: Missing required key `host`")
"""


def test_from_config_sql_failure(assert_error, make_timescale_config):

    result = SeriesBackend.from_config(config=make_timescale_config(), sql_factory=SqlFakeFail)
    assert_error(result, "load_short_lived_series_ids operation failed", "Boom!")


def test_flush_without_connection_and_exception(fixed_now, make_timescale_config, assert_error, unwrap):
    # force an immediate flush after adding via the batch size

    backend: SeriesBackend = unwrap(
        SeriesBackend.from_config(config=make_timescale_config(max_batch_size=1), sql_factory=SqlFakeOkFactory())
    )
    backend._sql_client.close_connection()
    now = fixed_now()
    entry = SeriesPoint(series_id=0, time=now, close=1)

    result = backend.add_point(entry)
    assert_error(result, "Flush_cold operation failed", "Boom!")


def test_add_writes_two_entries(fixed_now, make_timescale_config, unwrap):

    sql_factory = SqlFakeOkFactory()
    backend: SeriesBackend = unwrap(
        SeriesBackend.from_config(config=make_timescale_config(max_batch_size=2), sql_factory=sql_factory)
    )
    now = fixed_now()
    next = now + timedelta(seconds=1)
    entry1 = SeriesPoint(series_id=1, time=now, close=1)
    entry2 = SeriesPoint(series_id=2, time=next, close=1.1, volume=2)

    result = backend.add_point(entry1)
    assert result.ok is True, "First add"
    sql_client = sql_factory.instance
    assert sql_client.execute_many_count == 0
    result = backend.add_point(entry2)
    assert result.ok is True, "second add"
    assert sql_client.execute_many_count == 1


def test_close_writes(fixed_now, make_timescale_config, unwrap):

    sql_factory = SqlFakeOkFactory()
    backend: SeriesBackend = unwrap(
        SeriesBackend.from_config(config=make_timescale_config(max_batch_size=2), sql_factory=sql_factory)
    )

    now = fixed_now()
    entry1 = SeriesPoint(series_id=1, time=now, close=1)

    result = backend.add_point(entry1)
    assert result.ok is True, "add"
    write_count: int = unwrap(backend.close())
    assert write_count == 1, "write count is 1"
    assert sql_factory.instance.execute_many_count == 1


def test_flush_writes_when_batch_too_old(fixed_now, make_timescale_config, unwrap):
    sql_factory = SqlFakeOkFactory()
    backend: SeriesBackend = unwrap(
        SeriesBackend.from_config(config=make_timescale_config(max_batch_age_seconds=0), sql_factory=sql_factory)
    )

    now = fixed_now()
    entry = SeriesPoint(series_id=1, time=now, close=1)

    write_count = unwrap(backend.add_point(entry))
    assert write_count == 1
    assert sql_factory.instance.execute_many_count == 1


# ------------------
# Get series states
# ------------------


def test_get_series_states_loads_min_max(fixed_now, make_timescale_config, unwrap):

    sql_factory = SqlFakeOkFactory()

    backend: SeriesBackend = unwrap(SeriesBackend.from_config(config=make_timescale_config(), sql_factory=sql_factory))

    now = fixed_now()
    # Two series in cold table

    cold_result: SqlReadPayload = {
        "rows": [
            (1, now - timedelta(days=10), now - timedelta(days=1)),
            (2, now - timedelta(days=20), now - timedelta(days=5)),
        ],
        "columns": {},
    }

    hot_result: SqlReadPayload = {
        "rows": [
            (3, now - timedelta(hours=6), now - timedelta(hours=1)),
        ],
        "columns": {},
    }

    sweep_start = now - timedelta(days=7)
    next_sweep = now + timedelta(days=1)
    sweep_result: SqlReadPayload = {"rows": [(1, next_sweep, sweep_start), (4, next_sweep, sweep_start)], "columns": {}}

    sql_factory.instance.read_results = [
        cold_result,
        hot_result,
        sweep_result,
    ]

    result = backend.get_series_states()
    assert result.ok is True

    state = result.payload

    # Validate dict keys
    assert set(state.keys()) == {1, 2, 3, 4}

    # Validate series 1 (cold and sweep)
    s1: SeriesState = state[1]
    cold_rows = cold_result["rows"]
    assert (s1.first_point, s1.last_point) == (cold_rows[0][1], cold_rows[0][2])
    assert s1.sweep_start == sweep_start
    assert s1.next_sweep == next_sweep
    assert not s1.needs_save

    # Validate series 2 (cold and no sweep)
    s2: SeriesState = state[2]
    assert (s2.first_point, s2.last_point) == (cold_rows[1][1], cold_rows[1][2])
    assert s2.sweep_start is None
    assert s2.next_sweep is None
    assert s2.needs_save

    # Validate series 3 (hot and no sweep)
    hot_rows = hot_result["rows"]
    s3: SeriesState = state[3]
    assert (s3.first_point, s3.last_point) == (hot_rows[0][1], hot_rows[0][2])
    assert s3.needs_save

    # Validate series 4 (only sweep)
    s4: SeriesState = state[4]
    assert s4.first_point is None
    assert s4.last_point is None
    assert s4.sweep_start == sweep_start
    assert s4.next_sweep == next_sweep
    assert not s4.needs_save


def test_get_series_states_cold_error(assert_error, make_timescale_config, unwrap):

    backend: SeriesBackend = unwrap(
        SeriesBackend.from_config(config=make_timescale_config(), sql_factory=SqlFakeOkFactory())
    )

    backend._sql_client.close_connection()
    result = backend.get_series_states()
    assert_error(result, "get_series_states_range_cold operation failed", "Boom!")


def test_get_series_states_hot_error(assert_error, make_timescale_config, unwrap):

    sql_factory = SqlFakeOkFactory()
    backend: SeriesBackend = unwrap(SeriesBackend.from_config(config=make_timescale_config(), sql_factory=sql_factory))

    sql = sql_factory.instance
    sql.error_in = 2
    sql.read_count = 0

    result = backend.get_series_states()
    assert_error(result, "get_series_states_range_hot operation failed", "Error in 2")


def test_get_series_states_sweep_error(assert_error, make_timescale_config, unwrap):

    sql_factory = SqlFakeOkFactory()
    backend: SeriesBackend = unwrap(SeriesBackend.from_config(config=make_timescale_config(), sql_factory=sql_factory))

    sql = sql_factory.instance
    sql.error_in = 3
    sql.read_count = 0

    result = backend.get_series_states()
    assert_error(result, "get_series_states_sweep_info operation failed", "Error in 3")


def test_store_asset_no_effective_metadata(unwrap, make_asset, make_timescale_config, assert_error):
    backend: SeriesBackend = unwrap(
        SeriesBackend.from_config(config=make_timescale_config(), sql_factory=SqlFakeOkFactory())
    )
    asset = make_asset(effective_metadata=None)
    result = backend.store_asset(asset)
    assert_error(result, reason="Store asset failed", error="No effective metadata to store asset 'eur_usd'")
