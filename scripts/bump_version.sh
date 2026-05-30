#!/usr/bin/env bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: scripts/bump_version.sh

set -euo pipefail

DEV_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYPROJECT="$DEV_ROOT/pyproject.toml"
INIT_FILE="$DEV_ROOT/finance/__init__.py"

CURRENT_VERSION=$(grep '^version =' "$PYPROJECT" | sed -E 's/version = "([0-9]+)\.([0-9]+)\.([0-9]+)"/\1 \2 \3/')
read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

NEW_PATCH=$((PATCH + 1))
NEW_VERSION="$MAJOR.$MINOR.$NEW_PATCH"

sed -i "s/version = \"$MAJOR.$MINOR.$PATCH\"/version = \"$NEW_VERSION\"/" "$PYPROJECT"
sed -i "s/^__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"

echo "$NEW_VERSION"
