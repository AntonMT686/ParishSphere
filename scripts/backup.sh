#!/usr/bin/env bash
# Back up every ParishSphere database (master + one per parish) and the uploaded files from the
# production Docker stack into backups/<timestamp>/. Keeps the last ${KEEP:-14} backups.
#   scripts/backup.sh                 # run from the repository root, e.g. nightly from cron
# Copy the backups off the server (another disk, S3, …): a backup on the same disk is not a backup.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.prod.yml")
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$ROOT/backups/$STAMP"
KEEP="${KEEP:-14}"
mkdir -p "$DEST"
chmod 700 "$ROOT/backups" "$DEST"

DBS=$("${COMPOSE[@]}" exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SHOW DATABASES"' \
  | grep -E '^(ps_master|ps_t_[a-z0-9_]+)$' || true)
if [ -z "$DBS" ]; then echo "No ParishSphere databases found" >&2; exit 1; fi
for db in $DBS; do
  "${COMPOSE[@]}" exec -T mysql sh -c "mysqldump -uroot -p\"\$MYSQL_ROOT_PASSWORD\" --single-transaction --routines --triggers --set-gtid-purged=OFF $db" \
    | gzip >"$DEST/$db.sql.gz"
  echo "  $db → $DEST/$db.sql.gz"
done
"${COMPOSE[@]}" exec -T api tar -C /data -czf - files >"$DEST/files.tar.gz"
echo "  uploaded files → $DEST/files.tar.gz"

# Retention: keep the newest $KEEP backup folders.
ls -1d "$ROOT"/backups/*/ 2>/dev/null | sort | head -n -"$KEEP" | while read -r old; do
  case "$old" in "$ROOT"/backups/2*) rm -r -- "$old" ;; esac
done
echo "backup complete: $DEST"
