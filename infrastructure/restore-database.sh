#!/bin/bash
# Database Restore Script
#
# Restores VA Signals database from Cloud Storage backup.
# Supports both SQLite (local) and PostgreSQL (Cloud SQL).
#
# Usage:
#   ./restore-database.sh [backup_path] [--dry-run] [--latest]
#
# Examples:
#   ./restore-database.sh --latest                    # Restore latest backup
#   ./restore-database.sh daily/signals_2026-02-01.db.gz  # Restore specific backup
#   ./restore-database.sh --dry-run --latest          # Preview restore

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-va-signals-v2}"
GCS_BUCKET="${GCS_BUCKET:-va-signals-backups}"
LOCAL_DB_PATH="${LOCAL_DB_PATH:-data/signals.db}"

# Parse arguments
DRY_RUN=false
USE_LATEST=false
BACKUP_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --latest)
            USE_LATEST=true
            shift
            ;;
        *)
            BACKUP_PATH="$1"
            shift
            ;;
    esac
done

echo "=== VA Signals Database Restore ==="
echo "Dry run: $DRY_RUN"

# Determine backup source
if [[ "$USE_LATEST" == "true" ]]; then
    GCS_PATH="gs://${GCS_BUCKET}/latest/signals_latest.db.gz"
elif [[ -n "$BACKUP_PATH" ]]; then
    # Check if full path or relative
    if [[ "$BACKUP_PATH" == gs://* ]]; then
        GCS_PATH="$BACKUP_PATH"
    else
        GCS_PATH="gs://${GCS_BUCKET}/${BACKUP_PATH}"
    fi
else
    echo "Usage: $0 [backup_path] [--dry-run] [--latest]"
    echo ""
    echo "Available backups:"
    gsutil ls -l "gs://${GCS_BUCKET}/daily/" 2>/dev/null | tail -10 || true
    gsutil ls -l "gs://${GCS_BUCKET}/weekly/" 2>/dev/null | tail -5 || true
    gsutil ls -l "gs://${GCS_BUCKET}/monthly/" 2>/dev/null | tail -3 || true
    exit 1
fi

echo "Restore source: $GCS_PATH"

# Verify backup exists
if ! gsutil stat "$GCS_PATH" > /dev/null 2>&1; then
    echo "ERROR: Backup not found: $GCS_PATH"
    exit 1
fi

# Create temp directory
RESTORE_DIR="/tmp/va-signals-restore"
mkdir -p "$RESTORE_DIR"
TIMESTAMP=$(date -u +"%Y-%m-%d_%H%M%S")

# Download backup
LOCAL_BACKUP="$RESTORE_DIR/restore_${TIMESTAMP}.db.gz"
echo "Downloading backup..."

if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY RUN] Would download: $GCS_PATH"
else
    gsutil cp "$GCS_PATH" "$LOCAL_BACKUP"
    echo "Downloaded to: $LOCAL_BACKUP"
fi

# Function to restore SQLite
restore_sqlite() {
    local backup_file="$1"
    local db_path="$2"

    echo "Restoring SQLite database to: $db_path"

    # Create backup of current database
    if [[ -f "$db_path" ]]; then
        local current_backup="${db_path}.pre-restore.${TIMESTAMP}"
        echo "Creating pre-restore backup: $current_backup"
        if [[ "$DRY_RUN" != "true" ]]; then
            cp "$db_path" "$current_backup"
        fi
    fi

    # Decompress and restore
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY RUN] Would decompress and restore to: $db_path"
    else
        gunzip -c "$backup_file" > "$db_path"
        echo "Restore complete: $db_path"

        # Verify database integrity
        echo "Verifying database integrity..."
        if sqlite3 "$db_path" "PRAGMA integrity_check;" | grep -q "ok"; then
            echo "Database integrity check: PASSED"
        else
            echo "WARNING: Database integrity check failed!"
            exit 1
        fi
    fi
}

# Function to restore PostgreSQL
restore_postgresql() {
    local backup_file="$1"
    local db_url="$2"

    echo "Restoring PostgreSQL database"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY RUN] Would restore PostgreSQL from: $backup_file"
    else
        # Decompress
        local sql_file="${backup_file%.gz}"
        gunzip -c "$backup_file" > "$sql_file"

        # Restore (this will drop and recreate tables)
        psql "$db_url" < "$sql_file"
        echo "Restore complete"

        rm -f "$sql_file"
    fi
}

# Main restore logic
if [[ -n "${DATABASE_URL:-}" ]]; then
    # PostgreSQL restore
    if [[ "$DRY_RUN" != "true" ]]; then
        restore_postgresql "$LOCAL_BACKUP" "$DATABASE_URL"
    else
        echo "[DRY RUN] Would restore PostgreSQL database"
    fi
else
    # SQLite restore
    restore_sqlite "$LOCAL_BACKUP" "$LOCAL_DB_PATH"
fi

# Cleanup
if [[ "$DRY_RUN" != "true" ]]; then
    rm -f "$LOCAL_BACKUP"
fi

echo ""
echo "=== Restore Complete ==="
echo "Source: $GCS_PATH"
echo "Target: ${DATABASE_URL:-$LOCAL_DB_PATH}"
