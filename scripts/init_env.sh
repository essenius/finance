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

if [ ! -d "$ENV_ROOT" ]; then
    echo "=== Creating $ENV_ROOT ==="
    mkdir -p "$ENV_ROOT"
fi

if [ ! -d "$ENV_VENV" ]; then
    echo "=== Creating venv at $ENV_VENV ==="
    python3 -m venv "$ENV_VENV"
    "$ENV_VENV/bin/python" -m ensurepip
    "$ENV_VENV/bin/pip" install --upgrade pip wheel
fi

echo "=== Environment initialized ==="
