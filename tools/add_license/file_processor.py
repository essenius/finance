# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tools/add_license/file_processor.py

from pathlib import Path

from .header import Header  # if needed


def normalize_body_spacing(lines: list[str]) -> list[str]:
    """Ensure exactly one blank line before the body."""
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return [""] + lines[idx:]

def compute_relative_filename(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return path.name

class FileProcessor:
    """Handles reading, processing, and writing a single Python file."""

    def __init__(self, path: Path, project_root: Path, current_year: int):
        self.path = path
        self.project_root = project_root
        self.current_year = current_year
        self.lines = path.read_text(encoding="utf-8").splitlines()
        self.shebang = None

    def strip_shebang(self):
        if self.lines and self.lines[0].startswith("#!"):
            self.shebang = self.lines[0]
            self.lines = self.lines[1:]

    def strip_path_comment(self):
        if self.lines and self.lines[0].startswith("# Path:"):
            self.lines = self.lines[1:]

    def is_trivial_init(self) -> bool:
        if self.path.name != "__init__.py":
            return False
        return all(not line.strip() or line.lstrip().startswith("#") for line in self.lines)

    def process(self):
        # Clean trivial __init__.py
        if self.is_trivial_init():
            self.path.write_text("", encoding="utf-8")
            return

        self.strip_shebang()
        self.strip_path_comment()

        header, header_end = Header.parse(self.lines)
        filename = compute_relative_filename(self.path, self.project_root)

        if header is None:
            # New header
            header = Header(self.current_year, None, filename)
            body = normalize_body_spacing(self.lines)
        else:
            # Existing header
            body = normalize_body_spacing(self.lines[header_end:])
            header.filename = filename
            header.update_year(self.current_year)

        # Assemble final file
        final_lines = []
        if self.shebang:
            final_lines.append(self.shebang)

        final_lines.extend(header.render())
        final_lines.extend(body)

        self.path.write_text("\n".join(final_lines) + "\n", encoding="utf-8")
