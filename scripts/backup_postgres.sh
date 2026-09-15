#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BACKUP_DATABASE_URL:-}" || -z "${BACKUP_FILE:-}" ]]; then
  echo "Usage: BACKUP_DATABASE_URL=<dsn> BACKUP_FILE=<path.dump> scripts/backup_postgres.sh" >&2
  exit 2
fi

umask 077
export PGDATABASE="${BACKUP_DATABASE_URL}"
pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="${BACKUP_FILE}"
pg_restore --list "${BACKUP_FILE}" >/dev/null
echo "Backup created and archive structure verified: ${BACKUP_FILE}"
