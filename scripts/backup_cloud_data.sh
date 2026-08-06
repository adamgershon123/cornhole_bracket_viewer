#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/opt/cheesebaggers/cloud-data}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/cheesebaggers/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_ROOT/$STAMP/season_platform"

# SQLite's online backup command produces a consistent copy while WAL writes
# continue. Raw payloads stay in the persistent data volume and can be synced
# incrementally to S3 without stopping the application.
docker compose -f /opt/cheesebaggers/docker-compose.cloud.yml exec -T web \
  python -c "import sqlite3; src=sqlite3.connect('/data/season_platform/season_platform.db'); dst=sqlite3.connect('/data/season_platform/season_platform.backup.db'); src.backup(dst); dst.close(); src.close()"
mv "$DATA_ROOT/season_platform/season_platform.backup.db" \
  "$BACKUP_ROOT/$STAMP/season_platform/season_platform.db"

if command -v aws >/dev/null 2>&1 && [[ -n "${BACKUP_S3_URI:-}" ]]; then
  aws s3 sync "$DATA_ROOT/" "$BACKUP_S3_URI/current/" --only-show-errors
  aws s3 cp "$BACKUP_ROOT/$STAMP/season_platform/season_platform.db" \
    "$BACKUP_S3_URI/database/$STAMP.db" --only-show-errors
fi

find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf -- {} +

