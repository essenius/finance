#!/bin/bash
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: db/create_user.sh

# Create and configure the user for the ingestion process. Expects credentials in TIMESCALEDB_USER and TIMESCALEDB_PASSWORD

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# set CONTAINER, DB, USER and PASS
source "$SCRIPT_DIR/env.sh"

# Notice <<EOF, not <<'EOF'. Without quotes means it substitutes environment variables.
# To make that work, we need to escape $$ otherwise the shell would try and substitute that.

docker exec -i "$CONTAINER" psql -U postgres <<EOF
DO \$\$
BEGIN
   RAISE NOTICE 'DB: ${DB}, User: ${USER}';
   IF NOT EXISTS (
      SELECT 1 FROM pg_roles WHERE rolname = '${USER}'
   ) THEN
      EXECUTE format('CREATE USER ${USER} WITH PASSWORD %L', ${PASS});
   END IF;
END
\$\$;

GRANT CONNECT ON DATABASE ${DB} TO ${USER};

\connect ${DB}

GRANT USAGE, CREATE ON SCHEMA public TO ${USER};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${USER};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${USER};
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO ${USER};

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES TO ${USER};

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON SEQUENCES TO ${USER};

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON FUNCTIONS TO ${USER};


SELECT format('ALTER TABLE %I OWNER TO ${USER};', tablename)
FROM pg_tables WHERE schemaname='public' \gexec

SELECT format('ALTER SEQUENCE %I OWNER TO ${USER};', sequencename)
FROM pg_sequences WHERE schemaname='public' \gexec

EOF
