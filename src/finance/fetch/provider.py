# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/provider.py

from datetime import UTC, datetime

from finance.common.log_mixin import LogMixin


class MarketDataProvider(LogMixin):
    """Base interface for all market data providers."""

    def __init__(self, config=None, now_provider=None):

        self.config = config or {}
        self.now = now_provider or (lambda: datetime.now(UTC))

    def _check_status(self, symbol, response):
        if response.status_code != 200:
            message = f"status {response.status_code}"
            if response.text:
                message += f" ({response.text})"
            self.error(message, symbol)
            return False
        return True

    def error(self, message, symbol=None):
        provider = self.__class__.__name__.replace("Provider", "")
        msg = f"Error fetching {provider} data{'' if symbol is None else f' for {symbol}'}: {message}"
        super().error(msg)
        return []

    def _require_api_key(self, symbol):
        key = self.config.get("api_key")
        if not key:
            self.error("API key missing", symbol)
            return None
        return key

    def _safe(self, symbol, fn):
        try:
            return fn()
        except Exception as exc:
            self.error(exc, symbol)
            return []

    def _safe_get(self, obj, path):
        """
        Walk nested dict/list structures safely.
        Returns (value, None) on success.
        Returns (None, error_message) on failure.
        """
        current = obj
        for key in path:
            try:
                current = current[key]
            except KeyError:
                return None, f"missing key '{key}'"
            except IndexError:
                return None, f"missing index [{key}]"
            except TypeError:
                return None, f"cannot index with [{key}] into {type(current).__name__}"
        return current, None

    def fetch(self, asset: dict, last_timestamp: int):
        """
        Fetch data points for the given asset definition since the last timestamp.

        Must return:
            [{
                "timestamp": int,
                "fields": { field_name: value }
            }
            ...
            ]
        """
        raise NotImplementedError
