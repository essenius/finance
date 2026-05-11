#!/usr/bin/env python3
import os
from pathlib import Path

LICENSE_TEMPLATE = """\
# Copyright (c) 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See LICENSE file for details.
# File: {filename}
"""

def add_license_to_file(path: Path):
    filename = path.name
    license_block = LICENSE_TEMPLATE.format(filename=filename)

    text = path.read_text(encoding="utf-8")

    # Skip if already present
    if license_block.splitlines()[0] in text:
        return

    lines = text.splitlines()

    # Preserve shebang
    if lines and lines[0].startswith("#!"):
        new_text = lines[0] + "\n" + license_block + "\n" + "\n".join(lines[1:])
    else:
        new_text = license_block + "\n" + text

    path.write_text(new_text, encoding="utf-8")


def main():
    root = Path(__file__).resolve().parent.parent
    for path in root.rglob("*.py"):
        add_license_to_file(path)


if __name__ == "__main__":
    main()

