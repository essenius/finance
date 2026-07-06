#!/usr/bin/env bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: db/env.sh

# require_env NAME
# Ensures NAME exists and is non-empty.
# Returns the value via stdout.
require_env() {
  local name="$1"
  if ! declare -p "$name" >/dev/null 2>&1; then
    echo "ERROR: variable $name does not exist" >&2
    exit 1
  fi
  local value="${!name}"

  if [ -z "$value" ]; then
    echo "ERROR: $name is empty" >&2
    exit 1
  fi
  echo "$value"
}

USER="$(require_env TIMESCALEDB_USER)"
PASS="$(require_env TIMESCALEDB_PASSWORD)"
DB=test
CONTAINER=timescaledb
