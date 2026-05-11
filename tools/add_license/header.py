# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tools/add_license/header.py

import re
from pathlib import Path

COPYRIGHT_RE = re.compile(r"^# Copyright (\d{4})(?:-(\d{4}))? Rik Essenius$")
LICENSE_RE = re.compile(r"^# Licensed under the Apache License")
FILE_RE = re.compile(r"^# File: (.+)$")


class Header:
    """Represents the license header of a Python file."""

    def __init__(self, start_year: int, end_year: int | None, filename: str):
        self.start_year = start_year
        self.end_year = end_year
        self.filename = filename

    @classmethod
    def parse(cls, lines: list[str]):
        """
        Parse an existing header.
        Returns (Header instance, header_end_index) or (None, None).
        """
        start_year = None
        end_year = None
        header_end = None

        for i, line in enumerate(lines[:10]):
            m = COPYRIGHT_RE.match(line)
            if m:
                start_year = int(m.group(1))
                end_year = int(m.group(2)) if m.group(2) else None

            if FILE_RE.match(line) and start_year is not None:
                header_end = i + 1
                break

        if start_year is None or header_end is None:
            return None, None

        filename = FILE_RE.match(lines[header_end - 1]).group(1)
        return cls(start_year, end_year, filename), header_end

    def update_year(self, current_year: int):
        if self.end_year != current_year:
            self.end_year = current_year

    def render(self) -> list[str]:
        if self.end_year and self.end_year != self.start_year:
            years = f"{self.start_year}-{self.end_year}"
        else:
            years = f"{self.start_year}"

        return [
            f"# Copyright {years} Rik Essenius",
            "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.",
            f"# File: {self.filename}",
        ]
