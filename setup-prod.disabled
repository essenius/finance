#!/usr/bin/env bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: setup-prod.sh

set -euo pipefail

echo "=== Finance Production Setup ==="

# Load environment variables from .env, including PROD_ROOT and PROD_VENV
set -a
source .env
set +a

# Ensure PROD_ROOT is set
: "${PROD_ROOT:?PROD_ROOT is not set}"

VENV="$PROD_ROOT/venv"
SYSTEMD_DIR="/etc/systemd/system"

# Create prod folder
echo "=== Creating production directory at $PROD_ROOT ==="
sudo mkdir -p "$PROD_ROOT"
sudo chown -R pi:pi "$PROD_ROOT"

# Create venv if missing
if [ ! -d "$VENV" ]; then
    echo "=== Creating Python venv ==="
    python3 -m venv "$VENV"
else
    echo "=== venv already exists ==="
fi

# Ensure pip + build tools are up to date
echo "=== Updating pip and installing build tools ==="
"$VENV/bin/pip" install --upgrade pip setuptools wheel build


# Run initial deploy
echo "=== Running initial deploy ==="
./deploy.sh

echo "=== Setup complete ==="

