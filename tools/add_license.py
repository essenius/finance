#!/usr/bin/env python3
import re
from pathlib import Path
from datetime import datetime

CURRENT_YEAR = datetime.now().year

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LICENSE_TEMPLATE = """\
# Copyright {years} Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: {filename}
"""

# Matches:
#   # Copyright 2026 Rik Essenius
#   # Copyright 2026-2027 Rik Essenius
COPYRIGHT_RE = re.compile(r"#\s*Copyright\s+(\d{4})(?:-(\d{4}))?\s+Rik Essenius")

FILE_RE = re.compile(r"#\s*File:\s*(.+)")

def extract_years(text: str):
    """
    Returns (start_year, end_year or None) if a header exists.
    Otherwise returns None.
    """
    m = COPYRIGHT_RE.search(text)
    if not m:
        return None

    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else None
    return start, end

def compute_year_range(start_year: int):
    if CURRENT_YEAR == start_year:
        return str(start_year)
    return f"{start_year}-{CURRENT_YEAR}"

def is_path_comment(line: str) -> bool:
    line = line.strip()
    if not line.startswith("#"):
        return False
    content = line[1:].strip()
    return "/" in content and content.endswith(".py") and " " not in content

def add_license_to_file(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Compute project-relative filename
    try:
        filename = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        filename = path.name

    # Detect existing header
    years = extract_years(text)

    if years:
        start, end = years
        # Update only if needed
        new_years = compute_year_range(start)
        if end is None or end != CURRENT_YEAR:
            # Replace only the year part
            updated = COPYRIGHT_RE.sub(
                f"# Copyright {new_years} Rik Essenius",
                text,
                count=1
            )
        
        # Replace the File: line
        updated = FILE_RE.sub(f"# File: {filename}", updated, count=1)
        path.write_text(updated, encoding="utf-8")

        return

    # No header → new file
    start_year = CURRENT_YEAR
    year_range = str(start_year)

    license_block = LICENSE_TEMPLATE.format(years=year_range, filename=filename)

    new_lines = []
    idx = 0

    # Preserve shebang
    if lines and lines[0].startswith("#!"):
        new_lines.append(lines[0])
        idx = 1

    # Remove path-only comment if present
    if idx < len(lines) and is_path_comment(lines[idx]):
        idx += 1

    # Insert header
    new_lines.append(license_block)

    # Append rest of file
    new_lines.extend(lines[idx:])

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def main():
    for path in PROJECT_ROOT.rglob("*.py"):
        add_license_to_file(path)

if __name__ == "__main__":
    main()
