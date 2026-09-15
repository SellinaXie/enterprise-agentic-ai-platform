#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_DATABASE_RESTORE:-}" != "true" ]]; then
  echo "Restore refused. Set ALLOW_DATABASE_RESTORE=true after validating the target." >&2
  exit 2
fi
if [[ -z "${RESTORE_DATABASE_URL:-}" || -z "${BACKUP_FILE:-}" ]]; then
  echo "Usage: ALLOW_DATABASE_RESTORE=true RESTORE_DATABASE_URL=<dsn> BACKUP_FILE=<path.dump> scripts/restore_postgres.sh" >&2
  exit 2
fi
if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "Restore refused: backup archive does not exist." >&2
  exit 2
fi

pg_restore --list "${BACKUP_FILE}" >/dev/null
export PGDATABASE="${RESTORE_DATABASE_URL}"
pg_restore \
  --no-owner \
  --no-acl \
  --exit-on-error \
  "${BACKUP_FILE}"
echo "Restore completed. Run Alembic, readiness, and application smoke checks before cutover."
