#!/bin/bash
# backup-taris-vps.sh — Daily backup of taris_vps PostgreSQL database
#
# Install: crontab -e
#   0 3 * * * /opt/taris-docker/backup-taris-vps.sh >> /var/log/taris-backup.log 2>&1
#
# Keeps last 14 backups; older ones are deleted automatically.

set -e

BACKUP_DIR="/opt/taris-docker/backups"
DB_NAME="taris_vps"
DB_USER="taris"
RETAIN_DAYS=14
TIMESTAMP=$(date +%Y-%m-%d_%H%M)
BACKUP_FILE="${BACKUP_DIR}/taris_vps_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Starting backup of ${DB_NAME}..."

# Dump + compress (password from env or default from bot.env)
PGPASSWORD="${TARIS_PG_PASSWORD:-$(grep STORE_PG_DSN /opt/taris-docker/bot.env | grep -oP ':([^:@]+)@' | tr -d ':@')}" \
  pg_dump -h 127.0.0.1 -p 5432 -U "${DB_USER}" "${DB_NAME}" | gzip > "${BACKUP_FILE}"

SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Backup written: ${BACKUP_FILE} (${SIZE})"

# Prune old backups
find "${BACKUP_DIR}" -name "taris_vps_*.sql.gz" -mtime "+${RETAIN_DAYS}" -delete
REMAINING=$(ls "${BACKUP_DIR}" | grep -c 'taris_vps_' || true)
echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Retained backups: ${REMAINING}"
