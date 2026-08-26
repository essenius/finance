# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/backend_protocol.py

from typing import Protocol, TypedDict

from ..common.types import Result


class SqlReadPayload(TypedDict):
    rows: list[tuple]
    columns: dict[str, int]


class BackendProtocol(Protocol):
    def execute_read(
        self, query: str, params: tuple | None = None, context: str = "Read"
    ) -> Result[SqlReadPayload]: ...

    def execute_write(self, query: str, params: tuple, context: str = "Write") -> Result[int]: ...

    def execute_many(self, query: str, params: list[tuple], context: str) -> Result[None]: ...

    def is_connected(self) -> bool: ...

    def close_connection(self) -> None: ...
