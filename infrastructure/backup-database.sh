#!/bin/bash
# Database Backup Script
#
# Backs up the VA Signals database to Cloud Storage with retention policy.
# Supports both SQLite (local) and PostgreSQL (Cloud SQL).
#
# Usage:
#   ./backup-database.sh [--dry-run]
#
# Environment variables:
#   DATABASE_URL     - PostgreSQL connection string (if using Cloud SQL)
#   GCS_BUCKET       - GCS bucket for backups (default: va-signals-backups)
#   BACKUP_RETENTION_DAILY   - Days to keep daily backups (default: 7)
#   BACKUP_RETENTION_WEEKLY  - Weeks to keep weekly backups (default: 4)
#   BACKUP_RETENTION_MONTHLY - Months to keep monthly backups (default: 12)

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-va-signals-v2}"
GCS_BUCKET="${GCS_BUCKET:-va-signals-backups}"
BACKUP_RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"
BACKUP_RETENTION_MONTHLY="${BACKUP_RETENTION_MONTHLY:-12}"
LOCAL_DB_PATH="${LOCAL_DB_PATH:-data/signals.db}"

# Parse arguments
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Timestamp
TIMESTAMP=$(date -u +"%Y-%m-%d_%H%M%S")
DATE=$(date -u +"%Y-%m-%d")
DAY_OF_WEEK=$(date -u +"%u")  # 1=Monday, 7=Sunday
DAY_OF_MONTH=$(date -u +"%d")

echo "=== VA Signals Database Backup ==="
echo "Timestamp: $TIMESTAMP"
echo "Dry run: $DRY_RUN"

# Determine backup type (for retention purposes)
BACKUP_TYPE="daily"
if [[ "$DAY_OF_WEEK" == "7" ]]; then
    BACKUP_TYPE="weekly"
fi
if [[ "$DAY_OF_MONTH" == "01" ]]; then
    BACKUP_TYPE="monthly"
fi
echo "Backup type: $BACKUP_TYPE"

# Create local backup directory
BACKUP_DIR="/tmp/va-signals-backups"
mkdir -p "$BACKUP_DIR"

# Function to backup SQLite
backup_sqlite() {
    local db_path="$1"
    local backup_file="$BACKUP_DIR/signals_${TIMESTAMP}.db"

    echo "Backing up SQLite database: $db_path"

    if [[ ! -f "$db_path" ]]; then
        echo "ERROR: Database file not found: $db_path"
        exit 1
    fi

    # Use SQLite's backup command for consistency
    sqlite3 "$db_path" ".backup '$backup_file'"

    # Compress
    gzip "$backup_file"
    echo "Created: ${backup_file}.gz"

    echo "${backup_file}.gz"
}

# Function to backup PostgreSQL
backup_postgresql() {
    local db_url="$1"
    local backup_file="$BACKUP_DIR/signals_${TIMESTAMP}.sql"

    echo "Backing up PostgreSQL database"

    # Extract connection details from URL
    # Format: postgresql://user:pass@host:port/dbname
    pg_dump "$db_url" > "$backup_file"

    # Compress
    gzip "$backup_file"
    echo "Created: ${backup_file}.gz"

    echo "${backup_file}.gz"
}

# Function to upload to GCS
upload_to_gcs() {
    local local_file="$1"
    local backup_type="$2"
    local filename=$(basename "$local_file")
    local gcs_path="gs://${GCS_BUCKET}/${backup_type}/${filename}"

    echo "Uploading to: $gcs_path"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY RUN] Would upload: $local_file -> $gcs_path"
    else
        gsutil cp "$local_file" "$gcs_path"
        echo "Upload complete: $gcs_path"
    fi
}

# Function to clean old backups
cleanup_old_backups() {
    local backup_type="$1"
    local retention_days="$2"

    echo "Cleaning up $backup_type backups older than $retention_days days"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY RUN] Would delete backups older than $retention_days days from gs://${GCS_BUCKET}/${backup_type}/"
        gsutil ls -l "gs://${GCS_BUCKET}/${backup_type}/" 2>/dev/null || true
    else
        # List and delete old files
        cutoff_date=$(date -u -d "$retention_days days ago" +"%Y-%m-%d" 2>/dev/null || date -u -v-${retention_days}d +"%Y-%m-%d")

        gsutil ls "gs://${GCS_BUCKET}/${backup_type}/" 2>/dev/null | while read -r file; do
            # Extract date from filename (signals_YYYY-MM-DD_HHMMSS.db.gz)
            file_date=$(basename "$file" | sed -n 's/signals_\([0-9-]*\)_.*/\1/p')
            if [[ -n "$file_date" && "$file_date" < "$cutoff_date" ]]; then
                echo "Deleting old backup: $file"
                gsutil rm "$file"
            fi
        done
    fi
}

# Main backup logic
if [[ -n "${DATABASE_URL:-}" ]]; then
    # PostgreSQL backup
    BACKUP_FILE=$(backup_postgresql "$DATABASE_URL")
else
    # SQLite backup
    BACKUP_FILE=$(backup_sqlite "$LOCAL_DB_PATH")
fi

# Upload based on backup type
upload_to_gcs "$BACKUP_FILE" "$BACKUP_TYPE"

# Also keep a copy as "latest"
if [[ "$DRY_RUN" != "true" ]]; then
    gsutil cp "$BACKUP_FILE" "gs://${GCS_BUCKET}/latest/signals_latest.db.gz"
fi

# Cleanup old backups based on retention
cleanup_old_backups "daily" "$BACKUP_RETENTION_DAILY"
cleanup_old_backups "weekly" "$((BACKUP_RETENTION_WEEKLY * 7))"
cleanup_old_backups "monthly" "$((BACKUP_RETENTION_MONTHLY * 30))"

# Cleanup local temp file
rm -f "$BACKUP_FILE"

echo ""
echo "=== Backup Complete ==="
echo "File: $BACKUP_FILE"
echo "Type: $BACKUP_TYPE"
echo "Bucket: gs://${GCS_BUCKET}/"
