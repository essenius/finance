#!/bin/bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: db/cleanup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# set CONTAINER, DB, USER and PASS
source "$SCRIPT_DIR/env.sh"

echo $CONTAINER 
echo $DB

# we run the process as the configured user, not as postgres
docker exec -i "$CONTAINER" env PGUSER="$USER" PGPASSWORD="$PASS" bash -lc "psql -d \"$DB\"" <<EOF

-- the cascade causes series and the series_data tables to be truncated too

TRUNCATE TABLE asset RESTART IDENTITY CASCADE;
EOF
