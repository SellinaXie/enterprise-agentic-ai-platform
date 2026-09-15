# PostgreSQL backup, restore, and recovery

## Recovery objectives

The portfolio target is **RPO 24 hours** and **RTO 4 hours** for a small single-region deployment.
These are design targets, not measured SLAs. Production owners must select a managed PostgreSQL
plan whose backup/PITR retention supports the desired RPO and must measure the RTO in scheduled
recovery drills.

## Backup

Use a PostgreSQL client version compatible with the server. Keep DSNs in a secret manager or a
private shell environment and store archives in encrypted, access-controlled storage.

```bash
BACKUP_DATABASE_URL="$DATABASE_URL" \
BACKUP_FILE="/secure/backups/enterprise-ai-$(date +%Y%m%dT%H%M%S).dump" \
scripts/backup_postgres.sh
```

The script creates a custom-format `pg_dump` archive with ownership/ACL portability and validates
that `pg_restore` can read its catalog. This validates archive structure, not a complete recovery.

## Restore rehearsal

Never rehearse against the production database. Create a new isolated database with the same
PostgreSQL major version and pgvector available, then explicitly authorize the wrapper:

```bash
ALLOW_DATABASE_RESTORE=true \
RESTORE_DATABASE_URL="postgresql://.../enterprise_ai_restore_test" \
BACKUP_FILE="/secure/backups/enterprise-ai-20260915T120000.dump" \
scripts/restore_postgres.sh

DATABASE_URL="$RESTORE_DATABASE_URL" alembic upgrade head
DATABASE_URL="$RESTORE_DATABASE_URL" python scripts/postgres_probe.py
```

Start the API against the isolated target and verify `/readiness`, assessment reads, review audit
history, vector search, and the two synthetic demo paths. Record elapsed time, archive timestamp,
row counts, migration revision, and approver. Destroy the isolated target after evidence is
retained according to policy.

## Incident recovery sequence

1. Stop writes or isolate the failed service; preserve logs and request IDs.
2. Identify a recovery point within the agreed RPO.
3. Restore into a new database rather than overwriting the failed database.
4. Run Alembic to the application-compatible revision and complete integrity/readiness checks.
5. Point a canary API at the restored database; test before controlled cutover.
6. Update secrets/connection configuration, shift traffic, and monitor errors and gate decisions.
7. Document actual RPO/RTO and follow up on any gap.

Migration recovery favors a forward corrective migration. Database restore is for corruption,
operator error, or a failed change that cannot be repaired safely. Neither wrapper schedules
backups, encrypts archives, or replaces managed PITR.
