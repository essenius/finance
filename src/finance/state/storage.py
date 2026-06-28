# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/storage.py

import json
from dataclasses import asdict
from pathlib import Path

from finance.state.state import SeriesState


class StateStorage:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[int, SeriesState]:
        """
        Load state.json from the project root unless an explicit path is provided.
        """
        if not self.path.exists():
            return {}

        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
                if not isinstance(raw, dict):
                    return {}
        except Exception:
            return {}

        result: dict[int, SeriesState] = {}

        for key, value in raw.items():
            try:
                sid = int(key)
                if isinstance(value, dict):
                    result[sid] = SeriesState.from_dict(value)
            except Exception:
                continue

        return result

    def save(self, state: dict[int, SeriesState]) -> None:
        """
        Save state atomically to avoid corruption.
        """

        tmp_path = self.path.with_suffix(".tmp")

        serializable = {series_id: entry.to_dict() for series_id, entry in state.items()}
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
        tmp_path.replace(self.path)
