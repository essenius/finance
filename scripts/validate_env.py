#!/usr/bin/env python3
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: scripts/validate_env.py

import sys
from pathlib import Path


def is_irrelevant(line) -> bool:
    return not line or line.startswith("#") or "=" not in line


def parse_env_file(path: Path) -> tuple[dict[str, str], set[str]]:
    values: dict[str, str] = {}
    mandatory: set[str] = set()
    section = None

    for line in path.read_text().splitlines():
        line = line.strip()

        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue

        if is_irrelevant(line):
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()

        values[name] = value

        if section == "mandatory settings":
            mandatory.add(name)

    return values, mandatory


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} .env.example .env")
        return 2

    example_path = Path(sys.argv[1])
    env_path = Path(sys.argv[2])

    example, mandatory = parse_env_file(example_path)
    actual, _ = parse_env_file(env_path)

    errors = False
    warnings = False

    for name in sorted(mandatory):
        if name not in actual or not actual[name]:
            print(f"ERROR: Mandatory setting '{name}' is missing")
            errors = True
        elif actual[name] == example[name]:
            print(f"WARNING: Mandatory setting '{name}' still has its example value")
            warnings = True
    if not errors and not warnings:
        print("Validation of .env completed successfully")
    return 2 if errors else 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
