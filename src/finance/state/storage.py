# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/storage.py

import json
from pathlib import Path


class StateStorage:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, dict]:
        """
        Load state.json from the project root unless an explicit path is provided.
        """

        if not self.path.exists():
            return {}

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass  # corrupted or unreadable

        return {}

    def save(self, state: dict[str, dict]) -> None:
        """
        Save state atomically to avoid corruption.
        """

        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        tmp_path.replace(self.path)
