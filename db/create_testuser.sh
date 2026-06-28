#!/bin/bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: db/create_testuser.sh

set -e

CONTAINER="timescaledb"
DB="test"
USER="testuser"

PASS="${TIMESCALEDB_TESTPASS}"
if [ -z "$PASS" ]; then
  echo "ERROR: TIMESCALEDB_TESTPASS is not set"
  exit 1
fi

docker exec -i "$CONTAINER" env PASS="$PASS" psql -U postgres <<'EOF'
DO $$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_roles WHERE rolname = 'testuser'
   ) THEN
      EXECUTE format('CREATE USER testuser WITH PASSWORD %L', current_setting('PASS'));
   END IF;
END
$$;

GRANT CONNECT ON DATABASE test TO testuser;

\c test

GRANT USAGE, CREATE ON SCHEMA public TO testuser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO testuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO testuser;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO testuser;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES TO testuser;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON SEQUENCES TO testuser;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON FUNCTIONS TO testuser;
EOF
