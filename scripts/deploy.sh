#!/usr/bin/env bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: scripts/deploy.sh

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Environment file '$ENV_FILE' not found"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${ENV_ROOT:?ENV_ROOT is not set}"
: "${ENV_VENV:?ENV_VENV is not set}"

DEV_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

WHEEL=$(ls -t "$DEV_ROOT"/dist/*.whl | head -n 1)
if [ -z "$WHEEL" ]; then
    echo "ERROR: No wheel found in dist/"
    exit 1
fi

WHEEL_FILE=$(basename "$WHEEL")

WHEEL_FOLDER="$ENV_ROOT/wheels"
echo "=== Copying wheel to $WHEEL_FOLDER ==="
mkdir -p "$WHEEL_FOLDER"
cp "$WHEEL" "$WHEEL_FOLDER"

echo "=== Installing wheel into venv ==="
"$ENV_VENV/bin/pip3" install --force-reinstall --no-cache-dir "$WHEEL_FOLDER/$WHEEL_FILE"

cp "$DEV_ROOT/requirements.txt" "$ENV_ROOT"

if [[ ! -f "$ENV_ROOT/config.yaml" ]]; then
    echo "=== Copying config.yaml to $ENV_ROOT ==="
    cp "$DEV_ROOT/config.yaml" "$ENV_ROOT"
fi

TARGET="$ENV_ROOT/.env"
if [[ ! -f "$TARGET" ]]; then
    SOURCE="$DEV_ROOT/.env.example"
    echo "=== $SOURCE to $TARGET ==="
    cp "$SOURCE" "$TARGET"
    sed -i 's/^# File: .env.example$/# File: .env/' "$TARGET"
fi

echo "=== Deployment complete ==="
