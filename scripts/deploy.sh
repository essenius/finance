#!/usr/bin/env bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: scripts/deploy.sh

# exit if command fails, unset variable is error, and a pipeline fails if any command in it fails
set -euo pipefail

env | grep ROOT
echo -----
env | grep VENV
echo -----
: "${ENV_VENV:?ENV_VENV is not set}"
: "${ENV_ROOT:?ENV_ROOT is not set}"

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

ENV_CREATED=false

SOURCE="$DEV_ROOT/.env.example"
TARGET="$ENV_ROOT/.env"

if [[ ! -f "$TARGET" ]]; then
    echo "=== creating $TARGET from $SOURCE ==="
    cp "$SOURCE" "$TARGET"
    sed -i 's/^# File: .env.example$/# File: .env/' "$TARGET"
    echo "Please edit $TARGET with the required production values."
    echo "Deployment will need to be re-run after configuration."
    touch "$ENV_ROOT/.configuration-incomplete"
    exit 0
fi

if ! "$ENV_VENV/bin/python" "$DEV_ROOT/scripts/validate_env.py" "$SOURCE" "$TARGET"; then
    echo "ERROR: Environment validation failed; deployment aborted."
    exit 2
fi

if [[ -f "$ENV_ROOT/.configuration-incomplete" ]]; then
    rm "$ENV_ROOT/.configuration-incomplete"
fi
echo "=== Deployment complete ==="
