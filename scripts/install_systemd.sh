#!/usr/bin/env bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: scripts/install_systemd.sh

set -euo pipefail

DEV_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

sudo cp "$DEV_ROOT/systemd/finance-fetch.service" /etc/systemd/system/
sudo cp "$DEV_ROOT/systemd/finance-fetch.timer" /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable finance-fetch.timer
sudo systemctl restart finance-fetch.service

sudo systemctl --no-pager --full status finance-fetch.service
