# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/backend_protocol.py

from typing import Protocol

from ..common.result import Result


class BackendProtocol(Protocol):
    @property
    def config(self): ...

    @property
    def connection(self): ...

    def execute_read(
        self, sql_query: str | object, params: tuple | None = None, context: str = "Read"
    ) -> Result[list]: ...

    def execute_write(self, sql_query: str, params: tuple, context: str = "Write") -> Result[int]: ...

    def execute_many(self, sql_query: str | object, params: list[tuple], context: str) -> Result[None]: ...

    def close_connection(self) -> None: ...
