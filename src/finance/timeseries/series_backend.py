# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/series_backend.py

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ..common.applogger import AppLogger
from ..common.json_utils import JsonObject, JsonReader
from ..common.model import BACKEND, Asset, ProviderProtocol, Series, SeriesPoint, SeriesState
from ..common.time_utils import write_time, write_timezone
from ..common.types import Failure, ParseError, Result, Success
from .backend_protocol import BackendProtocol
from .timescale_sql import TimescaleConfig, TimescaleSqlClient

type SqlClientFactory = Callable[[TimescaleConfig], BackendProtocol]

logger = AppLogger("backend")


class SeriesBackend:
    def __init__(
        self,
        config: TimescaleConfig,
        sql_client: BackendProtocol,
        get_provider: Callable[[str], ProviderProtocol | None],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._sql_client = sql_client
        self._get_provider = get_provider
        self.now = now or datetime.now
        self._pending: list[SeriesPoint] = []
        self._last_flush: datetime | None = None
        self._short_lived_series_ids: set[int] = set()

    # ---------------------
    # Static/Class methods
    # ---------------------

    @classmethod
    def from_config(
        cls,
        config: TimescaleConfig,
        get_provider: Callable[[str], ProviderProtocol | None],
        sql_factory: SqlClientFactory = TimescaleSqlClient,
        now: Callable[[], datetime] | None = None,
    ) -> Result[SeriesBackend]:
        if config.sslmode == "verify-ca" and config.sslrootcert == "system":
            return Failure(
                reason="Timescale backend initialization failed",
                error=f"verify-ca requires path in {BACKEND.upper()}_SSL_ROOT_CERT in .env or ssl_root_cert in yaml",
            )

        logger.debug(f"user: {config.user}, port: {config.port}, db: {config.dbname}")
        backend = cls(config, sql_factory(config), get_provider, now)
        refresh_result = backend.refresh_short_lived_series_ids()
        if refresh_result.ok is False:
            return refresh_result
        return Success(backend)

    # ---------------
    # Public methods
    # ---------------

    def add_point(self, entry: SeriesPoint) -> Result[int]:
        self._pending.append(entry)

        if self._should_flush():
            return self.flush()

        return Success(0)

    def close(self) -> Result[int]:
        """Flush pending data and close the DB connection."""
        result = self.flush()
        self._sql_client.close_connection()
        return result

    def flush(self) -> Result[int]:
        if not self._pending:
            return Success(0)

        result = self._insert_batches(self._pending, "Flush")
        self._pending.clear()
        if result.ok:
            self._last_flush = self.now()
        return result

    def get_assets(self) -> Result[list[Asset]]:
        query = """
            SELECT id, name, symbol, provider, provider_code, long_name, short_name,
              instrument, region, exchange, currency, unit, first_available_date::text,
              timezone, week_start, week_end, market_open::text, market_close::text
            FROM asset ORDER BY id;
            """
        result = self._sql_client.execute_read(query, context="get_assets")
        if result.ok is False:
            return result
        asset_name = "None"
        try:
            payload = result.payload
            rows = payload["rows"]
            columns = payload["columns"]

            assets: list[Asset] = []
            for row in rows:
                config = self._table_to_json(row, columns)
                asset_name = config.get("name", "None")
                asset = Asset.create(config=config, get_provider=self._get_provider)
                assets.append(asset)
            return Success(assets)
        except ParseError as pe:
            return Failure(f"get_assets could not load asset '{asset_name}'", str(pe))

    def get_series(self, get_asset: Callable[[int], Asset | None]) -> Result[list[Series]]:
        query = """
            SELECT s.id, s.code, s.asset_id, a.name as asset_name, s.interval, s.series_type,
            s.retention, s.retention_period, s.bootstrap_history, s.publication_offset
            FROM series s
            JOIN asset a ON s.asset_id = a.id
            ORDER BY s.id;
            """
        result = self._sql_client.execute_read(query, context="get_series")
        if result.ok is False:
            return result

        try:
            payload = result.payload
            rows = payload["rows"]
            columns = payload["columns"]
            series_id: int | None = None
            series_list: list[Series] = []
            for row in rows:
                reader = JsonReader(self._table_to_json(row, columns))
                series_id = reader.require(int, "id")
                asset_id = reader.require(int, "asset_id")
                asset = get_asset(asset_id)
                if asset is None:
                    raise ParseError(f"could not find asset with ID '{asset_id}'")
                series = Series.create(asset=asset, config=reader.get_object())
                series_list.append(series)
            return Success(series_list)

        except ParseError as pe:
            return Failure(reason=f"get_series could not load series with ID '{series_id}'", error=str(pe))

    def get_series_states(self) -> Result[dict[int, SeriesState]]:
        # 1. Load cold/hot ranges
        cold = self._sql_client.execute_read(
            "SELECT series_id, MIN(time), MAX(time) FROM series_data_cold GROUP BY series_id;",
            context="get_series_states_range_cold",
        )
        if cold.ok is False:
            return cold

        hot = self._sql_client.execute_read(
            "SELECT series_id, MIN(time), MAX(time) FROM series_data_hot GROUP BY series_id;",
            context="get_series_states_range_hot",
        )
        if hot.ok is False:
            return hot

        # Merge cold + hot

        state: dict[int, SeriesState] = {}
        for row in cold.payload["rows"] + hot.payload["rows"]:
            series_id = int(row[0])
            state[series_id] = SeriesState(first_point=row[1], last_point=row[2], needs_save=False)

        # Load sweep info

        sweep = self._sql_client.execute_read(
            "SELECT series_id, next_sweep, sweep_start FROM series_state;", context="get_series_states_sweep_info"
        )
        if sweep.ok is False:
            return sweep

        # Merge sweep info

        for row in sweep.payload["rows"]:
            series_id = row[0]
            if series_id not in state:
                state[series_id] = SeriesState(next_sweep=row[1], sweep_start=row[2], needs_save=False)
            else:
                state[series_id].next_sweep = row[1]
                state[series_id].sweep_start = row[2]
                state[series_id].needs_save = False

        return Success(state)

    def refresh_short_lived_series_ids(self) -> Result[None]:
        query = "SELECT id FROM series WHERE retention = 'short_lived';"

        result = self._sql_client.execute_read(query, context="load_short_lived_series_ids")
        if result.ok is False:
            return result

        rows = result.payload["rows"]
        self._short_lived_series_ids = {row[0] for row in rows}

        return Success(None)

    def save_sweep(self, series_id: int, next_sweep: datetime, sweep_start: datetime) -> Result[int]:
        sql_query = """
            INSERT INTO series_state (series_id, next_sweep, sweep_start)
            VALUES (%s, %s, %s)
            ON CONFLICT (series_id)
            DO UPDATE SET next_sweep = EXCLUDED.next_sweep, sweep_start = EXCLUDED.sweep_start
            RETURNING series_id;
        """
        params = (series_id, next_sweep, sweep_start)
        return self._sql_client.execute_write(sql_query, params)

    def store_asset(self, asset: Asset) -> Result[Asset]:
        if asset.effective_metadata is None:
            return Failure(reason="Store asset failed", error=f"No effective metadata to store asset '{asset.name}'")
        meta = asset.effective_metadata
        base_fields = (
            asset.name,
            asset.symbol,
            asset.provider.name,
            asset.provider_code,
            meta.long_name,
            meta.short_name,
            meta.instrument,
            meta.region,
            meta.exchange,
            meta.currency,
            meta.unit,
            meta.first_available_date,
            write_timezone(meta.timezone),
            meta.week_start,
            meta.week_end,
            write_time(meta.market_open),
            write_time(meta.market_close),
        )

        if asset.id is None:
            sql_query = """
                    INSERT INTO asset (name, symbol, provider, provider_code,
                        long_name, short_name, instrument, region, exchange, currency, unit,
                        first_available_date, timezone, week_start, week_end, market_open, market_close)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """
            params = base_fields
        else:
            sql_query = """
                UPDATE asset
                SET name=%s, symbol=%s, provider=%s, provider_code=%s,
                    long_name=%s, short_name=%s, instrument=%s, region=%s, exchange=%s, currency=%s, unit=%s,
                    first_available_date=%s, timezone=%s, week_start=%s, week_end=%s, market_open=%s, market_close=%s
                WHERE id=%s
                RETURNING id;
            """
            params = (*base_fields, asset.id)

        result = self._sql_client.execute_write(sql_query, params)
        if result.ok is False:
            return result
        return Success(asset if asset.id is not None else asset.with_id(result.payload))

    def store_series(self, series: Series) -> Result[Series]:
        if series.asset.id is None:
            return Failure(reason="store series operation failed", error="asset.id was not set")

        base_fields = (
            series.code,
            series.asset.id,
            series.interval,
            series.series_type,
            series.retention,
            series.retention_period,
            series.bootstrap_history,
            series.publication_offset,
        )

        if series.id is None:
            sql_query = """
                INSERT INTO series (
                    code, asset_id, interval, series_type, retention, retention_period, bootstrap_history, publication_offset)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            params = base_fields
        else:
            sql_query = """
                UPDATE series
                SET code=%s, asset_id=%s, interval=%s, series_type=%s, retention=%s, retention_period=%s,
                    bootstrap_history=%s, publication_offset=%s
                WHERE id=%s
                RETURNING id;
            """
            params = (*base_fields, series.id)

        result = self._sql_client.execute_write(sql_query, params, context="store series")
        if result.ok is False:
            return result
        return Success(series if series.id is not None else series.with_id(result.payload))

    # ----------------
    # private methods
    # ----------------

    def _insert_batches(self, entries: list[SeriesPoint], context: str) -> Result[int]:
        sql_template = """
        INSERT INTO {table} (series_id, time, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (series_id, time)
        DO UPDATE SET
            open   = EXCLUDED.open,
            high   = EXCLUDED.high,
            low    = EXCLUDED.low,
            close  = EXCLUDED.close,
            volume = EXCLUDED.volume
        """

        points: dict[str, list[SeriesPoint]] = {"hot": [], "cold": []}
        for point in entries:
            label = "hot" if point.series_id in self._short_lived_series_ids else "cold"
            points[label].append(point)

        for label, point_list in points.items():
            if not point_list:
                continue
            table = f"series_data_{label}"
            values = [(e.series_id, e.time, e.open, e.high, e.low, e.close, e.volume) for e in point_list]

            result = self._sql_client.execute_many(sql_template, values, table=table, context=f"{context}_{label}")
            if result.ok is False:
                return result

        return Success(len(entries))

    def _should_flush(self) -> bool:
        now = self.now()
        if self._last_flush is None:
            self._last_flush = now

        if not self._pending:
            return False

        if len(self._pending) >= self._config.max_batch_size:
            return True

        age = now - self._last_flush
        return age >= self._config.max_batch_age

    def _table_to_json(self, row: tuple, columns: dict[str, int]) -> JsonObject:
        config: JsonObject = {}
        for field, index in columns.items():
            config[field] = row[index]
        return config
