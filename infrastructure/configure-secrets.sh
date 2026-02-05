#!/bin/bash
# VA Signals - Secret Manager Configuration
# GOLF COMMAND - Operation COMMAND POST
#
# This script configures Secret Manager secrets for authentication:
# 1. FIREBASE_ADMIN_SDK_KEY - Firebase service account credentials
# 2. SESSION_SECRET - HMAC key for session tokens
# 3. CSRF_SECRET - CSRF token generation key
#
# Usage: ./configure-secrets.sh [--dry-run]

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-va-signals-v2}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-va-signals-dashboard@${PROJECT_ID}.iam.gserviceaccount.com}"

# Secret names
SECRETS=(
    "FIREBASE_ADMIN_SDK_KEY"
    "SESSION_SECRET"
    "CSRF_SECRET"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    log_warn "DRY RUN MODE - No changes will be made"
fi

log_info "=== Secret Manager Configuration ==="
log_info "Project: ${PROJECT_ID}"
log_info "Service Account: ${SERVICE_ACCOUNT}"

# Enable Secret Manager API
log_info "Enabling Secret Manager API..."
if [[ "$DRY_RUN" == "false" ]]; then
    gcloud services enable secretmanager.googleapis.com --project="$PROJECT_ID" 2>/dev/null || true
fi

# Create secrets
for SECRET_NAME in "${SECRETS[@]}"; do
    log_info "Configuring secret: ${SECRET_NAME}..."

    # Check if secret exists
    SECRET_EXISTS=$(gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" 2>/dev/null && echo "yes" || echo "no")

    if [[ "$SECRET_EXISTS" == "yes" ]]; then
        log_info "Secret ${SECRET_NAME} already exists"
    else
        if [[ "$DRY_RUN" == "false" ]]; then
            log_info "Creating secret ${SECRET_NAME}..."
            gcloud secrets create "$SECRET_NAME" \
                --project="$PROJECT_ID" \
                --replication-policy="automatic"

            # Generate placeholder or prompt for value
            if [[ "$SECRET_NAME" == "SESSION_SECRET" ]] || [[ "$SECRET_NAME" == "CSRF_SECRET" ]]; then
                # Generate random secret
                RANDOM_SECRET=$(openssl rand -base64 32)
                echo -n "$RANDOM_SECRET" | gcloud secrets versions add "$SECRET_NAME" \
                    --project="$PROJECT_ID" \
                    --data-file=-
                log_info "Generated random value for ${SECRET_NAME}"
            else
                log_warn "Secret ${SECRET_NAME} created but needs a value"
                log_info "Add value with: echo -n 'SECRET_VALUE' | gcloud secrets versions add ${SECRET_NAME} --data-file=-"
            fi
        else
            log_info "Would create secret: ${SECRET_NAME}"
        fi
    fi

    # Grant access to service account
    if [[ "$DRY_RUN" == "false" ]]; then
        log_info "Granting access to service account..."
        gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
            --project="$PROJECT_ID" \
            --member="serviceAccount:${SERVICE_ACCOUNT}" \
            --role="roles/secretmanager.secretAccessor" \
            2>/dev/null || true
    fi
done

# Update Cloud Run service to use secrets
log_info "=== Cloud Run Secret Configuration ==="
log_info "Update Cloud Run service with:"
cat << 'EOF'

gcloud run services update va-signals-dashboard \
    --region=us-central1 \
    --set-secrets="FIREBASE_ADMIN_SDK_KEY=FIREBASE_ADMIN_SDK_KEY:latest" \
    --set-secrets="SESSION_SECRET=SESSION_SECRET:latest" \
    --set-secrets="CSRF_SECRET=CSRF_SECRET:latest"

EOF

log_info "=== Firebase Admin SDK Key ==="
log_info "To add Firebase Admin SDK credentials:"
log_info "1. Go to Firebase Console > Project Settings > Service Accounts"
log_info "2. Generate new private key (JSON)"
log_info "3. Add to Secret Manager:"
log_info "   cat firebase-adminsdk.json | gcloud secrets versions add FIREBASE_ADMIN_SDK_KEY --data-file=-"

log_info "=== Configuration Complete ==="
