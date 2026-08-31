#!/usr/bin/env bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: scripts/install_systemd.sh

set -euo pipefail

echo ENV=$ENV

: "${ENV_VENV:?ENV_VENV is not set}"
: "${ENV_ROOT:?ENV_ROOT is not set}"

echo ENV_VENV=${ENV_VENV}
echo ENV_ROOT=${ENV_ROOT}

DEV_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo DEV_ROOT=${DEV_ROOT}

sed \
    -e "s|\${ENV_ROOT}|$ENV_ROOT|g" \
    -e "s|\${ENV_VENV}|$ENV_VENV|g" \
    "$DEV_ROOT/systemd/finance-fetch.service" |
    sudo tee /etc/systemd/system/finance-fetch.service > /dev/null

sudo cp "$DEV_ROOT/systemd/finance-fetch.timer" /etc/systemd/system/

exit 1
sudo systemctl daemon-reload
sudo systemctl enable finance-fetch.timer
sudo systemctl restart finance-fetch.service

sudo systemctl --no-pager --full status finance-fetch.service
