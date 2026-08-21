# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/backend_protocol.py

from typing import Protocol

from ..common.result import Result


class BackendProtocol(Protocol):
    """TODO delete
    @property
    def config(self): ...

    @property
    def connection(self): ...
    """

    def execute_read(self, query: str, params: tuple | None = None, context: str = "Read") -> Result[dict]: ...

    def execute_write(self, query: str, params: tuple, context: str = "Write") -> Result[int]: ...

    def execute_many(self, query: str, params: list[tuple], context: str) -> Result[None]: ...

    def is_connected(self) -> bool: ...

    def close_connection(self) -> None: ...
