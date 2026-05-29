#!/usr/bin/env bash
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

WHEEL=$(ls "$DEV_ROOT"/dist/*.whl | head -n 1)
if [ -z "$WHEEL" ]; then
    echo "ERROR: No wheel found in dist/"
    exit 1
fi

WHEEL_FILE=$(basename "$WHEEL")

echo "=== Copying wheel to $ENV_ROOT ==="
cp "$WHEEL" "$ENV_ROOT/"

echo "=== Installing wheel into venv ==="
"$ENV_VENV/bin/pip" install --upgrade "$ENV_ROOT/$WHEEL_FILE"

echo "=== Deployment complete ==="
